from __future__ import annotations

from dataclasses import dataclass, field, replace

from bus_models import DEFAULT_BUS_MODEL_ID
from gtfs_data import GTFSBusConfig


SCENARIOS_DISPONIBLES = (1, 2, 3)


@dataclass(frozen=True)
class ConfigurationFlotte:
    """
    Parametres de flotte.

    La logique multi-bus n'est pas encore active dans le calcul, mais le
    parametre est centralise ici pour preparer l'evolution de l'architecture.
    """

    nombre_bus: int = 1


@dataclass(frozen=True)
class ConfigurationFrequentation:
    """
    Parametres lies a la frequentation.

    Ces informations sont centralisees des maintenant, meme si leur impact
    physique sur la masse du bus sera ajoute dans une priorite ulterieure.
    """

    activer: bool = False
    masse_moyenne_passager_kg: float = 70.0
    charge_moyenne_voyageurs: float | None = None


@dataclass(frozen=True)
class ConfigurationMeteo:
    """
    Parametres meteorologiques.

    Leur effet sur la batterie et les auxiliaires sera branche dans une
    priorite ulterieure.
    """

    activer: bool = False
    temperature_exterieure_c: float | None = None
    temperature_reference_c: float = 15.0


@dataclass(frozen=True)
class ConfigurationRecharge:
    """
    Parametres de recharge centralises.
    """

    scenario: int = 1
    puissance_borne_depot_kw: float = 150.0
    puissance_borne_terminus_kw: float = 100.0
    puissance_borne_intermediaire_kw: float = 50.0
    duree_recharge_terminus_s: float = 3 * 60.0
    duree_recharge_intermediaire_s: float = 30.0
    points_recharge_intermediaire: tuple[int, ...] = (10, 22)


@dataclass(frozen=True)
class ConfigurationAlertesBatterie:
    """
    Seuils de securite batterie.
    """

    seuil_alerte_soc_pct: float = 10.0
    seuil_echec_soc_pct: float = 0.0
    interrompre_si_batterie_vide: bool = True


@dataclass(frozen=True)
class ConfigurationSimulation:
    """
    Point d'entree unique pour les parametres de simulation.

    L'objectif est de conserver l'architecture modulaire existante tout en
    regroupant au meme endroit les parametres aujourd'hui utilises et ceux
    deja prevus pour les evolutions futures.
    """

    gtfs: GTFSBusConfig
    id_modele_bus: str = DEFAULT_BUS_MODEL_ID
    flotte: ConfigurationFlotte = field(default_factory=ConfigurationFlotte)
    recharge: ConfigurationRecharge = field(default_factory=ConfigurationRecharge)
    alertes_batterie: ConfigurationAlertesBatterie = field(
        default_factory=ConfigurationAlertesBatterie
    )
    frequentation: ConfigurationFrequentation = field(
        default_factory=ConfigurationFrequentation
    )
    meteo: ConfigurationMeteo = field(default_factory=ConfigurationMeteo)


def construire_configuration_simulation_par_defaut() -> ConfigurationSimulation:
    """
    Retourne la configuration par defaut actuellement equivalente au flux
    historique du projet.
    """

    configuration_gtfs = GTFSBusConfig(
        data_mode="online",
        network_name="Reseau urbain Ametis",
        line_selector="N1",
        direction_id=None,
        cycle_count=8,
        default_stop_duration_s=30.0,
        service_date="2026-04-08",
    )
    return ConfigurationSimulation(gtfs=configuration_gtfs)


