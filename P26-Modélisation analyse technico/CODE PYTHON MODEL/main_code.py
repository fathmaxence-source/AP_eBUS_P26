"""
Point d'entree du simulateur P26.

Le fichier conserve son role historique d'orchestrateur principal, mais le
coeur du calcul est maintenant delegue a des services reutilisables, ce qui
permet de piloter le simulateur depuis la console, depuis une petite
interface graphique, ou via un premier apercu de flotte.
"""

from __future__ import annotations

import argparse

from bus_models import list_bus_models
from configuration_simulation import (
    SCENARIOS_DISPONIBLES,
    construire_configuration_depuis_arguments,
    construire_configuration_simulation_par_defaut,
)
from gtfs_data import charger_courses_reelles_journalieres
from service_simulation import (
    afficher_resume_simulation_console,
    executer_simulation,
)


CONFIGURATION_PAR_DEFAUT = construire_configuration_simulation_par_defaut()


def construire_parseur_arguments() -> argparse.ArgumentParser:
    """
    Construit le parseur CLI du simulateur.
    """

    parser = argparse.ArgumentParser(
        description="Simulation energetique simplifiee d'un bus GTFS."
    )
    parser.add_argument(
        "--interface",
        action="store_true",
        help="Ouvre l'interface graphique simple du simulateur.",
    )
    parser.add_argument(
        "--sans-graphiques",
        action="store_true",
        help="Genere les fichiers PNG sans ouvrir les fenetres matplotlib.",
    )
    parser.add_argument(
        "--apercu-flotte",
        action="store_true",
        help="Affiche un premier apercu de flotte a partir du service GTFS reel.",
    )
    parser.add_argument(
        "--scenario",
        type=int,
        default=CONFIGURATION_PAR_DEFAUT.recharge.scenario,
        choices=SCENARIOS_DISPONIBLES,
    )
    parser.add_argument(
        "--bus-model",
        type=str,
        default=CONFIGURATION_PAR_DEFAUT.id_modele_bus,
    )
    parser.add_argument(
        "--data-mode",
        type=str,
        default=CONFIGURATION_PAR_DEFAUT.gtfs.data_mode,
        choices=("local", "online"),
    )
    parser.add_argument("--gtfs-path", type=str, default=None)
    parser.add_argument(
        "--network-name",
        type=str,
        default=CONFIGURATION_PAR_DEFAUT.gtfs.network_name,
    )
    parser.add_argument(
        "--line-selector",
        type=str,
        default=CONFIGURATION_PAR_DEFAUT.gtfs.line_selector,
    )
    parser.add_argument("--route-id", type=str, default=None)
    parser.add_argument("--trip-id", type=str, default=None)
    parser.add_argument("--direction-id", type=str, default=None)
    parser.add_argument(
        "--cycle-count",
        type=int,
        default=CONFIGURATION_PAR_DEFAUT.gtfs.cycle_count,
    )
    parser.add_argument(
        "--default-stop-duration-s",
        type=float,
        default=CONFIGURATION_PAR_DEFAUT.gtfs.default_stop_duration_s,
    )
    parser.add_argument(
        "--service-date",
        type=str,
        default=CONFIGURATION_PAR_DEFAUT.gtfs.service_date,
    )
    parser.add_argument("--depot-name", type=str, default=None)
    parser.add_argument("--distance-depot-m", type=float, default=None)
    parser.add_argument("--vitesse-depot-m-s", type=float, default=None)
    parser.add_argument("--desactiver-haut-le-pied", action="store_true")
    parser.add_argument("--nombre-bus", type=int, default=1)
    parser.add_argument("--temps-battement-s", type=float, default=0.0)
    parser.add_argument(
        "--smart-charging",
        dest="smart_charging",
        action="store_true",
        default=True,
        help="Optimise la puissance de recharge depot pour atteindre 100 % juste avant le prochain service.",
    )
    parser.add_argument(
        "--sans-smart-charging",
        dest="smart_charging",
        action="store_false",
        help="Utilise directement la puissance maximale de la borne depot.",
    )
    parser.add_argument("--puissance-borne-depot-kw", type=float, default=None)
    parser.add_argument("--puissance-borne-terminus-kw", type=float, default=None)
    parser.add_argument("--puissance-borne-intermediaire-kw", type=float, default=None)
    parser.add_argument("--seuil-alerte-soc", type=float, default=None)
    parser.add_argument("--seuil-echec-soc", type=float, default=None)
    parser.add_argument("--list-bus-models", action="store_true")
    return parser


def analyser_arguments() -> argparse.Namespace:
    """
    Analyse les arguments CLI.
    """

    return construire_parseur_arguments().parse_args()


def afficher_modeles_bus_disponibles() -> None:
    """
    Affiche les modeles de bus disponibles.
    """

    print("Modeles de bus disponibles :")
    for model in list_bus_models():
        print(f"- {model.model_id} : {model.display_name} ({model.popularity_scope})")


def lancer_mode_interface() -> None:
    """
    Lance l'interface graphique.
    """

    from interface_simulation import lancer_interface_simulation

    lancer_interface_simulation()


def lancer_mode_console(arguments: argparse.Namespace) -> None:
    """
    Lance une simulation depuis la ligne de commande.
    """

    configuration_simulation = construire_configuration_depuis_arguments(arguments)
    resultat_simulation = executer_simulation(
        configuration_simulation=configuration_simulation,
        afficher_graphiques=not arguments.sans_graphiques,
    )
    afficher_resume_simulation_console(resultat_simulation)


def lancer_apercu_flotte(arguments: argparse.Namespace) -> None:
    """
    Affiche un premier dimensionnement de flotte a partir des departs reels.
    """

    from flotte_exploitation import (
        affecter_courses_aux_bus,
        construire_lignes_resume_flotte,
    )

    arguments_configuration = vars(arguments).copy()
    arguments_configuration["nombre_bus"] = 1
    configuration_simulation = construire_configuration_depuis_arguments(
        argparse.Namespace(**arguments_configuration)
    )

    courses, metadonnees_service = charger_courses_reelles_journalieres(
        configuration_simulation.gtfs
    )
    resultat_affectation = affecter_courses_aux_bus(
        courses=courses,
        temps_battement_s=arguments.temps_battement_s,
    )

    for ligne in construire_lignes_resume_flotte(
        resultat_affectation=resultat_affectation,
        metadonnees_service=metadonnees_service,
    ):
        print(ligne)


def main() -> None:
    arguments = analyser_arguments()
    if arguments.list_bus_models:
        afficher_modeles_bus_disponibles()
        return
    if arguments.interface:
        lancer_mode_interface()
        return
    if arguments.apercu_flotte:
        lancer_apercu_flotte(arguments)
        return
    lancer_mode_console(arguments)


if __name__ == "__main__":
    main()

#TEST