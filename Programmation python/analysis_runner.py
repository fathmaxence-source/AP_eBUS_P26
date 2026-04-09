from pathlib import Path

from altimetry_services import (
    create_online_altimetry_source,
    describe_altimetry_source,
    select_local_altimetry_dataset,
)
from app_models import BusParameters
from energy_logic import build_scenario_comparisons, compute_trip_energy
from gtfs_services import build_raw_segments_from_gtfs, compute_selected_gtfs_bounds
from project_paths import get_altimetry_search_root
from validation_services import compare_trip_with_legacy_reference


def resolve_positive_integer(value: object, label: str) -> int:
    try:
        integer_value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} doit être un entier strictement positif.") from exc

    if integer_value <= 0:
        raise ValueError(f"{label} doit être un entier strictement positif.")

    return integer_value


def scale_scenario_comparisons(
    comparisons: list[dict],
    multiplier: int,
) -> list[dict]:
    scaled_comparisons: list[dict] = []
    for scenario in comparisons:
        scaled_scenario = dict(scenario)
        scaled_scenario["total_energy_kwh"] = scenario["total_energy_kwh"] * multiplier
        scaled_scenario["delta_energy_kwh"] = scenario["delta_energy_kwh"] * multiplier
        scaled_comparisons.append(scaled_scenario)
    return scaled_comparisons


def build_operation_results(
    gtfs_data: dict,
    reference_results: dict,
    round_trip_count: int,
    bus_count: int,
) -> dict:
    multiplier = round_trip_count * bus_count
    operation_results = dict(reference_results)

    operation_results["reference_total_distance_km"] = reference_results["total_distance_km"]
    operation_results["reference_total_energy_kwh"] = reference_results["total_energy_kwh"]
    operation_results["reference_total_turn_energy_kwh"] = reference_results["total_turn_energy_kwh"]
    operation_results["reference_total_turn_points"] = reference_results["total_turn_points"]
    operation_results["reference_total_sharp_turns"] = reference_results["total_sharp_turns"]
    operation_results["reference_segment_count"] = len(reference_results["segments"])
    operation_results["analysis_unit_label"] = (
        "aller-retour"
        if len(gtfs_data.get("trip_summaries", [])) > 1
        else "trajet sélectionné"
    )
    operation_results["analysis_unit_count"] = round_trip_count
    operation_results["bus_count"] = bus_count
    operation_results["operation_multiplier"] = multiplier
    operation_results["operation_segment_count"] = len(reference_results["segments"]) * multiplier

    operation_results["total_distance_km"] = reference_results["total_distance_km"] * multiplier
    operation_results["total_energy_kwh"] = reference_results["total_energy_kwh"] * multiplier
    operation_results["total_turn_energy_kwh"] = reference_results["total_turn_energy_kwh"] * multiplier
    operation_results["total_turn_points"] = reference_results["total_turn_points"] * multiplier
    operation_results["total_sharp_turns"] = reference_results["total_sharp_turns"] * multiplier
    operation_results["scenario_comparisons"] = scale_scenario_comparisons(
        reference_results.get("scenario_comparisons", []),
        multiplier,
    )

    return operation_results


def run_analysis(arguments) -> tuple[dict, dict]:
    gtfs_dir = arguments.gtfs_path
    if gtfs_dir is None:
        raise ValueError("Le répertoire GTFS n'a pas été résolu avant le lancement de l'analyse.")

    altimetry_source = None
    altimetry_metadata = describe_altimetry_source(None)
    altimetry_search_root = get_altimetry_search_root()
    if not arguments.disable_altimetry:
        geographic_bounds = compute_selected_gtfs_bounds(
            gtfs_dir=gtfs_dir,
            trip_id=arguments.trip_id,
            route_id=arguments.route_id,
            line_selector=arguments.line,
            direction_id=arguments.direction_id,
        )
        if arguments.data_mode == "online":
            altimetry_source = create_online_altimetry_source()
            altimetry_metadata = describe_altimetry_source(
                altimetry_source,
                selection_mode="online",
                geographic_bounds=geographic_bounds,
                search_root=altimetry_search_root,
            )
        else:
            altimetry_source = select_local_altimetry_dataset(
                search_root=altimetry_search_root,
                geographic_bounds=geographic_bounds,
            )
            altimetry_metadata = describe_altimetry_source(
                altimetry_source,
                selection_mode="auto",
                geographic_bounds=geographic_bounds,
                search_root=altimetry_search_root,
            )

    gtfs_data = build_raw_segments_from_gtfs(
        gtfs_dir=gtfs_dir,
        altimetry_source=altimetry_source,
        trip_id=arguments.trip_id,
        route_id=arguments.route_id,
        line_selector=arguments.line,
        direction_id=arguments.direction_id,
        max_segments=arguments.max_segments,
        data_mode=arguments.data_mode,
    )
    gtfs_data["altimetry_enabled"] = altimetry_metadata["enabled"]
    gtfs_data["altimetry_label"] = altimetry_metadata["label"]
    gtfs_data["altimetry_mode"] = altimetry_metadata["mode"]
    gtfs_data["altimetry_tile_count"] = altimetry_metadata["tile_count"]
    gtfs_data["altimetry_dataset_names"] = altimetry_metadata.get("dataset_names", [])
    gtfs_data["gtfs_bounds"] = altimetry_metadata.get("bounds")

    raw_segments = gtfs_data["raw_segments"]
    if not raw_segments:
        raise ValueError("Aucun segment exploitable n'a été trouvé dans le feed GTFS.")

    raw_bus = getattr(arguments, "bus_parameters", None)
    if isinstance(raw_bus, BusParameters):
        bus = BusParameters(
            mass_kg=raw_bus.mass_kg,
            g=raw_bus.g,
            air_density=raw_bus.air_density,
            rolling_coeff=raw_bus.rolling_coeff,
            frontal_area_m2=raw_bus.frontal_area_m2,
            drag_coeff=raw_bus.drag_coeff,
            aux_power_kw=raw_bus.aux_power_kw,
        )
    elif isinstance(raw_bus, dict):
        bus = BusParameters(**raw_bus)
    else:
        bus = BusParameters()

    round_trip_count = resolve_positive_integer(
        getattr(arguments, "round_trip_count", getattr(arguments, "round_trips", 1)),
        "Le nombre d'allers-retours",
    )
    bus_count = resolve_positive_integer(
        getattr(arguments, "bus_count", 1),
        "Le nombre de bus",
    )

    reference_results = compute_trip_energy(raw_segments, bus)
    reference_results["scenario_comparisons"] = build_scenario_comparisons(raw_segments, bus)
    reference_results["bus_parameters"] = {
        "mass_kg": bus.mass_kg,
        "g": bus.g,
        "air_density": bus.air_density,
        "rolling_coeff": bus.rolling_coeff,
        "frontal_area_m2": bus.frontal_area_m2,
        "drag_coeff": bus.drag_coeff,
        "aux_power_kw": bus.aux_power_kw,
    }
    reference_results["bus_parameters_mode"] = (
        "default" if getattr(arguments, "use_default_bus_parameters", True) else "custom"
    )

    if arguments.validation_file:
        historical_validation = compare_trip_with_legacy_reference(
            raw_segments=raw_segments,
            results=reference_results,
            validation_path=arguments.validation_file,
        )
    else:
        historical_validation = None

    results = build_operation_results(
        gtfs_data=gtfs_data,
        reference_results=reference_results,
        round_trip_count=round_trip_count,
        bus_count=bus_count,
    )
    results["historical_validation"] = historical_validation

    return gtfs_data, results
