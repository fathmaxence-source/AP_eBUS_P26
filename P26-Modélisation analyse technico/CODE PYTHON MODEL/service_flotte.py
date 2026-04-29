from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import unicodedata
from typing import Any

import pandas as pd

from bus_models import BusModel, get_bus_model
from configuration_simulation import ConfigurationSimulation
from flotte_exploitation import ResultatAffectationFlotte, affecter_courses_aux_bus
from gtfs_data import charger_courses_et_segments_reels_journaliers
from route_power import calculer_puissance_parcours
from route_soc import calculer_soc_parcours, construire_message_alerte_batterie


@dataclass(frozen=True)
class ResultatSimulationFlotte:
    """
    Resultat de la premiere simulation energetique bus par bus.

    Cette version ne gere pas encore les conflits de bornes ni les recharges
    partagees : elle simule l'exploitation journaliere de chaque bus affecte.
    """

    configuration_simulation: ConfigurationSimulation
    modele_bus: BusModel
    metadonnees_service: dict[str, Any]
    resultat_affectation: ResultatAffectationFlotte
    resume_energie_bus: pd.DataFrame
    profils_bus: dict[int, pd.DataFrame]
    capacite_batterie_kwh: float


def _ligne_inactive(
    *,
    bus_index: int,
    trip_id: str,
    nom_arret: str,
    duree_s: float,
    phase: str,
    course_index: int | None = None,
) -> dict[str, Any]:
    return {
        "Stop": 0,
        "Alpha": 0.0,
        "Distance": 0.0,
        "Velocity": 0.0,
        "deltaT": float(max(duree_s, 0.0)),
        "TripID": trip_id,
        "StartStopName": nom_arret,
        "EndStopName": nom_arret,
        "BusIndex": bus_index,
        "CourseIndex": course_index,
        "Phase": phase,
    }


def _ligne_haut_le_pied(
    *,
    bus_index: int,
    trip_id: str,
    depart: str,
    arrivee: str,
    distance_m: float,
    vitesse_m_s: float,
    phase: str,
) -> dict[str, Any]:
    duree_s = distance_m / vitesse_m_s if vitesse_m_s > 0 else 0.0
    return {
        "Stop": 1,
        "Alpha": 0.0,
        "Distance": float(distance_m),
        "Velocity": float(vitesse_m_s),
        "deltaT": float(duree_s),
        "TripID": trip_id,
        "StartStopName": depart,
        "EndStopName": arrivee,
        "BusIndex": bus_index,
        "CourseIndex": None,
        "Phase": phase,
    }


def _preparer_segment_service(
    segment: dict[str, Any],
    bus_index: int,
) -> dict[str, Any]:
    ligne = {
        "Stop": int(segment["Stop"]),
        "Alpha": float(segment["Alpha"]),
        "Distance": float(segment["Distance"]),
        "Velocity": float(segment["Velocity"]),
        "deltaT": float(segment["deltaT"]),
        "TripID": segment["TripID"],
        "StartStopName": segment["StartStopName"],
        "EndStopName": segment["EndStopName"],
        "BusIndex": bus_index,
        "CourseIndex": int(segment["CourseIndex"]),
        "SegmentIndex": int(segment["SegmentIndex"]),
        "Phase": "SERVICE",
    }
    return ligne


