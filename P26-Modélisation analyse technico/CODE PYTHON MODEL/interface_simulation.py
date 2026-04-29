from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from bus_models import list_bus_models
from configuration_simulation import (
    SCENARIOS_DISPONIBLES,
    construire_configuration_depuis_arguments,
    construire_configuration_simulation_par_defaut,
)
from flotte_exploitation import (
    affecter_courses_aux_bus,
    construire_lignes_resume_flotte,
)
from gtfs_data import charger_courses_reelles_journalieres
from service_simulation import (
    ResultatSimulation,
    construire_lignes_resume_simulation,
    executer_simulation,
)

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None
    ttk = None
    filedialog = None
    messagebox = None


CONFIGURATION_PAR_DEFAUT = construire_configuration_simulation_par_defaut()
MODELES_BUS = {modele.model_id: modele for modele in list_bus_models()}


class InterfaceSimulationP26:
    """
    Petite interface Tkinter pour lancer rapidement une simulation.
    """

    def __init__(self) -> None:
        if tk is None or ttk is None or filedialog is None or messagebox is None:
            raise RuntimeError(
                "Tkinter n'est pas disponible sur cet interpreteur Python."
            )

        self.racine = tk.Tk()
        self.racine.title("Simulateur P26 - Modelisation technico")
        self.racine.geometry("1180x760")
        self.racine.minsize(1040, 660)
        self.racine.configure(bg="#f4f1ea")

        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.resultat_simulation: ResultatSimulation | None = None
        self.dossier_sortie_courant: Path | None = None

        self.var_mode_execution = tk.StringVar(value="simulation")
        self.var_mode_donnees = tk.StringVar(
            value=CONFIGURATION_PAR_DEFAUT.gtfs.data_mode
        )
        self.var_gtfs_path = tk.StringVar(value="")
        self.var_reseau = tk.StringVar(
            value=CONFIGURATION_PAR_DEFAUT.gtfs.network_name
        )
        self.var_ligne = tk.StringVar(
            value=CONFIGURATION_PAR_DEFAUT.gtfs.line_selector or ""
        )
        self.var_direction = tk.StringVar(
            value=""
            if CONFIGURATION_PAR_DEFAUT.gtfs.direction_id is None
            else str(CONFIGURATION_PAR_DEFAUT.gtfs.direction_id)
        )
        self.var_date_service = tk.StringVar(
            value=CONFIGURATION_PAR_DEFAUT.gtfs.service_date
        )
        self.var_cycles = tk.StringVar(
            value=str(CONFIGURATION_PAR_DEFAUT.gtfs.cycle_count)
        )
        self.var_duree_arret = tk.StringVar(
            value=str(CONFIGURATION_PAR_DEFAUT.gtfs.default_stop_duration_s)
        )
        self.var_scenario = tk.StringVar(
            value=str(CONFIGURATION_PAR_DEFAUT.recharge.scenario)
        )
        self.var_modele_bus = tk.StringVar(
            value=CONFIGURATION_PAR_DEFAUT.id_modele_bus
        )
        self.var_nombre_bus = tk.StringVar(
            value=str(CONFIGURATION_PAR_DEFAUT.flotte.nombre_bus)
        )
        self.var_temps_battement = tk.StringVar(value="300")
        self.var_nom_depot = tk.StringVar(
            value=CONFIGURATION_PAR_DEFAUT.gtfs.depot_name
        )
        self.var_distance_depot = tk.StringVar(
            value=str(CONFIGURATION_PAR_DEFAUT.gtfs.depot_deadhead_distance_m)
        )
        self.var_vitesse_depot = tk.StringVar(
            value=str(CONFIGURATION_PAR_DEFAUT.gtfs.depot_deadhead_speed_m_s)
        )
        self.var_puissance_borne_depot = tk.StringVar(
            value=str(CONFIGURATION_PAR_DEFAUT.recharge.puissance_borne_depot_kw)
        )
        self.var_puissance_borne_terminus = tk.StringVar(
            value=str(CONFIGURATION_PAR_DEFAUT.recharge.puissance_borne_terminus_kw)
        )
        self.var_puissance_borne_intermediaire = tk.StringVar(
            value=str(
                CONFIGURATION_PAR_DEFAUT.recharge.puissance_borne_intermediaire_kw
            )
        )
        self.var_seuil_alerte = tk.StringVar(
            value=str(
                CONFIGURATION_PAR_DEFAUT.alertes_batterie.seuil_alerte_soc_pct
            )
        )
        self.var_seuil_echec = tk.StringVar(
            value=str(
                CONFIGURATION_PAR_DEFAUT.alertes_batterie.seuil_echec_soc_pct
            )
        )
        self.var_haut_le_pied_actif = tk.BooleanVar(
            value=CONFIGURATION_PAR_DEFAUT.gtfs.include_depot_deadhead
        )
        self.var_afficher_graphiques = tk.BooleanVar(value=True)
        self.var_smart_charging = tk.BooleanVar(
            value=CONFIGURATION_PAR_DEFAUT.recharge.smart_charging
        )
        self.var_resume_modele = tk.StringVar(value="")
        self.var_resume_mode_execution = tk.StringVar(value="")

        self._construire_interface()
        self._mettre_a_jour_resume_mode_execution()
        self._mettre_a_jour_resume_modele()
        self._mettre_a_jour_etat_gtfs_local()

    def _construire_interface(self) -> None:
        bandeau = tk.Frame(self.racine, bg="#17324d", padx=18, pady=16)
        bandeau.pack(fill="x")

        titre = tk.Label(
            bandeau,
            text="Simulateur energetique P26",
            font=("Segoe UI", 18, "bold"),
            fg="white",
            bg="#17324d",
        )
        titre.pack(anchor="w")

        sous_titre = tk.Label(
            bandeau,
            text=(
                "Parametrage par onglets pour garder tous les champs accessibles "
                "sans defilement complexe."
            ),
            font=("Segoe UI", 10),
            fg="#d7e6f6",
            bg="#17324d",
        )
        sous_titre.pack(anchor="w", pady=(6, 0))

        corps = tk.Frame(self.racine, bg="#f4f1ea", padx=14, pady=14)
        corps.pack(fill="both", expand=True)
        corps.grid_columnconfigure(0, weight=0)
        corps.grid_columnconfigure(1, weight=1)
        corps.grid_rowconfigure(0, weight=1)

        colonne_formulaire = tk.Frame(corps, bg="#f4f1ea", width=470)
        colonne_formulaire.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        colonne_formulaire.grid_propagate(False)

        colonne_resultats = tk.Frame(corps, bg="#f4f1ea")
        colonne_resultats.grid(row=0, column=1, sticky="nsew")
        colonne_resultats.grid_rowconfigure(1, weight=1)
        colonne_resultats.grid_columnconfigure(0, weight=1)

        self._construire_formulaire(colonne_formulaire)
        self._construire_zone_resultats(colonne_resultats)

    def _creer_carte(self, parent: Any, titre: str) -> tk.LabelFrame:
        cadre = tk.LabelFrame(
            parent,
            text=titre,
            bg="white",
            fg="#17324d",
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=10,
            bd=1,
            relief="groove",
        )
        cadre.pack(fill="x", pady=(0, 10))
        return cadre

    def _ajouter_ligne(
        self,
        parent: Any,
        ligne: int,
        etiquette: str,
        widget: Any,
        aide: str | None = None,
    ) -> None:
        label = tk.Label(
            parent,
            text=etiquette,
            bg="white",
            fg="#1f2933",
            font=("Segoe UI", 9, "bold"),
        )
        label.grid(row=ligne, column=0, sticky="w", padx=(0, 10), pady=4)
        widget.grid(row=ligne, column=1, sticky="ew", pady=4)
        if aide:
            aide_label = tk.Label(
                parent,
                text=aide,
                bg="white",
                fg="#617182",
                font=("Segoe UI", 8),
            )
            aide_label.grid(row=ligne + 1, column=1, sticky="w", pady=(0, 4))

    def _creer_onglet(self, notebook: Any, titre: str) -> tk.Frame:
        onglet = tk.Frame(notebook, bg="#f4f1ea", padx=6, pady=8)
        notebook.add(onglet, text=titre)
        return onglet

    def _construire_formulaire(self, parent: Any) -> None:
        zone_actions = tk.Frame(parent, bg="#f4f1ea")
        zone_actions.pack(side="bottom", fill="x")

        rappel_navigation = tk.Label(
            zone_actions,
            text=(
                "Passe d'un onglet a l'autre puis clique sur "
                "'Lancer la simulation'."
            ),
            bg="#f4f1ea",
            fg="#617182",
            font=("Segoe UI", 9),
            anchor="w",
        )
        rappel_navigation.pack(fill="x", pady=(0, 8))

        self.bouton_lancer = tk.Button(
            zone_actions,
            text="Lancer la simulation",
            bg="#b74d1f",
            fg="white",
            activebackground="#944016",
            activeforeground="white",
            relief="flat",
            padx=18,
            pady=10,
            font=("Segoe UI", 10, "bold"),
            command=self.lancer_simulation,
        )
        self.bouton_lancer.pack(fill="x")

        notebook = ttk.Notebook(parent)
        notebook.pack(side="top", fill="both", expand=True, pady=(0, 10))
        try:
            notebook.enable_traversal()
        except tk.TclError:
            pass

        onglet_service = self._creer_onglet(notebook, "Service")
        onglet_bus = self._creer_onglet(notebook, "Bus")
        onglet_recharge = self._creer_onglet(notebook, "Recharge")
        onglet_depot = self._creer_onglet(notebook, "Depot")

        carte_service = self._creer_carte(onglet_service, "Service GTFS")
        carte_service.grid_columnconfigure(1, weight=1)

        ligne_mode_execution = tk.Frame(carte_service, bg="white")
        bouton_mode_simulation = ttk.Radiobutton(
            ligne_mode_execution,
            text="Simulation energetique",
            value="simulation",
            variable=self.var_mode_execution,
            command=self._mettre_a_jour_resume_mode_execution,
        )
        bouton_mode_simulation.pack(anchor="w")
        bouton_mode_flotte = ttk.Radiobutton(
            ligne_mode_execution,
            text="Apercu flotte GTFS reel",
            value="apercu_flotte",
            variable=self.var_mode_execution,
            command=self._mettre_a_jour_resume_mode_execution,
        )
        bouton_mode_flotte.pack(anchor="w", pady=(4, 0))
        self._ajouter_ligne(
            carte_service,
            0,
            "Mode d'execution",
            ligne_mode_execution,
            aide=(
                "La simulation energetique suit le flux historique a 1 bus. "
                "L'apercu flotte calcule le nombre minimal de bus a partir "
                "des departs reels du GTFS."
            ),
        )

        resume_mode = tk.Label(
            carte_service,
            textvariable=self.var_resume_mode_execution,
            justify="left",
            anchor="w",
            bg="white",
            fg="#455468",
            font=("Segoe UI", 8),
        )
        resume_mode.grid(row=2, column=1, sticky="w", pady=(0, 6))

        combo_mode = ttk.Combobox(
            carte_service,
            textvariable=self.var_mode_donnees,
            values=("online", "local"),
            state="readonly",
            width=24,
        )
        combo_mode.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._mettre_a_jour_etat_gtfs_local(),
        )
        self._ajouter_ligne(carte_service, 3, "Mode de donnees", combo_mode)

        ligne_path = tk.Frame(carte_service, bg="white")
        ligne_path.grid_columnconfigure(0, weight=1)
        entree_path = ttk.Entry(ligne_path, textvariable=self.var_gtfs_path)
        entree_path.grid(row=0, column=0, sticky="ew")
        bouton_path = ttk.Button(
            ligne_path,
            text="Parcourir",
            command=self.parcourir_dossier_gtfs,
            width=12,
        )
        bouton_path.grid(row=0, column=1, padx=(8, 0))
        self.entree_gtfs_path = entree_path
        self.bouton_gtfs_path = bouton_path
        self._ajouter_ligne(
            carte_service,
            5,
            "Dossier GTFS local",
            ligne_path,
            aide="Optionnel en mode local. Laisse vide pour la recherche par defaut.",
        )

        self._ajouter_ligne(
            carte_service,
            7,
            "Reseau GTFS",
            ttk.Entry(carte_service, textvariable=self.var_reseau, width=28),
        )
        self._ajouter_ligne(
            carte_service,
            8,
            "Ligne",
            ttk.Entry(carte_service, textvariable=self.var_ligne, width=28),
        )
        self._ajouter_ligne(
            carte_service,
            9,
            "Direction",
            ttk.Entry(carte_service, textvariable=self.var_direction, width=28),
            aide=(
                "Laisse vide pour prendre un trajet representatif en simulation, "
                "ou toutes les directions en apercu flotte."
            ),
        )
        self._ajouter_ligne(
            carte_service,
            11,
            "Date de service",
            ttk.Entry(carte_service, textvariable=self.var_date_service, width=28),
            aide="Format attendu : AAAA-MM-JJ",
        )
        self._ajouter_ligne(
            carte_service,
            13,
            "Cycles",
            ttk.Entry(carte_service, textvariable=self.var_cycles, width=28),
            aide="Utilise seulement par la simulation energetique historique.",
        )
        self._ajouter_ligne(
            carte_service,
            15,
            "Duree d'arret (s)",
            ttk.Entry(carte_service, textvariable=self.var_duree_arret, width=28),
            aide="Utilisee seulement par la simulation energetique historique.",
        )

        carte_bus = self._creer_carte(onglet_bus, "Bus et flotte")
        carte_bus.grid_columnconfigure(1, weight=1)

        combo_modele = ttk.Combobox(
            carte_bus,
            textvariable=self.var_modele_bus,
            values=tuple(MODELES_BUS.keys()),
            state="readonly",
            width=32,
        )
        combo_modele.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._mettre_a_jour_resume_modele(),
        )
        self._ajouter_ligne(carte_bus, 0, "Modele bus", combo_modele)

        resume_modele = tk.Label(
            carte_bus,
            textvariable=self.var_resume_modele,
            justify="left",
            anchor="w",
            bg="white",
            fg="#455468",
            font=("Consolas", 9),
        )
        resume_modele.grid(row=1, column=1, sticky="w", pady=(0, 6))

        self._ajouter_ligne(
            carte_bus,
            2,
            "Nombre de bus",
            ttk.Entry(carte_bus, textvariable=self.var_nombre_bus, width=32),
            aide=(
                "Champ prepare pour la future simulation multi-bus. "
                "Ignore dans l'apercu flotte, ou le nombre est calcule."
            ),
        )
        self._ajouter_ligne(
            carte_bus,
            4,
            "Battement flotte (s)",
            ttk.Entry(carte_bus, textvariable=self.var_temps_battement, width=32),
            aide=(
                "Temps minimal entre deux courses d'un meme bus. "
                "Utilise par l'apercu flotte GTFS reel."
            ),
        )

        carte_recharge = self._creer_carte(onglet_recharge, "Recharge et securite")
        carte_recharge.grid_columnconfigure(1, weight=1)

        combo_scenario = ttk.Combobox(
            carte_recharge,
            textvariable=self.var_scenario,
            values=tuple(str(valeur) for valeur in SCENARIOS_DISPONIBLES),
            state="readonly",
            width=20,
        )
        self._ajouter_ligne(carte_recharge, 0, "Scenario", combo_scenario)
        self._ajouter_ligne(
            carte_recharge,
            1,
            "Borne depot (kW)",
            ttk.Entry(
                carte_recharge,
                textvariable=self.var_puissance_borne_depot,
                width=22,
            ),
        )
        self._ajouter_ligne(
            carte_recharge,
            2,
            "Borne terminus (kW)",
            ttk.Entry(
                carte_recharge,
                textvariable=self.var_puissance_borne_terminus,
                width=22,
            ),
        )
        self._ajouter_ligne(
            carte_recharge,
            3,
            "Borne intermediaire (kW)",
            ttk.Entry(
                carte_recharge,
                textvariable=self.var_puissance_borne_intermediaire,
                width=22,
            ),
        )
        self._ajouter_ligne(
            carte_recharge,
            4,
            "Optimiser charge",
            ttk.Checkbutton(
                carte_recharge,
                variable=self.var_smart_charging,
            ),
            aide=(
                "Si actif, la puissance depot est ajustee au besoin reel. "
                "Sinon, la borne depot charge a sa puissance maximale."
            ),
        )
        self._ajouter_ligne(
            carte_recharge,
            6,
            "Seuil alerte SoC (%)",
            ttk.Entry(carte_recharge, textvariable=self.var_seuil_alerte, width=22),
        )
        self._ajouter_ligne(
            carte_recharge,
            7,
            "Seuil echec SoC (%)",
            ttk.Entry(carte_recharge, textvariable=self.var_seuil_echec, width=22),
        )

        carte_depot = self._creer_carte(onglet_depot, "Depot et options")
        carte_depot.grid_columnconfigure(1, weight=1)

        self._ajouter_ligne(
            carte_depot,
            0,
            "Nom depot",
            ttk.Entry(carte_depot, textvariable=self.var_nom_depot, width=28),
        )
        self._ajouter_ligne(
            carte_depot,
            1,
            "Distance depot (m)",
            ttk.Entry(carte_depot, textvariable=self.var_distance_depot, width=28),
        )
        self._ajouter_ligne(
            carte_depot,
            2,
            "Vitesse depot (m/s)",
            ttk.Entry(carte_depot, textvariable=self.var_vitesse_depot, width=28),
        )

        ligne_cases = tk.Frame(carte_depot, bg="white")
        ligne_cases.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        case_hlp = ttk.Checkbutton(
            ligne_cases,
            text="Activer les trajets depot",
            variable=self.var_haut_le_pied_actif,
        )
        case_hlp.pack(anchor="w")

        case_graphes = ttk.Checkbutton(
            ligne_cases,
            text="Afficher les graphes a la fin du calcul",
            variable=self.var_afficher_graphiques,
        )
        case_graphes.pack(anchor="w", pady=(4, 0))

    def _construire_zone_resultats(self, parent: Any) -> None:
        entete = tk.Frame(parent, bg="#f4f1ea")
        entete.grid(row=0, column=0, sticky="ew")
        entete.grid_columnconfigure(0, weight=1)

        titre = tk.Label(
            entete,
            text="Journal de simulation",
            font=("Segoe UI", 12, "bold"),
            bg="#f4f1ea",
            fg="#17324d",
        )
        titre.grid(row=0, column=0, sticky="w")

        actions = tk.Frame(entete, bg="#f4f1ea")
        actions.grid(row=0, column=1, sticky="e")

        bouton_ouvrir = ttk.Button(
            actions,
            text="Ouvrir sorties",
            command=self.ouvrir_dossier_sortie,
        )
        bouton_ouvrir.pack(side="left")

        bouton_quitter = ttk.Button(
            actions,
            text="Quitter",
            command=self.racine.destroy,
        )
        bouton_quitter.pack(side="left", padx=(8, 0))

        cadre_texte = tk.Frame(parent, bg="white", bd=1, relief="groove")
        cadre_texte.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        cadre_texte.grid_rowconfigure(0, weight=1)
        cadre_texte.grid_columnconfigure(0, weight=1)

        self.zone_texte = tk.Text(
            cadre_texte,
            wrap="word",
            bg="white",
            fg="#1f2933",
            font=("Consolas", 10),
            padx=12,
            pady=12,
        )
        self.zone_texte.grid(row=0, column=0, sticky="nsew")

        barre = ttk.Scrollbar(
            cadre_texte,
            orient="vertical",
            command=self.zone_texte.yview,
        )
        barre.grid(row=0, column=1, sticky="ns")
        self.zone_texte.configure(yscrollcommand=barre.set)

        self._ecrire_journal(
            "Interface prete.\n\n"
            "Choisis d'abord un mode : simulation energetique ou apercu flotte.\n"
            "Les graphes ne sont generes que par la simulation energetique.\n"
        )

    def _mettre_a_jour_resume_mode_execution(self) -> None:
        mode_execution = self.var_mode_execution.get()
        if mode_execution == "apercu_flotte":
            self.var_resume_mode_execution.set(
                "Apercu flotte : service reel du jour, tri des courses par heure,\n"
                "puis affectation simple a une flotte minimale avec battement fixe."
            )
            self.bouton_lancer.configure(text="Lancer l'apercu flotte")
        else:
            self.var_resume_mode_execution.set(
                "Simulation energetique : flux historique du projet sur un bus,\n"
                "avec cycles, recharge et generation des graphes."
            )
            self.bouton_lancer.configure(text="Lancer la simulation")

    def _mettre_a_jour_resume_modele(self) -> None:
        modele = MODELES_BUS[self.var_modele_bus.get()]
        self.var_resume_modele.set(
            "Constructeur : {constructeur}\n"
            "Masse ref   : {masse:.0f} kg\n"
            "Batterie    : {batterie:.0f} kWh\n"
            "Surface AV  : {surface:.2f} m2".format(
                constructeur=modele.manufacturer,
                masse=modele.reference_mass_kg,
                batterie=modele.battery_capacity_kwh,
                surface=modele.frontal_area_m2,
            )
        )

    def _mettre_a_jour_etat_gtfs_local(self) -> None:
        mode_local = self.var_mode_donnees.get() == "local"
        nouvel_etat = "normal" if mode_local else "disabled"
        self.entree_gtfs_path.configure(state=nouvel_etat)
        self.bouton_gtfs_path.configure(state=nouvel_etat)

    def _ecrire_journal(self, texte: str, remplacer: bool = False) -> None:
        self.zone_texte.configure(state="normal")
        if remplacer:
            self.zone_texte.delete("1.0", "end")
        self.zone_texte.insert("end", texte)
        self.zone_texte.see("end")
        self.zone_texte.configure(state="disabled")

    def _lire_entier(self, valeur: str, etiquette: str) -> int:
        try:
            return int(valeur)
        except ValueError as exc:
            raise ValueError(f"{etiquette} doit etre un entier valide.") from exc

    def _lire_flottant(self, valeur: str, etiquette: str) -> float:
        try:
            return float(valeur)
        except ValueError as exc:
            raise ValueError(f"{etiquette} doit etre un nombre valide.") from exc

    def parcourir_dossier_gtfs(self) -> None:
        dossier = filedialog.askdirectory(
            title="Selectionner le dossier GTFS",
            initialdir=str(Path(__file__).resolve().parent),
        )
        if dossier:
            self.var_gtfs_path.set(dossier)

    def construire_arguments_depuis_formulaire(self) -> argparse.Namespace:
        gtfs_path = self.var_gtfs_path.get().strip() or None
        direction = self.var_direction.get().strip() or None
        mode_execution = self.var_mode_execution.get()

        arguments = argparse.Namespace(
            scenario=self._lire_entier(self.var_scenario.get(), "Le scenario"),
            smart_charging=self.var_smart_charging.get(),
            bus_model=self.var_modele_bus.get(),
            data_mode=self.var_mode_donnees.get(),
            gtfs_path=gtfs_path,
            network_name=self.var_reseau.get().strip(),
            line_selector=self.var_ligne.get().strip(),
            route_id=None,
            trip_id=None,
            direction_id=direction,
            cycle_count=self._lire_entier(
                self.var_cycles.get(),
                "Le nombre de cycles",
            ),
            default_stop_duration_s=self._lire_flottant(
                self.var_duree_arret.get(),
                "La duree d'arret",
            ),
            service_date=self.var_date_service.get().strip(),
            depot_name=self.var_nom_depot.get().strip() or None,
            distance_depot_m=self._lire_flottant(
                self.var_distance_depot.get(),
                "La distance depot",
            ),
            vitesse_depot_m_s=self._lire_flottant(
                self.var_vitesse_depot.get(),
                "La vitesse depot",
            ),
            desactiver_haut_le_pied=not self.var_haut_le_pied_actif.get(),
            nombre_bus=self._lire_entier(
                self.var_nombre_bus.get(),
                "Le nombre de bus",
            ),
            temps_battement_s=self._lire_flottant(
                self.var_temps_battement.get(),
                "Le temps de battement flotte",
            ),
            puissance_borne_depot_kw=self._lire_flottant(
                self.var_puissance_borne_depot.get(),
                "La puissance de borne depot",
            ),
            puissance_borne_terminus_kw=self._lire_flottant(
                self.var_puissance_borne_terminus.get(),
                "La puissance de borne terminus",
            ),
            puissance_borne_intermediaire_kw=self._lire_flottant(
                self.var_puissance_borne_intermediaire.get(),
                "La puissance de borne intermediaire",
            ),
            seuil_alerte_soc=self._lire_flottant(
                self.var_seuil_alerte.get(),
                "Le seuil d'alerte SoC",
            ),
            seuil_echec_soc=self._lire_flottant(
                self.var_seuil_echec.get(),
                "Le seuil d'echec SoC",
            ),
            list_bus_models=False,
            apercu_flotte=mode_execution == "apercu_flotte",
            interface=False,
            sans_graphiques=not self.var_afficher_graphiques.get(),
        )
        return arguments

    def _executer_simulation_energetique(
        self,
        arguments: argparse.Namespace,
    ) -> str:
        configuration_simulation = construire_configuration_depuis_arguments(arguments)
        self.resultat_simulation = executer_simulation(
            configuration_simulation=configuration_simulation,
            afficher_graphiques=self.var_afficher_graphiques.get(),
        )
        self.dossier_sortie_courant = self.resultat_simulation.dossier_sortie
        return "\n".join(
            construire_lignes_resume_simulation(self.resultat_simulation)
        )

    def _executer_apercu_flotte(
        self,
        arguments: argparse.Namespace,
    ) -> str:
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

        self.resultat_simulation = None
        self.dossier_sortie_courant = None
        return "\n".join(
            construire_lignes_resume_flotte(
                resultat_affectation=resultat_affectation,
                metadonnees_service=metadonnees_service,
            )
        )

    def lancer_simulation(self) -> None:
        self.bouton_lancer.configure(state="disabled")
        self.racine.configure(cursor="watch")
        mode_execution = self.var_mode_execution.get()
        texte_attente = (
            "Apercu flotte en cours...\n\n"
            if mode_execution == "apercu_flotte"
            else "Simulation en cours...\n\n"
        )
        self._ecrire_journal(texte_attente, remplacer=True)
        self.racine.update_idletasks()

        try:
            arguments = self.construire_arguments_depuis_formulaire()
            if arguments.apercu_flotte:
                resume = self._executer_apercu_flotte(arguments)
            else:
                resume = self._executer_simulation_energetique(arguments)
            self._ecrire_journal(resume + "\n", remplacer=True)
        except Exception as exc:  # noqa: BLE001
            self._ecrire_journal(f"Echec de la simulation : {exc}\n", remplacer=True)
            messagebox.showerror(
                "Simulation impossible",
                str(exc),
            )
        finally:
            self.racine.configure(cursor="")
            self.bouton_lancer.configure(state="normal")

    def ouvrir_dossier_sortie(self) -> None:
        if self.dossier_sortie_courant is None:
            messagebox.showinfo(
                "Aucun dossier",
                "Ce mode n'a pas genere de dossier de sortie ouvrable.",
            )
            return

        dossier = self.dossier_sortie_courant
        if not dossier.exists():
            messagebox.showwarning(
                "Dossier introuvable",
                f"Le dossier n'existe pas : {dossier}",
            )
            return

        if hasattr(os, "startfile"):
            os.startfile(str(dossier))  # type: ignore[attr-defined]
        else:
            messagebox.showinfo(
                "Dossier de sortie",
                str(dossier),
            )

    def run(self) -> None:
        self.racine.mainloop()


def lancer_interface_simulation() -> None:
    """
    Point d'entree public de l'interface.
    """

    application = InterfaceSimulationP26()
    application.run()


def main() -> None:
    """
    Point d'entree direct pour lancer ce module comme script.
    """

    lancer_interface_simulation()


if __name__ == "__main__":
    main()
