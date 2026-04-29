from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from bus_models import BusModel, get_bus_model
from configuration_simulation import ConfigurationSimulation
from gtfs_data import load_single_bus_service
from route_power import calculer_puissance_parcours
from route_soc import calculer_soc_parcours, construire_message_alerte_batterie


@dataclass(frozen=True)
class ResultatSimulation:
    """
    Conteneur unique des sorties de simulation.
    """

    configuration_simulation: ConfigurationSimulation
    modele_bus: BusModel
    tableau_parcours: pd.DataFrame
    profil_temps_reel: pd.DataFrame
    profil_jour_complet: pd.DataFrame
    metadonnees_gtfs: dict[str, Any]
    metadonnees_charge: dict[str, Any]
    capacite_batterie_kwh: float
    dossier_sortie: Path
    chemins_graphes: dict[str, Path]
    message_alerte_batterie: str | None


def construire_dossier_sortie(
    configuration_simulation: ConfigurationSimulation,
    modele_bus: BusModel,
) -> Path:
    """
    Calcule le dossier de sortie standard d'une simulation.
    """

    return (
        Path(__file__).resolve().parent
        / "outputs"
        / f"scenario_{configuration_simulation.recharge.scenario}"
        / modele_bus.model_id
    )


def nettoyer_anciennes_sorties(dossier_sortie: Path) -> None:
    """
    Supprime les sorties historiques que l'on ne souhaite plus conserver.
    """

    anciens_noms = (
        "bus_realtime_profile.csv",
        "bus_segment_summary.csv",
        "bus_full_day_profile.csv",
        "bus_models_reference.csv",
        "bus_realtime_dashboard.png",
        "bus_segment_dashboard.png",
        "bus_distance_soc_recharge.png",
    )
    for ancien_nom in anciens_noms:
        chemin = dossier_sortie / ancien_nom
        if chemin.exists():
            chemin.unlink()


def executer_simulation(
    configuration_simulation: ConfigurationSimulation,
    afficher_graphiques: bool = True,
) -> ResultatSimulation:
    """
    Execute le pipeline complet de simulation a partir d'une configuration.
    """

    import matplotlib.pyplot as plt

    from bus_analysis import (
        build_full_day_profile,
        build_realtime_profile,
        plot_energy_consumption_over_time,
        plot_power_over_time,
        plot_soc_over_time,
    )

    modele_bus = get_bus_model(configuration_simulation.id_modele_bus)
    tableau_parcours, metadonnees_gtfs = load_single_bus_service(
        configuration_simulation.gtfs
    )

    tableau_parcours = calculer_puissance_parcours(
        tabl=tableau_parcours,
        configuration_recharge=configuration_simulation.recharge,
        bus_model=modele_bus,
    )
    tableau_parcours, capacite_batterie_kwh = calculer_soc_parcours(
        tabl=tableau_parcours,
        bus_model=modele_bus,
    )

    debut_service = metadonnees_gtfs["start_time"]
    tableau_parcours = tableau_parcours.copy()
    tableau_parcours["TimeHour"] = debut_service + pd.to_timedelta(
        tableau_parcours["Time"],
        unit="s",
    )

    profil_temps_reel = build_realtime_profile(tableau_parcours)
    profil_jour_complet, metadonnees_charge = build_full_day_profile(
        realtime_profile=profil_temps_reel,
        battery_capacity_kwh=capacite_batterie_kwh,
        service_start_time=debut_service,
        terminal_power_kw=configuration_simulation.recharge.puissance_borne_depot_kw,
        smart_charging=configuration_simulation.recharge.smart_charging  # Passage du paramètre
    )

    dossier_sortie = construire_dossier_sortie(
        configuration_simulation=configuration_simulation,
        modele_bus=modele_bus,
    )
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    nettoyer_anciennes_sorties(dossier_sortie)

    nom_ligne = (
        metadonnees_gtfs["route_long_name"]
        or metadonnees_gtfs["route_short_name"]
        or metadonnees_gtfs["route_id"]
    )
    titre_graphes = f"{nom_ligne} - {modele_bus.display_name}"
    chemins_graphes = {
        "puissance": dossier_sortie / "bus_power_over_time.png",
        "soc": dossier_sortie / "bus_soc_over_time.png",
        "energie": dossier_sortie / "bus_energy_consumption_over_time.png",
    }

    plot_power_over_time(
        full_day_profile=profil_jour_complet,
        route_name=titre_graphes,
        output_path=chemins_graphes["puissance"],
    )
    plot_soc_over_time(
        full_day_profile=profil_jour_complet,
        route_name=titre_graphes,
        output_path=chemins_graphes["soc"],
    )
    plot_energy_consumption_over_time(
        full_day_profile=profil_jour_complet,
        route_name=titre_graphes,
        output_path=chemins_graphes["energie"],
    )

    message_alerte_batterie = construire_message_alerte_batterie(
        tabl=tableau_parcours,
        configuration_alertes=configuration_simulation.alertes_batterie,
    )

    if afficher_graphiques and "agg" not in plt.get_backend().lower():
        plt.show()
    else:
        plt.close("all")

    return ResultatSimulation(
        configuration_simulation=configuration_simulation,
        modele_bus=modele_bus,
        tableau_parcours=tableau_parcours,
        profil_temps_reel=profil_temps_reel,
        profil_jour_complet=profil_jour_complet,
        metadonnees_gtfs=metadonnees_gtfs,
        metadonnees_charge=metadonnees_charge,
        capacite_batterie_kwh=capacite_batterie_kwh,
        dossier_sortie=dossier_sortie,
        chemins_graphes=chemins_graphes,
        message_alerte_batterie=message_alerte_batterie,
    )