def construire_parcours_bus(
    *,
    bus_index: int,
    courses_bus: pd.DataFrame,
    segments_courses: pd.DataFrame,
    configuration_simulation: ConfigurationSimulation,
) -> pd.DataFrame:
    """
    Reconstruit le parcours chronologique d'un bus affecte a plusieurs courses.
    """

    if courses_bus.empty:
        raise ValueError(f"Le bus {bus_index} ne contient aucune course.")

    configuration_gtfs = configuration_simulation.gtfs
    if (
        configuration_gtfs.include_depot_deadhead
        and configuration_gtfs.depot_deadhead_speed_m_s <= 0
    ):
        raise ValueError("La vitesse du haut-le-pied depot doit etre > 0 m/s.")

    courses_bus = courses_bus.sort_values(
        by=["DepartureSeconds", "ArrivalSeconds", "TripID"],
    ).reset_index(drop=True)

    premiere_course = courses_bus.iloc[0]
    derniere_course = courses_bus.iloc[-1]
    duree_hlp_s = 0.0
    if configuration_gtfs.include_depot_deadhead:
        duree_hlp_s = (
            configuration_gtfs.depot_deadhead_distance_m
            / configuration_gtfs.depot_deadhead_speed_m_s
        )

    debut_absolu_s = float(premiere_course["DepartureSeconds"]) - duree_hlp_s
    lignes: list[dict[str, Any]] = [
        _ligne_inactive(
            bus_index=bus_index,
            trip_id=f"BUS_{bus_index}_START",
            nom_arret=configuration_gtfs.depot_name,
            duree_s=0.0,
            phase="INITIAL",
        )
    ]

    if configuration_gtfs.include_depot_deadhead:
        lignes.append(
            _ligne_haut_le_pied(
                bus_index=bus_index,
                trip_id="DEPOT_OUT",
                depart=configuration_gtfs.depot_name,
                arrivee=str(premiere_course["StartStopName"]),
                distance_m=configuration_gtfs.depot_deadhead_distance_m,
                vitesse_m_s=configuration_gtfs.depot_deadhead_speed_m_s,
                phase="DEPOT_OUT",
            )
        )

    arrivee_precedente_s: float | None = None
    arret_precedent = str(premiere_course["StartStopName"])

    for course in courses_bus.to_dict("records"):
        depart_course_s = float(course["DepartureSeconds"])
        arrivee_course_s = float(course["ArrivalSeconds"])
        course_index = int(course["CourseIndex"])

        if arrivee_precedente_s is not None:
            attente_s = depart_course_s - arrivee_precedente_s
            if attente_s < -1e-6:
                raise ValueError(
                    "Courses incompatibles pour le bus "
                    f"{bus_index} : la course {course_index} demarre avant "
                    "la fin de la course precedente."
                )
            if attente_s > 0:
                lignes.append(
                    _ligne_inactive(
                        bus_index=bus_index,
                        trip_id="ATTENTE_INTER_COURSES",
                        nom_arret=arret_precedent,
                        duree_s=attente_s,
                        phase="ATTENTE",
                        course_index=course_index,
                    )
                )

        segments_course = segments_courses[
            segments_courses["CourseIndex"] == course_index
        ].sort_values("SegmentIndex")
        if segments_course.empty:
            raise ValueError(
                f"Aucun segment detaille n'a ete trouve pour la course {course_index}."
            )

        duree_segments_s = 0.0
        for segment in segments_course.to_dict("records"):
            ligne_segment = _preparer_segment_service(segment, bus_index)
            duree_segments_s += float(ligne_segment["deltaT"])
            lignes.append(ligne_segment)

        duree_course_s = float(course["Duration_s"])
        duree_arrets_s = duree_course_s - duree_segments_s
        if duree_arrets_s < -1e-6:
            raise ValueError(
                "Incoherence temporelle GTFS pour la course "
                f"{course_index} : les segments depassent la duree annoncee."
            )
        if duree_arrets_s > 0:
            lignes.append(
                _ligne_inactive(
                    bus_index=bus_index,
                    trip_id="ARRETS_COURSE",
                    nom_arret=str(course["EndStopName"]),
                    duree_s=duree_arrets_s,
                    phase="ARRETS_COURSE",
                    course_index=course_index,
                )
            )

        arrivee_precedente_s = arrivee_course_s
        arret_precedent = str(course["EndStopName"])

    if configuration_gtfs.include_depot_deadhead:
        lignes.append(
            _ligne_haut_le_pied(
                bus_index=bus_index,
                trip_id="DEPOT_IN",
                depart=str(derniere_course["EndStopName"]),
                arrivee=configuration_gtfs.depot_name,
                distance_m=configuration_gtfs.depot_deadhead_distance_m,
                vitesse_m_s=configuration_gtfs.depot_deadhead_speed_m_s,
                phase="DEPOT_IN",
            )
        )

    parcours = pd.DataFrame(lignes)
    parcours["PointID"] = range(len(parcours))
    parcours["Time"] = parcours["deltaT"].cumsum()
    parcours["Total_Distance"] = parcours["Distance"].cumsum()
    debut_horaire = pd.Timestamp(configuration_gtfs.service_date) + pd.to_timedelta(
        debut_absolu_s,
        unit="s",
    )
    parcours["TimeHour"] = debut_horaire + pd.to_timedelta(
        parcours["Time"],
        unit="s",
    )
    return parcours


