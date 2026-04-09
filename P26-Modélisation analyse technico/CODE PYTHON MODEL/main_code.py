"""
Calcule les indicateurs bus entre chaque arret a partir du GTFS.

Le GTFS est recupere via l'API transport.data.gouv.fr. Le script reste
centre sur un seul bus et une seule ligne, mais il permet maintenant de
choisir entre plusieurs modeles de bus electriques pour comparer les
resultats par scenario.
"""

import argparse
from dataclasses import replace
from pathlib import Path

import pandas as pd

from bus_models import (
    DEFAULT_BUS_MODEL_ID,
    build_bus_models_reference_table,
    get_bus_model,
    list_bus_models,
)
from gtfs_data import GTFSBusConfig, load_single_bus_service
from route_power import route_power
from route_soc import build_battery_alert_message, route_soc


SCENARIO = 1
PTERMINAL = 150.0
BUS_MODEL_ID = DEFAULT_BUS_MODEL_ID

GTFS_CONFIG = GTFSBusConfig(
    data_mode="online",
    network_name="Reseau urbain Ametis",
    line_selector="N1",
    direction_id=None,
    cycle_count=8,
    default_stop_duration_s=30.0,
    service_date="2026-04-08",
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulation energetique simplifiee d'un bus GTFS.")
    parser.add_argument("--scenario", type=int, default=SCENARIO, choices=(1, 2, 3))
    parser.add_argument("--bus-model", type=str, default=BUS_MODEL_ID)
    parser.add_argument("--gtfs-path", type=str, default=None)
    parser.add_argument("--list-bus-models", action="store_true")
    return parser.parse_args()


def print_available_bus_models() -> None:
    print("Modeles de bus disponibles :")
    for model in list_bus_models():
        print(f"- {model.model_id} : {model.display_name} ({model.popularity_scope})")


def main() -> None:
    args = parse_arguments()
    if args.list_bus_models:
        print_available_bus_models()
        return

    import matplotlib.pyplot as plt

    from bus_analysis import (
        build_full_day_profile,
        build_realtime_profile,
        plot_energy_consumption_over_time,
        plot_power_over_time,
        plot_soc_over_time,
        # build_segment_summary,
        # export_analysis_tables,
        # plot_distance_soc_over_time,
        # plot_realtime_dashboard,
        # plot_segment_dashboard,
        # print_segment_preview,
    )

    selected_bus_model = get_bus_model(args.bus_model)
    gtfs_config = GTFS_CONFIG
    if args.gtfs_path:
        gtfs_config = replace(
            GTFS_CONFIG,
            gtfs_path=args.gtfs_path,
            data_mode="local",
        )

    tabl, metadata = load_single_bus_service(gtfs_config)

    tabl = route_power(tabl, args.scenario, bus_model=selected_bus_model)
    tabl, eb = route_soc(tabl, bus_model=selected_bus_model)

    start_day = metadata["start_time"]
    tabl["TimeHour"] = start_day + pd.to_timedelta(tabl["Time"], unit="s")
    end_day = tabl["TimeHour"].iloc[-1]

    realtime_profile = build_realtime_profile(tabl)
    full_day_profile, charge_metadata = build_full_day_profile(
        realtime_profile=realtime_profile,
        battery_capacity_kwh=eb,
        service_start_time=start_day,
        terminal_power_kw=PTERMINAL,
    )

    output_dir = (
        Path(__file__).resolve().parent
        / "outputs"
        / f"scenario_{args.scenario}"
        / selected_bus_model.model_id
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    legacy_output_paths = [
        output_dir / "bus_realtime_profile.csv",
        output_dir / "bus_segment_summary.csv",
        output_dir / "bus_full_day_profile.csv",
        output_dir / "bus_models_reference.csv",
        output_dir / "bus_realtime_dashboard.png",
        output_dir / "bus_segment_dashboard.png",
        output_dir / "bus_distance_soc_recharge.png",
    ]
    for legacy_output_path in legacy_output_paths:
        if legacy_output_path.exists():
            legacy_output_path.unlink()

    # Sorties tabulaires desactivees temporairement pour ne garder
    # que les trois graphes demandes.
    # segment_summary = build_segment_summary(tabl)
    # realtime_csv, segments_csv = export_analysis_tables(
    #     realtime_profile=realtime_profile,
    #     segment_summary=segment_summary,
    #     output_dir=output_dir,
    # )
    # full_day_csv = output_dir / "bus_full_day_profile.csv"
    # full_day_profile.to_csv(full_day_csv, index=False)
    # models_reference_csv = output_dir / "bus_models_reference.csv"
    # build_bus_models_reference_table().to_csv(models_reference_csv, index=False)

    route_name = metadata["route_long_name"] or metadata["route_short_name"] or metadata["route_id"]
    plot_title = f"{route_name} - {selected_bus_model.display_name}"

    print(f"Reseau GTFS : {gtfs_config.network_name}")
    print(f"Ligne       : {route_name}")
    print(f"Scenario    : {args.scenario}")
    print(f"Modele bus  : {selected_bus_model.display_name}")
    print(f"Constructeur: {selected_bus_model.manufacturer}")
    print(f"Trips       : {', '.join(metadata['trip_ids'])}")
    print(f"Cycles      : {metadata['cycle_count']}")
    print(f"Depart      : {start_day}")
    print(f"1er arret   : {metadata['first_stop_departure']}")
    print(f"Fin service : {end_day}")
    print(f"Distance    : {realtime_profile['CumulativeDistance_km'].iloc[-1]:.2f} km")
    print(f"Energie     : {realtime_profile['EnergyUsed_kWh'].sum():.2f} kWh")
    print(f"SoC final   : {tabl['SoC'].iloc[-1]:.2f} %")
    print(f"Charge soir : {charge_metadata['charge_power_kw']:.2f} kW")
    print(f"Fin charge  : {charge_metadata['next_start_time']}")
    print(f"Batterie    : {eb:.2f} kWh")
    print(f"Masse ref   : {selected_bus_model.reference_mass_kg:.0f} kg")
    print(f"Surface AV  : {selected_bus_model.frontal_area_m2:.2f} m2")
    # print(f"CSV temps reel : {realtime_csv}")
    # print(f"CSV segments   : {segments_csv}")
    # print(f"CSV jour complet : {full_day_csv}")
    # print(f"CSV modeles     : {models_reference_csv}")
    if metadata["include_depot_deadhead"]:
        print(
            "Hypothese depot : "
            f"{metadata['depot_deadhead_distance_m'] / 1000:.1f} km a "
            f"{metadata['depot_deadhead_speed_m_s']:.1f} m/s au depart et au retour"
        )
    battery_alert_message = build_battery_alert_message(tabl)
    if battery_alert_message:
        print(battery_alert_message)

    # print_segment_preview(segment_summary)

    power_time_plot = output_dir / "bus_power_over_time.png"
    soc_time_plot = output_dir / "bus_soc_over_time.png"
    energy_time_plot = output_dir / "bus_energy_consumption_over_time.png"

    plot_power_over_time(
        full_day_profile=full_day_profile,
        route_name=plot_title,
        output_path=power_time_plot,
    )
    plot_soc_over_time(
        full_day_profile=full_day_profile,
        route_name=plot_title,
        output_path=soc_time_plot,
    )
    plot_energy_consumption_over_time(
        full_day_profile=full_day_profile,
        route_name=plot_title,
        output_path=energy_time_plot,
    )

    print(f"Graphe puissance/temps : {power_time_plot}")
    print(f"Graphe SoC/temps       : {soc_time_plot}")
    print(f"Graphe energie/temps : {energy_time_plot}")

    if "agg" not in plt.get_backend().lower():
        plt.show()


if __name__ == "__main__":
    main()