def construire_configuration_depuis_arguments(
    arguments,
) -> ConfigurationSimulation:
    """
    Construit la configuration centrale a partir des arguments CLI.
    """

    configuration = construire_configuration_simulation_par_defaut()
    configuration_gtfs = configuration.gtfs

    if getattr(arguments, "data_mode", None):
        configuration_gtfs = replace(
            configuration_gtfs,
            data_mode=arguments.data_mode,
        )
    if getattr(arguments, "network_name", None):
        configuration_gtfs = replace(
            configuration_gtfs,
            network_name=arguments.network_name,
        )
    if getattr(arguments, "line_selector", None):
        configuration_gtfs = replace(
            configuration_gtfs,
            line_selector=arguments.line_selector,
        )
    if getattr(arguments, "route_id", None):
        configuration_gtfs = replace(
            configuration_gtfs,
            route_id=arguments.route_id,
        )
    if getattr(arguments, "trip_id", None):
        configuration_gtfs = replace(
            configuration_gtfs,
            trip_id=arguments.trip_id,
        )
    if getattr(arguments, "direction_id", None) is not None:
        configuration_gtfs = replace(
            configuration_gtfs,
            direction_id=arguments.direction_id,
        )
    if getattr(arguments, "cycle_count", None) is not None:
        configuration_gtfs = replace(
            configuration_gtfs,
            cycle_count=arguments.cycle_count,
        )
    if getattr(arguments, "default_stop_duration_s", None) is not None:
        configuration_gtfs = replace(
            configuration_gtfs,
            default_stop_duration_s=arguments.default_stop_duration_s,
        )
    if getattr(arguments, "service_date", None):
        configuration_gtfs = replace(
            configuration_gtfs,
            service_date=arguments.service_date,
        )
    if getattr(arguments, "desactiver_haut_le_pied", False):
        configuration_gtfs = replace(
            configuration_gtfs,
            include_depot_deadhead=False,
        )
    if getattr(arguments, "distance_depot_m", None) is not None:
        configuration_gtfs = replace(
            configuration_gtfs,
            depot_deadhead_distance_m=arguments.distance_depot_m,
        )
    if getattr(arguments, "vitesse_depot_m_s", None) is not None:
        configuration_gtfs = replace(
            configuration_gtfs,
            depot_deadhead_speed_m_s=arguments.vitesse_depot_m_s,
        )
    if getattr(arguments, "depot_name", None):
        configuration_gtfs = replace(
            configuration_gtfs,
            depot_name=arguments.depot_name,
        )
    if getattr(arguments, "gtfs_path", None):
        configuration_gtfs = replace(
            configuration_gtfs,
            gtfs_path=arguments.gtfs_path,
            data_mode="local",
        )

    configuration_recharge = replace(
        configuration.recharge,
        scenario=arguments.scenario,
        puissance_borne_depot_kw=(
            arguments.puissance_borne_depot_kw
            if getattr(arguments, "puissance_borne_depot_kw", None) is not None
            else configuration.recharge.puissance_borne_depot_kw
        ),
        puissance_borne_terminus_kw=(
            arguments.puissance_borne_terminus_kw
            if getattr(arguments, "puissance_borne_terminus_kw", None) is not None
            else configuration.recharge.puissance_borne_terminus_kw
        ),
        puissance_borne_intermediaire_kw=(
            arguments.puissance_borne_intermediaire_kw
            if getattr(arguments, "puissance_borne_intermediaire_kw", None) is not None
            else configuration.recharge.puissance_borne_intermediaire_kw
        ),
    )

    configuration_alertes = replace(
        configuration.alertes_batterie,
        seuil_alerte_soc_pct=(
            arguments.seuil_alerte_soc
            if getattr(arguments, "seuil_alerte_soc", None) is not None
            else configuration.alertes_batterie.seuil_alerte_soc_pct
        ),
        seuil_echec_soc_pct=(
            arguments.seuil_echec_soc
            if getattr(arguments, "seuil_echec_soc", None) is not None
            else configuration.alertes_batterie.seuil_echec_soc_pct
        ),
    )

    configuration_flotte = replace(
        configuration.flotte,
        nombre_bus=(
            arguments.nombre_bus
            if getattr(arguments, "nombre_bus", None) is not None
            else configuration.flotte.nombre_bus
        ),
    )

    configuration_finale = replace(
        configuration,
        gtfs=configuration_gtfs,
        id_modele_bus=arguments.bus_model,
        flotte=configuration_flotte,
        recharge=configuration_recharge,
        alertes_batterie=configuration_alertes,
    )
    valider_configuration_simulation(configuration_finale)
    return configuration_finale


def valider_configuration_simulation(configuration: ConfigurationSimulation) -> None:
    """
    Valide la coherence minimale des parametres centralises.
    """

    if configuration.recharge.scenario not in SCENARIOS_DISPONIBLES:
        raise ValueError(
            "Scenario de recharge invalide. Valeurs autorisees : "
            f"{', '.join(str(valeur) for valeur in SCENARIOS_DISPONIBLES)}."
        )

    if configuration.flotte.nombre_bus <= 0:
        raise ValueError("Le nombre de bus doit etre strictement positif.")

    if configuration.flotte.nombre_bus != 1:
        raise NotImplementedError(
            "La configuration multi-bus est maintenant centralisee, "
            "mais le calcul flotte n'est pas encore implemente."
        )

    if configuration.gtfs.cycle_count <= 0:
        raise ValueError("Le nombre de cycles doit etre strictement positif.")

    if configuration.gtfs.default_stop_duration_s < 0:
        raise ValueError("La duree d'arret par defaut ne peut pas etre negative.")

    if configuration.gtfs.include_depot_deadhead:
        if configuration.gtfs.depot_deadhead_distance_m <= 0:
            raise ValueError(
                "La distance du trajet depot doit etre strictement positive."
            )
        if configuration.gtfs.depot_deadhead_speed_m_s <= 0:
            raise ValueError(
                "La vitesse du trajet depot doit etre strictement positive."
            )

    if configuration.recharge.puissance_borne_depot_kw <= 0:
        raise ValueError("La puissance de la borne depot doit etre > 0 kW.")
    if configuration.recharge.puissance_borne_terminus_kw <= 0:
        raise ValueError("La puissance de la borne terminus doit etre > 0 kW.")
    if configuration.recharge.puissance_borne_intermediaire_kw <= 0:
        raise ValueError(
            "La puissance de la borne intermediaire doit etre > 0 kW."
        )

    if not (0 <= configuration.alertes_batterie.seuil_echec_soc_pct <= 100):
        raise ValueError("Le seuil d'echec SoC doit etre compris entre 0 et 100 %.")
    if not (0 <= configuration.alertes_batterie.seuil_alerte_soc_pct <= 100):
        raise ValueError("Le seuil d'alerte SoC doit etre compris entre 0 et 100 %.")
    if (
        configuration.alertes_batterie.seuil_echec_soc_pct
        > configuration.alertes_batterie.seuil_alerte_soc_pct
    ):
        raise ValueError(
            "Le seuil d'echec SoC ne peut pas etre superieur au seuil d'alerte."
        )