def _construire_resume_bus(
    *,
    bus_index: int,
    parcours: pd.DataFrame,
    courses_bus: pd.DataFrame,
    configuration_simulation: ConfigurationSimulation,
    capacite_batterie_kwh: float,
) -> dict[str, Any]:
    energie_kwh = float((parcours["Power"] * parcours["deltaT"]).sum() / 3.6e6)
    distance_km = float(parcours["Distance"].sum() / 1000.0)
    soc_min = float(parcours["SoC"].min())
    soc_final = float(parcours["SoC"].iloc[-1])
    seuil_alerte = configuration_simulation.alertes_batterie.seuil_alerte_soc_pct
    seuil_echec = configuration_simulation.alertes_batterie.seuil_echec_soc_pct
    energie_restante_finale = soc_final / 100.0 * capacite_batterie_kwh
    marge_min_soc = soc_min - seuil_alerte
    amplitude_h = float(
        max(
            (
                courses_bus["ArrivalTime"].max()
                - courses_bus["DepartureTime"].min()
            ).total_seconds(),
            0.0,
        )
        / 3600.0
    )
    attente_s = float(
        parcours.loc[
            parcours["Phase"].isin(("ATTENTE", "ARRETS_COURSE")),
            "deltaT",
        ].sum()
    )
    message_alerte = construire_message_alerte_batterie(
        tabl=parcours,
        configuration_alertes=configuration_simulation.alertes_batterie,
    )
    statut = "OK"
    if soc_min <= seuil_echec:
        statut = "ECHEC"
    elif soc_min <= seuil_alerte:
        statut = "ALERTE"
    return {
        "BusIndex": bus_index,
        "NbCourses": int(len(courses_bus)),
        "PremierDepart": courses_bus["DepartureTime"].min(),
        "DerniereArrivee": courses_bus["ArrivalTime"].max(),
        "DistanceTotale_km": distance_km,
        "Energie_kWh": energie_kwh,
        "SoCFinal_pct": soc_final,
        "SoCMin_pct": soc_min,
        "EnergieRestanteFinale_kWh": energie_restante_finale,
        "MargeMinSoc_pct": marge_min_soc,
        "Amplitude_h": amplitude_h,
        "Attente_s": attente_s,
        "StatutViabilite": statut,
        "Alerte": message_alerte or "",
    }


def _priorite_statut(statut: str) -> int:
    priorites = {"OK": 0, "ALERTE": 1, "ECHEC": 2}
    return priorites.get(str(statut), 0)


def _nom_fichier_sur(valeur: object, valeur_defaut: str = "simulation") -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or valeur_defaut))
    texte = texte.encode("ascii", "ignore").decode("ascii")
    caracteres = [caractere if caractere.isalnum() else "_" for caractere in texte.strip().lower()]
    nom = "_".join("".join(caracteres).split("_"))
    return nom or valeur_defaut


def construire_resume_global_flotte(resultat: ResultatSimulationFlotte) -> dict[str, Any]:
    """Construit les indicateurs principaux de viabilite de la flotte."""
    resume = resultat.resume_energie_bus
    if resume.empty:
        return {
            "StatutGlobal": "ECHEC",
            "NbBus": 0,
            "NbCourses": 0,
            "DistanceTotale_km": 0.0,
            "EnergieTotale_kWh": 0.0,
            "SoCMinFlotte_pct": float("nan"),
            "BusCritique": None,
            "MargeMinSoc_pct": float("nan"),
            "EnergieMoyenneBus_kWh": 0.0,
            "DistanceMoyenneBus_km": 0.0,
        }

    statut_global = max(
        (str(statut) for statut in resume["StatutViabilite"].tolist()),
        key=_priorite_statut,
    )
    index_critique = resume["SoCMin_pct"].astype(float).idxmin()
    bus_critique = int(resume.loc[index_critique, "BusIndex"])
    nb_bus = int(len(resume))
    nb_courses = int(resume["NbCourses"].sum())
    distance_totale = float(resume["DistanceTotale_km"].sum())
    energie_totale = float(resume["Energie_kWh"].sum())

    return {
        "StatutGlobal": statut_global,
        "NbBus": nb_bus,
        "NbCourses": nb_courses,
        "DistanceTotale_km": distance_totale,
        "EnergieTotale_kWh": energie_totale,
        "SoCMinFlotte_pct": float(resume["SoCMin_pct"].min()),
        "BusCritique": bus_critique,
        "MargeMinSoc_pct": float(resume["MargeMinSoc_pct"].min()),
        "EnergieMoyenneBus_kWh": energie_totale / nb_bus if nb_bus else 0.0,
        "DistanceMoyenneBus_km": distance_totale / nb_bus if nb_bus else 0.0,
    }