def construire_lignes_resume_simulation(
    resultat_simulation: ResultatSimulation,
) -> list[str]:
    """
    Formate un resume textuel unique reutilisable par le CLI et l'interface.
    """

    configuration = resultat_simulation.configuration_simulation
    metadonnees_gtfs = resultat_simulation.metadonnees_gtfs
    metadonnees_charge = resultat_simulation.metadonnees_charge
    profil_temps_reel = resultat_simulation.profil_temps_reel
    tableau_parcours = resultat_simulation.tableau_parcours
    modele_bus = resultat_simulation.modele_bus

    nom_ligne = (
        metadonnees_gtfs["route_long_name"]
        or metadonnees_gtfs["route_short_name"]
        or metadonnees_gtfs["route_id"]
    )
    lignes = [
        f"Reseau GTFS : {configuration.gtfs.network_name}",
        f"Ligne       : {nom_ligne}",
        f"Scenario    : {configuration.recharge.scenario}",
        f"Modele bus  : {modele_bus.display_name}",
        f"Constructeur: {modele_bus.manufacturer}",
        f"Nb bus      : {configuration.flotte.nombre_bus}",
        f"Trips       : {', '.join(metadonnees_gtfs['trip_ids'])}",
        f"Cycles      : {metadonnees_gtfs['cycle_count']}",
        f"Depart      : {metadonnees_gtfs['start_time']}",
        f"1er arret   : {metadonnees_gtfs['first_stop_departure']}",
        f"Fin service : {tableau_parcours['TimeHour'].iloc[-1]}",
        f"Distance    : {profil_temps_reel['CumulativeDistance_km'].iloc[-1]:.2f} km",
        f"Energie     : {profil_temps_reel['EnergyUsed_kWh'].sum():.2f} kWh",
        f"SoC final   : {tableau_parcours['SoC'].iloc[-1]:.2f} %",
        f"Charge soir : {metadonnees_charge['charge_power_kw']:.2f} kW",
        f"Borne depot : {configuration.recharge.puissance_borne_depot_kw:.2f} kW",
        "Fin charge  : "
        f"{metadonnees_charge.get('actual_charge_end_time', metadonnees_charge['next_start_time'])}",
        f"Batterie    : {resultat_simulation.capacite_batterie_kwh:.2f} kWh",
        f"Masse ref   : {modele_bus.reference_mass_kg:.0f} kg",
        f"Surface AV  : {modele_bus.frontal_area_m2:.2f} m2",
        f"Alerte SoC  : {configuration.alertes_batterie.seuil_alerte_soc_pct:.2f} %",
        f"Echec SoC   : {configuration.alertes_batterie.seuil_echec_soc_pct:.2f} %",
    ]

    if metadonnees_gtfs["include_depot_deadhead"]:
        lignes.append(
            "Hypothese depot : "
            f"{metadonnees_gtfs['depot_deadhead_distance_m'] / 1000:.1f} km a "
            f"{metadonnees_gtfs['depot_deadhead_speed_m_s']:.1f} m/s au depart et au retour"
        )

    if resultat_simulation.message_alerte_batterie:
        lignes.append(resultat_simulation.message_alerte_batterie)

    lignes.extend(
        [
            f"Graphe puissance/temps : {resultat_simulation.chemins_graphes['puissance']}",
            f"Graphe SoC/temps       : {resultat_simulation.chemins_graphes['soc']}",
            f"Graphe energie/temps   : {resultat_simulation.chemins_graphes['energie']}",
        ]
    )
    return lignes


def afficher_resume_simulation_console(
    resultat_simulation: ResultatSimulation,
) -> None:
    """
    Affiche le resume standard dans la console.
    """

    for ligne in construire_lignes_resume_simulation(resultat_simulation):
        print(ligne)
        