def construire_dossier_sortie_flotte(
    resultat: ResultatSimulationFlotte,
    dossier_base: Path | None = None,
) -> Path:
    configuration = resultat.configuration_simulation
    gtfs = configuration.gtfs
    base = dossier_base or Path(__file__).resolve().parent / "outputs" / "flotte"
    scenario = _nom_fichier_sur(f"scenario_{configuration.recharge.scenario}")
    modele = _nom_fichier_sur(resultat.modele_bus.model_id)
    ligne = _nom_fichier_sur(gtfs.line_selector or gtfs.route_id or gtfs.network_name or "ligne")
    date_service = _nom_fichier_sur(gtfs.service_date or "date_service")
    return base / scenario / modele / f"{date_service}_{ligne}"


def exporter_resultats_flotte(
    resultat: ResultatSimulationFlotte,
    dossier_sortie: Path | None = None,
) -> dict[str, Path]:
    """Exporte les resultats flotte dans des fichiers faciles a relire."""
    dossier = dossier_sortie or construire_dossier_sortie_flotte(resultat)
    dossier.mkdir(parents=True, exist_ok=True)

    chemins = {
        "resume_global": dossier / "resume_global.csv",
        "resume_bus": dossier / "resume_bus.csv",
        "courses_affectees": dossier / "courses_affectees.csv",
        "profils_bus": dossier / "profils_bus.csv",
        "resume_texte": dossier / "resume.txt",
    }
    pd.DataFrame([construire_resume_global_flotte(resultat)]).to_csv(
        chemins["resume_global"],
        index=False,
        encoding="utf-8-sig",
    )
    resultat.resume_energie_bus.to_csv(chemins["resume_bus"], index=False, encoding="utf-8-sig")
    resultat.resultat_affectation.courses_affectees.to_csv(
        chemins["courses_affectees"],
        index=False,
        encoding="utf-8-sig",
    )

    profils = [profil.copy() for profil in resultat.profils_bus.values() if not profil.empty]
    if profils:
        pd.concat(profils, ignore_index=True).to_csv(
            chemins["profils_bus"],
            index=False,
            encoding="utf-8-sig",
        )
    else:
        pd.DataFrame().to_csv(chemins["profils_bus"], index=False, encoding="utf-8-sig")

    chemins_resume = {nom: chemin for nom, chemin in chemins.items() if nom != "resume_texte"}
    chemins["resume_texte"].write_text(
        "\n".join(construire_lignes_resume_simulation_flotte(resultat, chemins_exports=chemins_resume)) + "\n",
        encoding="utf-8",
    )
    return chemins


def executer_simulation_flotte(
    *,
    configuration_simulation: ConfigurationSimulation,
    temps_battement_s: float,
) -> ResultatSimulationFlotte:
    """
    Execute une premiere simulation energetique flotte bus par bus.
    """

    modele_bus = get_bus_model(configuration_simulation.id_modele_bus)
    courses, segments, metadonnees_service = (
        charger_courses_et_segments_reels_journaliers(configuration_simulation.gtfs)
    )
    resultat_affectation = affecter_courses_aux_bus(
        courses=courses,
        temps_battement_s=temps_battement_s,
    )

    profils_bus: dict[int, pd.DataFrame] = {}
    lignes_resume: list[dict[str, Any]] = []
    capacite_batterie_kwh = modele_bus.battery_capacity_kwh

    configuration_recharge_sans_borne = replace(
        configuration_simulation.recharge,
        scenario=1,
    )

    for bus_index, courses_bus in resultat_affectation.courses_affectees.groupby(
        "BusIndex",
        sort=True,
    ):
        bus_index_int = int(bus_index)
        parcours = construire_parcours_bus(
            bus_index=bus_index_int,
            courses_bus=courses_bus,
            segments_courses=segments,
            configuration_simulation=configuration_simulation,
        )
        parcours = calculer_puissance_parcours(
            tabl=parcours,
            configuration_recharge=configuration_recharge_sans_borne,
            bus_model=modele_bus,
        )
        parcours, capacite_batterie_kwh = calculer_soc_parcours(
            tabl=parcours,
            bus_model=modele_bus,
        )
        profils_bus[bus_index_int] = parcours
        lignes_resume.append(
            _construire_resume_bus(
                bus_index=bus_index_int,
                parcours=parcours,
                courses_bus=courses_bus,
                configuration_simulation=configuration_simulation,
                capacite_batterie_kwh=capacite_batterie_kwh,
            )
        )

    resume_energie_bus = pd.DataFrame(lignes_resume).sort_values(
        "BusIndex",
    ).reset_index(drop=True)

    return ResultatSimulationFlotte(
        configuration_simulation=configuration_simulation,
        modele_bus=modele_bus,
        metadonnees_service=metadonnees_service,
        resultat_affectation=resultat_affectation,
        resume_energie_bus=resume_energie_bus,
        profils_bus=profils_bus,
        capacite_batterie_kwh=capacite_batterie_kwh,
    )


def construire_lignes_resume_simulation_flotte(
    resultat: ResultatSimulationFlotte,
    chemins_exports: dict[str, Path] | None = None,
) -> list[str]:
    """
    Formate le resume de la simulation flotte pour le CLI et l'interface.
    """

    metadonnees = resultat.metadonnees_service
    affectation = resultat.resultat_affectation
    resume = resultat.resume_energie_bus
    resume_global = construire_resume_global_flotte(resultat)
    nom_ligne = (
        metadonnees.get("route_long_name")
        or metadonnees.get("route_short_name")
        or metadonnees.get("route_id")
        or ""
    )

    lignes = [
        "Simulation flotte bus par bus",
        f"Statut global : {resume_global['StatutGlobal']}",
        f"Service date  : {metadonnees.get('service_date', '')}",
        f"Ligne         : {nom_ligne}",
        f"Direction     : {metadonnees.get('direction_id', '') or 'toutes'}",
        f"Modele bus    : {resultat.modele_bus.display_name}",
        f"Nb courses    : {metadonnees.get('trip_count', 0)}",
        f"Nb bus mini   : {affectation.nombre_bus_necessaires}",
        f"Battement     : {affectation.temps_battement_s:.0f} s",
        f"Distance tot. : {resume_global['DistanceTotale_km']:.1f} km",
        f"Energie tot.  : {resume_global['EnergieTotale_kWh']:.1f} kWh",
        f"SoC min flotte: {resume_global['SoCMinFlotte_pct']:.2f} %",
        f"Bus critique  : bus {resume_global['BusCritique']}",
        f"Marge min SoC : {resume_global['MargeMinSoc_pct']:.2f} points",
        (
            "Hypotheses    : pas encore de recharge en journee ni conflits de "
            "bornes, pas de haut-le-pied reel entre courses, attente avec "
            "auxiliaires actifs."
        ),
    ]

    for _, ligne_bus in resume.iterrows():
        lignes.append(
            "Bus {bus} [{statut}] : {courses} courses, {distance:.1f} km, "
            "{energie:.1f} kWh, SoC final {soc_final:.1f} %, "
            "SoC min {soc_min:.1f} %, marge {marge:.1f} pts".format(
                bus=int(ligne_bus["BusIndex"]),
                statut=str(ligne_bus["StatutViabilite"]),
                courses=int(ligne_bus["NbCourses"]),
                distance=float(ligne_bus["DistanceTotale_km"]),
                energie=float(ligne_bus["Energie_kWh"]),
                soc_final=float(ligne_bus["SoCFinal_pct"]),
                soc_min=float(ligne_bus["SoCMin_pct"]),
                marge=float(ligne_bus["MargeMinSoc_pct"]),
            )
        )

    alertes = [
        str(alerte)
        for alerte in resume["Alerte"].tolist()
        if str(alerte).strip()
    ]
    if alertes:
        lignes.append("")
        lignes.append("Alertes batterie :")
        lignes.extend(alertes)

    if chemins_exports:
        lignes.append("")
        lignes.append("Exports generes :")
        for nom, chemin in chemins_exports.items():
            lignes.append(f"- {nom}: {chemin}")

    return lignes
