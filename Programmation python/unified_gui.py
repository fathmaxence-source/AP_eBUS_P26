import argparse
from pathlib import Path
from typing import Any, Dict, List

from accueil_outil_aide import (
    create_card,
    create_chip,
    create_logo_badge,
    load_home_image,
    open_method_dialog,
    open_scope_dialog,
)
from altimetry_services import describe_altimetry_source, select_local_altimetry_dataset
from analysis_runner import run_analysis
from app_models import BusParameters
from gtfs_services import (
    compute_selected_gtfs_bounds_from_feed,
    normalize_text,
    preview_trip_selection,
    select_gtfs_feed,
)
from project_paths import EXPORTS_DIR, PROJECT_ROOT, get_altimetry_search_root, get_gtfs_search_root
from reporting_services import build_default_report_name, export_analysis_report_bundle
from ui_helpers import (
    Aide_résultat,
    Aide_sélection,
    UI_PALETTE,
    bind_canvas_mousewheel,
    build_feed_label,
    build_route_labels,
    build_validation_label,
    clone_bus_parameters,
    configure_app_theme,
    create_hero_banner,
    create_metric_tile,
    create_path_strip,
    create_primary_button,
    create_secondary_button,
    create_vertical_scrollable_area,
    discover_gtfs_feeds_cached,
    discover_legacy_validation_files_cached,
    filter_labels,
    format_altimetry_preview,
    format_operation_overview,
    format_bus_parameters_summary,
    format_results_bus_parameters,
    format_results_summary,
    format_scenario_summary,
    format_stop_sequences,
    format_validation_summary,
    load_gtfs_feed_cached,
    print_results_console,
    show_bus_parameters_dialog,
)
from window_layout import apply_main_window_geometry, capture_main_window_geometry

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None
    ttk = None
    messagebox = None
    filedialog = None


class UnifiedBusApplication:
    def __init__(self, arguments: argparse.Namespace) -> None:
        if tk is None or ttk is None or messagebox is None:
            raise RuntimeError(
                "Tkinter n'est pas disponible sur cet interpréteur Python. "
                "Utilisez les arguments en ligne de commande ou installez Python avec Tk."
            )

        self.arguments = self._clone_arguments(arguments)
        self.root = tk.Tk()
        self.root.title("Accueil - Outil d'aide à la décision")
        apply_main_window_geometry(self.root)
        configure_app_theme(self.root)
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.container = tk.Frame(self.root, bg=UI_PALETTE["sand"])
        self.container.grid(row=0, column=0, sticky="nsew")
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.home_frame: Any | None = None
        self.selection_frame: Any | None = None
        self.results_frame: Any | None = None
        self.home_images: list[Any] = []
        self.selection_state: Dict[str, Any] = {}
        self.current_gtfs_data: Dict[str, Any] | None = None
        self.current_results: Dict[str, Any] | None = None
        self.current_view = "home"

        self._build_home_view()
        self.show_home()

    @staticmethod
    def _clone_arguments(arguments: argparse.Namespace) -> argparse.Namespace:
        cloned = argparse.Namespace(**vars(arguments))
        cloned.bus_parameters = clone_bus_parameters(
            getattr(arguments, "bus_parameters", BusParameters())
        )
        cloned.use_default_bus_parameters = getattr(
            arguments,
            "use_default_bus_parameters",
            True,
        )
        cloned.round_trip_count = getattr(arguments, "round_trip_count", 1)
        cloned.bus_count = getattr(arguments, "bus_count", 1)
        return cloned

    def _set_root_bindings(
        self,
        return_callback: Any | None = None,
        escape_callback: Any | None = None,
    ) -> None:
        self.root.unbind("<Return>")
        self.root.unbind("<Escape>")
        if return_callback is not None:
            self.root.bind("<Return>", lambda event: return_callback())
        if escape_callback is not None:
            self.root.bind("<Escape>", lambda event: escape_callback())

    def _show_view(
        self,
        frame: Any,
        title: str,
        view_name: str,
        return_callback: Any | None = None,
        escape_callback: Any | None = None,
        focus_widget: Any | None = None,
    ) -> None:
        self.current_view = view_name
        self.root.title(title)
        frame.tkraise()
        self._set_root_bindings(return_callback=return_callback, escape_callback=escape_callback)
        if focus_widget is not None:
            self.root.after_idle(focus_widget.focus_set)

    def close_app(self) -> None:
        capture_main_window_geometry(self.root)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()

    def show_home(self) -> None:
        if self.home_frame is None:
            self._build_home_view()
        self._show_view(
            self.home_frame,
            "Accueil - Outil d'aide à la décision",
            "home",
            return_callback=self.show_selection,
            escape_callback=self.close_app,
        )

    def show_selection(self) -> None:
        if self.selection_frame is None:
            self._build_selection_view()
        focus_widget = self.selection_state.get("focus_widget")
        confirm_callback = self.selection_state.get("confirm")
        self._show_view(
            self.selection_frame,
            "Sélection du réseau et de la ligne",
            "selection",
            return_callback=confirm_callback,
            escape_callback=self.show_home,
            focus_widget=focus_widget,
        )

    def show_results(self) -> None:
        if self.results_frame is None:
            return
        self._show_view(
            self.results_frame,
            "Résultats de l'analyse",
            "results",
            escape_callback=self.close_app,
        )

    def _create_scrollable_page(self, parent: Any) -> tuple[Any, Any, Any]:
        container = tk.Frame(parent, bg=UI_PALETTE["sand"])
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            container,
            bg=UI_PALETTE["sand"],
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        content = tk.Frame(canvas, bg=UI_PALETTE["sand"])
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scrollregion(_: Any = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_content(event: Any) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        content.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", resize_content)
        return container, content, canvas

    @staticmethod
    def _configure_readonly_text(widget: Any, height: int) -> None:
        widget.configure(
            height=height,
            wrap="word",
            bg=UI_PALETTE["white"],
            fg=UI_PALETTE["ink"],
            relief="flat",
            borderwidth=0,
            padx=2,
            pady=2,
            font=("Segoe UI", 10),
        )
        widget.configure(state="disabled")

    def _build_home_view(self) -> None:
        self.home_frame = tk.Frame(self.container, bg=UI_PALETTE["sand"])
        self.home_frame.grid(row=0, column=0, sticky="nsew")
        _, page, page_canvas = self._create_scrollable_page(self.home_frame)

        hero = tk.Frame(page, bg=UI_PALETTE["night"], padx=34, pady=28)
        hero.pack(fill="x", padx=24, pady=(24, 16))

        left_hero = tk.Frame(hero, bg=UI_PALETTE["night"])
        left_hero.pack(side="left", fill="both", expand=True)

        tk.Label(
            left_hero,
            text="Plateforme d'analyse énergétique\npour réseaux de bus électriques",
            font=("Bahnschrift SemiBold", 28),
            fg=UI_PALETTE["white"],
            bg=UI_PALETTE["night"],
            justify="left",
        ).pack(anchor="w")
        tk.Label(
            left_hero,
            text=(
                "Un point d'entrée unique pour cadrer l'étude, sélectionner une ligne, "
                "mobiliser les données GTFS et géo-altimétriques, puis produire des indicateurs "
                "directement exploitables en ingénierie de système."
            ),
            font=("Segoe UI", 11),
            fg="#d9e6f1",
            bg=UI_PALETTE["night"],
            justify="left",
            wraplength=720,
        ).pack(anchor="w", pady=(16, 0))

        create_path_strip(page, "Accueil")

        chips_row = tk.Frame(page, bg=UI_PALETTE["sand"])
        chips_row.pack(fill="x", padx=24, pady=(0, 16))
        chip_specs = [
            ("Données", "GTFS, shapes, altimétrie, validation XLSX"),
            ("Calculs", "Pente, accélération, virages, puissance, énergie"),
            ("Restitution", "Bilan trajet, segments, scénarios comparés"),
        ]
        for index, (title, value) in enumerate(chip_specs):
            chip = create_chip(chips_row, title, value)
            chip.pack(
                side="left",
                fill="x",
                expand=True,
                padx=(0, 12 if index < len(chip_specs) - 1 else 0),
            )

        body = tk.Frame(page, bg=UI_PALETTE["sand"])
        body.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        left_column = tk.Frame(body, bg=UI_PALETTE["sand"])
        left_column.pack(side="left", fill="both", expand=True)

        right_column = tk.Frame(body, bg=UI_PALETTE["sand"], width=250)
        right_column.pack(side="right", fill="y", padx=(20, 0))
        right_column.pack_propagate(False)

        tk.Label(
            left_column,
            text="Blocs fonctionnels",
            font=("Bahnschrift SemiBold", 18),
            fg=UI_PALETTE["ink"],
            bg=UI_PALETTE["sand"],
        ).pack(anchor="w", pady=(0, 10))

        cards_grid = tk.Frame(left_column, bg=UI_PALETTE["sand"])
        cards_grid.pack(fill="x")
        cards = [
            (
                "Cadrage des données",
                "Sélection du réseau, de la ligne et du mode de données. Le périmètre d'étude reste explicite.",
                UI_PALETTE["teal"],
            ),
            (
                "Reconstruction du trajet",
                "Le système reconstruit un trajet GTFS représentatif à partir des arrêts, des shapes et des distances.",
                UI_PALETTE["amber"],
            ),
            (
                "Enrichissement géographique",
                "Le relief et la géométrie du parcours alimentent les calculs de pente et les pénalités liées aux virages.",
                "#6a8caf",
            ),
            (
                "Évaluation énergétique",
                "Les sorties visent le dimensionnement : puissance, énergie, consommation spécifique et scénarios comparés.",
                "#2d6a4f",
            ),
        ]
        for index, (title, body_text, accent) in enumerate(cards):
            card = create_card(cards_grid, title, body_text, accent)
            row = index // 2
            column = index % 2
            card.grid(row=row, column=column, sticky="nsew", padx=(0, 12), pady=(0, 12))
        cards_grid.columnconfigure(0, weight=1)
        cards_grid.columnconfigure(1, weight=1)

        actions = tk.Frame(left_column, bg=UI_PALETTE["sand"])
        actions.pack(fill="x", pady=(8, 0))
        create_primary_button(actions, "Démarrer l'analyse", self.show_selection).pack(side="left")
        create_secondary_button(
            actions,
            "Méthode",
            lambda: open_method_dialog(self.root),
        ).pack(side="left", padx=(10, 0))
        create_secondary_button(
            actions,
            "Périmètre",
            lambda: open_scope_dialog(self.root),
        ).pack(side="left", padx=(10, 0))
        create_secondary_button(actions, "Quitter", self.close_app).pack(side="right")

        logo_panel = tk.Frame(
            right_column,
            bg=UI_PALETTE["mist"],
            padx=10,
            pady=10,
            highlightbackground=UI_PALETTE["line"],
            highlightthickness=1,
        )
        logo_panel.pack(fill="x", pady=(4, 0))

        utc_image = load_home_image("utc", max_width=190)
        region_image = load_home_image("hauts-de-france", max_width=120)
        if utc_image is not None:
            self.home_images.append(utc_image)
        if region_image is not None:
            self.home_images.append(region_image)

        create_logo_badge(logo_panel, utc_image).pack(fill="x")
        create_logo_badge(logo_panel, region_image).pack(fill="x", pady=(10, 0))

        footer = tk.Label(
            page,
            text=(
                "Conçu comme une interface de pré-analyse pour l'électrification des réseaux de bus, "
                "avec une logique d'ingénierie système."
            ),
            font=("Segoe UI", 9),
            fg=UI_PALETTE["steel"],
            bg=UI_PALETTE["sand"],
        )
        footer.pack(anchor="w", padx=24, pady=(0, 16))

        bind_canvas_mousewheel(page, page_canvas, excluded_classes=())

    def _build_selection_view(self) -> None:
        self.selection_frame = tk.Frame(self.container, bg=UI_PALETTE["sand"])
        self.selection_frame.grid(row=0, column=0, sticky="nsew")
        create_hero_banner(
            self.selection_frame,
            "Préparation de l'analyse",
            "Définissez ici le périmètre d'étude et vérifiez le trajet retenu avant le lancement.",
        )
        create_path_strip(self.selection_frame, "Sélection")

        frame_container, frame, frame_canvas = create_vertical_scrollable_area(
            self.selection_frame,
            padding=16,
        )
        frame_container.pack(fill="both", expand=True)
        frame_container.configure(style="Bus.TFrame")
        frame.configure(style="BusCard.TFrame")
        frame_canvas.configure(bg=UI_PALETTE["sand"])

        title_frame = tk.Frame(frame, bg=UI_PALETTE["white"])
        title_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        tk.Label(
            title_frame,
            text="Paramètres d'analyse",
            font=("Bahnschrift SemiBold", 15),
            fg=UI_PALETTE["ink"],
            bg=UI_PALETTE["white"],
        ).pack(anchor="w")
        tk.Label(
            title_frame,
            text=(
                "Renseignez la source de données, le réseau et la ligne. "
                "La sélection reste mémorisée pour fluidifier les retours entre les écrans."
            ),
            font=("Segoe UI", 10),
            fg=UI_PALETTE["steel"],
            bg=UI_PALETTE["white"],
            wraplength=740,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        ttk.Label(frame, text="Mode de données").grid(row=1, column=0, sticky="w", pady=6)
        mode_var = tk.StringVar(value=self.arguments.data_mode)
        mode_box = ttk.Combobox(
            frame,
            textvariable=mode_var,
            state="readonly",
            width=20,
            values=["local", "online"],
        )
        mode_box.grid(row=1, column=1, sticky="w", pady=6)

        ttk.Label(frame, text="Réseau GTFS").grid(row=2, column=0, sticky="w", pady=6)
        network_var = tk.StringVar()
        network_box = ttk.Combobox(
            frame,
            textvariable=network_var,
            state="normal",
            width=70,
            values=[],
        )
        network_box.grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="Ligne").grid(row=3, column=0, sticky="w", pady=6)
        line_var = tk.StringVar()
        line_box = ttk.Combobox(frame, textvariable=line_var, state="normal", width=70)
        line_box.grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="Direction (optionnelle)").grid(row=4, column=0, sticky="w", pady=6)
        direction_var = tk.StringVar(value=getattr(self.arguments, "direction_id", "") or "")
        direction_entry = ttk.Entry(frame, textvariable=direction_var, width=72)
        direction_entry.grid(row=4, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="Trajet retenu").grid(row=5, column=0, sticky="nw", pady=6)
        trip_preview_var = tk.StringVar(
            value="Choisissez une ligne pour afficher le trajet retenu et son nombre de segments."
        )
        ttk.Label(
            frame,
            textvariable=trip_preview_var,
            wraplength=640,
            justify="left",
        ).grid(row=5, column=1, sticky="w", pady=6)

        ttk.Label(frame, text="Nombre maximal de segments").grid(row=6, column=0, sticky="w", pady=6)
        max_segments_var = tk.StringVar(value=str(self.arguments.max_segments))
        max_segments_entry = ttk.Entry(frame, textvariable=max_segments_var, width=10)
        max_segments_entry.grid(row=6, column=1, sticky="w", pady=6)
        ttk.Label(
            frame,
            text="La valeur proposée correspond au nombre total de segments du trajet retenu, mais reste modifiable.",
            wraplength=520,
        ).grid(row=6, column=1, sticky="w", padx=(90, 0), pady=6)

        ttk.Label(frame, text="Nombre d'allers-retours").grid(row=7, column=0, sticky="w", pady=6)
        round_trip_count_var = tk.StringVar(value=str(getattr(self.arguments, "round_trip_count", 1)))
        round_trip_count_entry = ttk.Entry(frame, textvariable=round_trip_count_var, width=10)
        round_trip_count_entry.grid(row=7, column=1, sticky="w", pady=6)
        ttk.Label(
            frame,
            text=(
                "Applique le bilan du trajet de référence autant de fois que nécessaire. "
                "Si une direction unique est imposée, le multiplicateur s'applique à ce trajet."
            ),
            wraplength=520,
        ).grid(row=7, column=1, sticky="w", padx=(90, 0), pady=6)

        ttk.Label(frame, text="Nombre de bus").grid(row=8, column=0, sticky="w", pady=6)
        bus_count_var = tk.StringVar(value=str(getattr(self.arguments, "bus_count", 1)))
        bus_count_entry = ttk.Entry(frame, textvariable=bus_count_var, width=10)
        bus_count_entry.grid(row=8, column=1, sticky="w", pady=6)
        ttk.Label(
            frame,
            text="Multiplie le bilan cumulé pour représenter plusieurs bus affectés à la ligne.",
            wraplength=520,
        ).grid(row=8, column=1, sticky="w", padx=(90, 0), pady=6)

        ttk.Label(frame, text="Validation historique").grid(row=9, column=0, sticky="w", pady=6)
        validation_var = tk.StringVar(value="Aucune")
        validation_box = ttk.Combobox(
            frame,
            textvariable=validation_var,
            state="normal",
            width=70,
            values=["Aucune"],
        )
        validation_box.grid(row=9, column=1, sticky="ew", pady=6)

        altimetry_var = tk.BooleanVar(value=not self.arguments.disable_altimetry)
        ttk.Checkbutton(
            frame,
            text="Activer l'altimétrie IGN",
            variable=altimetry_var,
            style="Bus.TCheckbutton",
        ).grid(row=10, column=1, sticky="w", pady=6)
        ttk.Label(
            frame,
            text=(
                "En mode local, les tuiles altimétriques téléchargées sont sélectionnées "
                "automatiquement selon l'emprise géographique du GTFS retenu."
            ),
            wraplength=620,
            justify="left",
        ).grid(row=10, column=1, sticky="w", padx=(190, 0), pady=6)

        ttk.Label(frame, text="Source altimétrique détectée").grid(row=11, column=0, sticky="nw", pady=6)
        altimetry_preview_var = tk.StringVar(
            value="Choisissez un réseau et une ligne pour déterminer automatiquement la base altimétrique."
        )
        ttk.Label(
            frame,
            textvariable=altimetry_preview_var,
            wraplength=640,
            justify="left",
        ).grid(row=11, column=1, sticky="w", pady=6)

        ttk.Label(frame, text="Paramètres du bus").grid(row=12, column=0, sticky="nw", pady=6)
        selected_bus_parameters = clone_bus_parameters(
            getattr(self.arguments, "bus_parameters", BusParameters())
        )
        use_default_bus_parameters = getattr(
            self.arguments,
            "use_default_bus_parameters",
            True,
        )
        bus_summary_var = tk.StringVar(
            value=format_bus_parameters_summary(
                selected_bus_parameters,
                use_default_bus_parameters,
            )
        )
        bus_frame = tk.Frame(frame, bg=UI_PALETTE["white"])
        bus_frame.grid(row=12, column=1, sticky="ew", pady=6)

        route_maps: Dict[str, Dict[str, str]] = {}
        feed_label_map: Dict[str, Dict[str, str]] = {}
        validation_label_map: Dict[str, Dict[str, str]] = {}
        feeds: List[Dict[str, str]] = []
        filtered_feeds: List[Dict[str, str]] = []
        validation_references: List[Dict[str, str]] = []
        filtered_validation_references: List[Dict[str, str]] = []
        all_route_labels: List[str] = []
        filtered_route_labels: List[str] = []
        loaded_feed: Dict[str, List[Dict[str, str]]] | None = None
        loaded_gtfs_dir: Path | None = None

        def get_feed_labels(feed_items: List[Dict[str, str]]) -> List[str]:
            return [build_feed_label(feed) for feed in feed_items]

        def find_initial_feed_label() -> str | None:
            preferred_path = str(self.arguments.gtfs_path or "")
            preferred_network = str(self.arguments.network or "")

            for label, feed in feed_label_map.items():
                if preferred_path and str(feed["path"]) == preferred_path:
                    return label

            for label, feed in feed_label_map.items():
                if preferred_network and (
                    normalize_text(preferred_network) in normalize_text(feed["agency_name"])
                    or normalize_text(preferred_network) in normalize_text(feed["name"])
                ):
                    return label

            return None

        def find_initial_route_label() -> str | None:
            preferred_route_id = str(self.arguments.route_id or "")
            preferred_line = str(self.arguments.line or "")

            for label, route in route_maps.items():
                if preferred_route_id and route.get("route_id", "") == preferred_route_id:
                    return label

            for label, route in route_maps.items():
                short_name = route.get("route_short_name", "")
                if preferred_line and (
                    normalize_text(preferred_line) == normalize_text(short_name)
                    or normalize_text(preferred_line) == normalize_text(route.get("route_id", ""))
                    or normalize_text(preferred_line) in normalize_text(label)
                ):
                    return label

            return None

        def find_initial_validation_label() -> str | None:
            preferred_path = str(getattr(self.arguments, "validation_file", None) or "")
            if not preferred_path:
                return None

            for label, reference in validation_label_map.items():
                if str(reference["path"]) == preferred_path:
                    return label

            return None

        def resolve_selected_feed(accept_single_candidate: bool = False) -> Dict[str, str] | None:
            current_index = network_box.current()
            if 0 <= current_index < len(filtered_feeds):
                return filtered_feeds[current_index]

            selected_text = network_var.get().strip()
            if selected_text in feed_label_map:
                return feed_label_map[selected_text]

            if accept_single_candidate and len(filtered_feeds) == 1:
                return filtered_feeds[0]

            return None

        def resolve_selected_route(accept_single_candidate: bool = False) -> Dict[str, str] | None:
            current_index = line_box.current()
            if 0 <= current_index < len(filtered_route_labels):
                return route_maps[filtered_route_labels[current_index]]

            selected_text = line_var.get().strip()
            if selected_text in route_maps:
                return route_maps[selected_text]

            if accept_single_candidate and len(filtered_route_labels) == 1:
                return route_maps[filtered_route_labels[0]]

            return None

        def resolve_selected_validation(
            accept_single_candidate: bool = False,
        ) -> Dict[str, str] | None:
            selected_text = validation_var.get().strip()
            if not selected_text or normalize_text(selected_text) == "aucune":
                return None

            current_index = validation_box.current()
            current_values = list(validation_box.cget("values"))
            if 0 <= current_index < len(current_values):
                current_label = current_values[current_index]
                if current_label in validation_label_map:
                    return validation_label_map[current_label]

            if selected_text in validation_label_map:
                return validation_label_map[selected_text]

            if accept_single_candidate and len(filtered_validation_references) == 1:
                return filtered_validation_references[0]

            return None

        def configure_bus_parameters() -> None:
            nonlocal selected_bus_parameters, use_default_bus_parameters
            dialog_result = show_bus_parameters_dialog(
                self.root,
                selected_bus_parameters,
                use_default_bus_parameters,
            )
            if dialog_result is None:
                return

            selected_bus_parameters, use_default_bus_parameters = dialog_result
            bus_summary_var.set(
                format_bus_parameters_summary(
                    selected_bus_parameters,
                    use_default_bus_parameters,
                )
            )

        create_secondary_button(bus_frame, "Configurer le bus", configure_bus_parameters).pack(
            side="left"
        )
        tk.Label(
            bus_frame,
            textvariable=bus_summary_var,
            font=("Segoe UI", 10),
            fg=UI_PALETTE["night"],
            bg=UI_PALETTE["sand"],
            justify="left",
            wraplength=550,
        ).pack(side="left", padx=(12, 0))

        info_text = (
            "Choisissez d'abord le mode local ou online, puis le réseau et la ligne à étudier. "
            "Vous pouvez taper les premières lettres pour filtrer la recherche, par exemple "
            "'Com' pour retrouver Compiègne. Le détail par segment reste calculé sur un trajet "
            "de référence, puis le bilan est cumulé selon le nombre d'allers-retours et de bus."
        )
        ttk.Label(frame, text=info_text, wraplength=640).grid(
            row=13,
            column=0,
            columnspan=2,
            sticky="w",
            pady=12,
        )

        def filter_line_options(*_: Any) -> None:
            nonlocal filtered_route_labels
            filtered_route_labels = filter_labels(all_route_labels, line_var.get())
            line_box["values"] = filtered_route_labels
            update_trip_preview()

        def update_lines(*_: Any) -> None:
            nonlocal all_route_labels, filtered_route_labels, loaded_feed, loaded_gtfs_dir
            selected_feed = resolve_selected_feed(accept_single_candidate=True)
            if selected_feed is None:
                all_route_labels = []
                filtered_route_labels = []
                loaded_feed = None
                loaded_gtfs_dir = None
                route_maps.clear()
                line_box["values"] = []
                line_var.set("")
                trip_preview_var.set(
                    "Choisissez une ligne pour afficher le trajet retenu et son nombre de segments."
                )
                return

            try:
                gtfs_dir = select_gtfs_feed(
                    search_root=get_gtfs_search_root(mode_var.get()),
                    gtfs_path=selected_feed["path"],
                    network_name=selected_feed["agency_name"],
                    data_mode=mode_var.get(),
                    version_key=selected_feed.get("resource_updated"),
                )
                feed = load_gtfs_feed_cached(gtfs_dir)
            except Exception as exc:
                messagebox.showerror("Réseau GTFS", str(exc), parent=self.root)
                return

            loaded_feed = feed
            loaded_gtfs_dir = gtfs_dir
            labels = build_route_labels(feed["routes"])
            all_route_labels = labels
            route_maps.clear()

            for label, route in zip(labels, feed["routes"]):
                route_maps[label] = route

            filter_line_options()
            if filtered_route_labels and not line_var.get().strip():
                line_var.set(filtered_route_labels[0])
            update_trip_preview()

        def update_altimetry_preview() -> None:
            if not altimetry_var.get():
                altimetry_preview_var.set(
                    format_altimetry_preview(
                        {
                            "mode": "disabled",
                            "label": "L'altimétrie est désactivée pour cette analyse.",
                        }
                    )
                )
                return

            selected_route = resolve_selected_route(accept_single_candidate=True)
            if mode_var.get() == "online":
                geographic_bounds = None
                if loaded_feed is not None and selected_route is not None:
                    try:
                        geographic_bounds = compute_selected_gtfs_bounds_from_feed(
                            feed=loaded_feed,
                            route_id=selected_route["route_id"],
                            direction_id=direction_var.get().strip() or None,
                        )
                    except Exception:
                        geographic_bounds = None
                altimetry_preview_var.set(
                    format_altimetry_preview(
                        {
                            "mode": "online",
                            "label": "API altimétrique IGN en ligne",
                            "resource_name": "ign_rge_alti_wld",
                            "bounds": geographic_bounds,
                        }
                    )
                )
                return

            if loaded_feed is None or loaded_gtfs_dir is None or selected_route is None:
                altimetry_preview_var.set(
                    format_altimetry_preview(
                        {
                            "mode": "pending",
                            "label": (
                                "Choisissez un réseau et une ligne pour déterminer automatiquement "
                                "la base altimétrique locale."
                            ),
                        }
                    )
                )
                return

            try:
                altimetry_search_root = get_altimetry_search_root()
                geographic_bounds = compute_selected_gtfs_bounds_from_feed(
                    feed=loaded_feed,
                    route_id=selected_route["route_id"],
                    direction_id=direction_var.get().strip() or None,
                )
                metadata = describe_altimetry_source(
                    select_local_altimetry_dataset(
                        search_root=altimetry_search_root,
                        geographic_bounds=geographic_bounds,
                    ),
                    selection_mode="auto",
                    geographic_bounds=geographic_bounds,
                    search_root=altimetry_search_root,
                )
            except Exception as exc:
                altimetry_preview_var.set(
                    format_altimetry_preview(
                        {
                            "mode": "error",
                            "label": f"Détection altimétrique impossible avec les filtres courants : {exc}",
                        }
                    )
                )
                return

            altimetry_preview_var.set(format_altimetry_preview(metadata))

        def update_trip_preview(*_: Any) -> None:
            selected_route = resolve_selected_route(accept_single_candidate=True)
            if loaded_feed is None or selected_route is None:
                trip_preview_var.set(
                    "Choisissez une ligne pour afficher le trajet retenu et son nombre de segments."
                )
                update_altimetry_preview()
                return

            try:
                preview = preview_trip_selection(
                    feed=loaded_feed,
                    route_id=selected_route["route_id"],
                    direction_id=direction_var.get().strip() or None,
                )
            except Exception as exc:
                trip_preview_var.set(f"Trajet non résolu avec les filtres courants : {exc}")
                update_altimetry_preview()
                return

            headsign = preview["headsign"] or preview["direction_id"] or "N/A"
            if preview.get("trip_count", 1) > 1:
                trip_preview_var.set(
                    f"{preview['trip_count']} trajets retenus (aller/retour) | "
                    f"{preview['segment_count']} segments disponibles | "
                    f"{preview['stop_count']} arrêts cumulés | directions={headsign} | "
                    "base de calcul = 1 aller-retour"
                )
            else:
                trip_preview_var.set(
                    "trip_id="
                    f"{preview['trip_id']} | {preview['segment_count']} segments disponibles | "
                    f"{preview['stop_count']} arrêts | direction={headsign} | "
                    "base de calcul = 1 trajet"
                )
            max_segments_var.set(str(preview["segment_count"]))
            update_altimetry_preview()

        def refresh_networks(*_: Any) -> None:
            nonlocal feeds, filtered_feeds
            try:
                feeds = discover_gtfs_feeds_cached(
                    get_gtfs_search_root(mode_var.get()),
                    data_mode=mode_var.get(),
                )
            except Exception as exc:
                messagebox.showerror("Erreur réseaux", str(exc), parent=self.root)
                feeds = []

            feed_label_map.clear()
            for feed in feeds:
                feed_label_map[build_feed_label(feed)] = feed

            network_var.set("")
            filtered_feeds = feeds[:]
            network_box["values"] = get_feed_labels(filtered_feeds)
            line_box["values"] = []
            line_var.set("")
            update_lines()

        def refresh_validation_references() -> None:
            nonlocal validation_references, filtered_validation_references
            validation_references = discover_legacy_validation_files_cached(PROJECT_ROOT)
            validation_label_map.clear()

            for reference in validation_references:
                validation_label_map[build_validation_label(reference)] = reference

            filtered_validation_references = validation_references[:]
            validation_box["values"] = ["Aucune"] + [
                build_validation_label(reference) for reference in filtered_validation_references
            ]
            validation_var.set("Aucune")

        def apply_initial_selection() -> None:
            preferred_feed_label = find_initial_feed_label()
            if preferred_feed_label is not None:
                available_feed_labels = get_feed_labels(feeds)
                network_box["values"] = available_feed_labels
                network_var.set(preferred_feed_label)
                if preferred_feed_label in available_feed_labels:
                    network_box.current(available_feed_labels.index(preferred_feed_label))
                update_lines()

            preferred_route_label = find_initial_route_label()
            if preferred_route_label is not None:
                line_var.set(preferred_route_label)
                if preferred_route_label in filtered_route_labels:
                    line_box.current(filtered_route_labels.index(preferred_route_label))

            preferred_validation_label = find_initial_validation_label()
            if preferred_validation_label is not None:
                current_values = list(validation_box.cget("values"))
                validation_var.set(preferred_validation_label)
                if preferred_validation_label in current_values:
                    validation_box.current(current_values.index(preferred_validation_label))

            update_trip_preview()

        def filter_network_options(*_: Any) -> None:
            nonlocal filtered_feeds
            filtered_labels = filter_labels(get_feed_labels(feeds), network_var.get())
            filtered_feeds = [feed_label_map[label] for label in filtered_labels]
            network_box["values"] = filtered_labels
            update_lines()

        def filter_validation_options(*_: Any) -> None:
            nonlocal filtered_validation_references
            query = validation_var.get().strip()
            if not query or normalize_text(query) == "aucune":
                filtered_validation_references = validation_references[:]
                validation_box["values"] = ["Aucune"] + [
                    build_validation_label(reference) for reference in filtered_validation_references
                ]
                return

            filtered_labels = filter_labels(
                [build_validation_label(reference) for reference in validation_references],
                query,
            )
            filtered_validation_references = [
                validation_label_map[label] for label in filtered_labels
            ]
            validation_box["values"] = filtered_labels

        def confirm_selection() -> None:
            selected_feed = resolve_selected_feed(accept_single_candidate=True)
            if selected_feed is None:
                messagebox.showerror(
                    "Sélection incomplète",
                    "Choisissez un réseau GTFS dans la liste ou affinez la recherche.",
                    parent=self.root,
                )
                return

            selected_route = resolve_selected_route(accept_single_candidate=True)
            if selected_route is None:
                messagebox.showerror(
                    "Sélection incomplète",
                    "Choisissez une ligne dans la liste ou affinez la recherche.",
                    parent=self.root,
                )
                return

            selected_validation = resolve_selected_validation(accept_single_candidate=True)
            if (
                validation_var.get().strip()
                and normalize_text(validation_var.get()) != "aucune"
                and selected_validation is None
            ):
                messagebox.showerror(
                    "Validation historique",
                    "Choisissez une référence historique exacte dans la liste ou affinez la recherche.",
                    parent=self.root,
                )
                return

            try:
                max_segments = int(max_segments_var.get())
            except ValueError:
                messagebox.showerror(
                    "Valeur invalide",
                    "Le nombre maximal de segments doit être un entier.",
                    parent=self.root,
                )
                return

            try:
                round_trip_count = int(round_trip_count_var.get())
                if round_trip_count <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Valeur invalide",
                    "Le nombre d'allers-retours doit être un entier strictement positif.",
                    parent=self.root,
                )
                return

            try:
                bus_count = int(bus_count_var.get())
                if bus_count <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Valeur invalide",
                    "Le nombre de bus doit être un entier strictement positif.",
                    parent=self.root,
                )
                return

            resolved_gtfs_dir = loaded_gtfs_dir
            if resolved_gtfs_dir is None:
                try:
                    resolved_gtfs_dir = select_gtfs_feed(
                        search_root=get_gtfs_search_root(mode_var.get()),
                        gtfs_path=selected_feed["path"],
                        network_name=selected_feed["agency_name"],
                        data_mode=mode_var.get(),
                        version_key=selected_feed.get("resource_updated"),
                    )
                except Exception as exc:
                    messagebox.showerror("Réseau GTFS", str(exc), parent=self.root)
                    return

            self.arguments.data_mode = mode_var.get()
            self.arguments.network = selected_feed["agency_name"]
            self.arguments.gtfs_path = resolved_gtfs_dir
            self.arguments.gtfs_version_key = selected_feed.get("resource_updated")
            self.arguments.line = selected_route.get("route_short_name") or selected_route["route_id"]
            self.arguments.route_id = selected_route["route_id"]
            self.arguments.direction_id = direction_var.get().strip() or None
            self.arguments.max_segments = max_segments
            self.arguments.round_trip_count = round_trip_count
            self.arguments.bus_count = bus_count
            self.arguments.disable_altimetry = not altimetry_var.get()
            self.arguments.validation_file = (
                None if selected_validation is None else selected_validation["path"]
            )
            self.arguments.bus_parameters = clone_bus_parameters(selected_bus_parameters)
            self.arguments.use_default_bus_parameters = use_default_bus_parameters

            try:
                gtfs_data, results = run_analysis(self.arguments)
            except Exception as exc:
                messagebox.showerror("Analyse", str(exc), parent=self.root)
                return

            self.current_gtfs_data = gtfs_data
            self.current_results = results
            print_results_console(gtfs_data, results)
            self._build_results_view(gtfs_data, results)
            self.show_results()

        buttons = tk.Frame(frame, bg=UI_PALETTE["white"])
        buttons.grid(row=14, column=0, columnspan=2, sticky="ew", pady=16)
        create_secondary_button(buttons, "Aide", Aide_sélection).pack(side="left")
        create_secondary_button(buttons, "Annuler", self.close_app).pack(side="right")
        create_secondary_button(buttons, "Retour à l'accueil", self.show_home).pack(
            side="right",
            padx=8,
        )
        create_primary_button(buttons, "Lancer l'analyse", confirm_selection).pack(
            side="right",
            padx=8,
        )

        frame.columnconfigure(1, weight=1)
        mode_box.bind("<<ComboboxSelected>>", refresh_networks)
        network_box.bind("<<ComboboxSelected>>", update_lines)
        line_box.bind("<<ComboboxSelected>>", update_trip_preview)
        network_box.bind("<KeyRelease>", filter_network_options)
        line_box.bind("<KeyRelease>", filter_line_options)
        direction_entry.bind("<KeyRelease>", update_trip_preview)
        altimetry_var.trace_add("write", lambda *_: update_altimetry_preview())
        validation_box.bind("<KeyRelease>", filter_validation_options)
        refresh_networks()
        refresh_validation_references()
        apply_initial_selection()
        update_altimetry_preview()
        bind_canvas_mousewheel(frame, frame_canvas, excluded_classes=("TCombobox",))

        self.selection_state = {
            "frame": self.selection_frame,
            "focus_widget": network_box,
            "confirm": confirm_selection,
        }

    def _build_results_view(self, gtfs_data: Dict[str, Any], results: Dict[str, Any]) -> None:
        if self.results_frame is not None:
            self.results_frame.destroy()

        self.results_frame = tk.Frame(self.container, bg=UI_PALETTE["sand"])
        self.results_frame.grid(row=0, column=0, sticky="nsew")

        route_label = gtfs_data["route"].get("route_short_name", "") or gtfs_data["trip"].get(
            "route_id",
            "",
        )
        create_hero_banner(
            self.results_frame,
            f"Résultats de la ligne {route_label}",
            "Le calcul est terminé. Consultez le bilan, comparez les scénarios et explorez les segments filtrés.",
        )
        create_path_strip(self.results_frame, "Résultats")

        metrics_bar = tk.Frame(self.results_frame, bg=UI_PALETTE["sand"])
        metrics_bar.pack(fill="x", padx=20, pady=(0, 12))
        distance_label = "Distance cumulée" if results.get("operation_multiplier", 1) > 1 else "Distance totale"
        energy_label = "Énergie cumulée" if results.get("operation_multiplier", 1) > 1 else "Énergie totale"
        create_metric_tile(metrics_bar, distance_label, f"{results['total_distance_km']:.3f} km").pack(
            side="left",
            padx=(0, 10),
        )
        create_metric_tile(metrics_bar, energy_label, f"{results['total_energy_kwh']:.4f} kWh").pack(
            side="left",
            padx=(0, 10),
        )
        create_metric_tile(
            metrics_bar,
            "Consommation spécifique",
            f"{results['specific_consumption_kwh_km']:.4f} kWh/km",
            width=220,
        ).pack(side="left")

        def export_report() -> None:
            if filedialog is None or messagebox is None:
                return

            default_dir = EXPORTS_DIR / "rapports"
            default_dir.mkdir(parents=True, exist_ok=True)
            output_path = filedialog.asksaveasfilename(
                parent=self.root,
                title="Enregistrer le rapport d’analyse",
                defaultextension=".html",
                filetypes=[("Rapport HTML", "*.html")],
                initialdir=str(default_dir),
                initialfile=build_default_report_name(gtfs_data, results),
            )
            if not output_path:
                return

            try:
                bundle_paths = export_analysis_report_bundle(
                    gtfs_data=gtfs_data,
                    results=results,
                    requested_output=output_path,
                )
            except Exception as exc:
                messagebox.showerror(
                    "Export du rapport",
                    f"La génération du rapport a échoué : {exc}",
                    parent=self.root,
                )
                return

            messagebox.showinfo(
                "Rapport généré",
                "\n".join(
                    [
                        "Le rapport a été généré avec succès.",
                        f"HTML : {bundle_paths['html']}",
                        f"CSV segments : {bundle_paths['segments_csv']}",
                        f"CSV scénarios : {bundle_paths['scenarios_csv']}",
                    ]
                ),
                parent=self.root,
            )

        toolbar = tk.Frame(self.results_frame, bg=UI_PALETTE["sand"])
        toolbar.pack(fill="x", padx=20, pady=(0, 10))
        create_secondary_button(toolbar, "Aide", Aide_résultat).pack(side="left")
        create_secondary_button(toolbar, "Générer un rapport", export_report).pack(
            side="left",
            padx=(8, 0),
        )
        create_secondary_button(toolbar, "Fermer", self.close_app).pack(side="right")
        create_secondary_button(toolbar, "Retour à l'accueil", self.show_home).pack(
            side="right",
            padx=(0, 8),
        )
        create_primary_button(toolbar, "Retour à la sélection", self.show_selection).pack(
            side="right",
            padx=(0, 8),
        )

        notebook = ttk.Notebook(self.results_frame, style="BusNotebook.TNotebook")
        notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        summary_tab, summary_content, summary_canvas = create_vertical_scrollable_area(
            notebook,
            padding=12,
        )
        segments_tab, segments_content, segments_canvas = create_vertical_scrollable_area(
            notebook,
            padding=12,
        )
        notebook.add(summary_tab, text="Résumé")
        notebook.add(segments_tab, text="Segments")

        summary_frame = ttk.LabelFrame(
            summary_content,
            text="Résumé général",
            padding=10,
            style="Bus.TLabelframe",
        )
        summary_frame.pack(fill="x", expand=False)
        summary_text = tk.Text(summary_frame)
        summary_text.insert("1.0", format_results_summary(gtfs_data, results))
        self._configure_readonly_text(summary_text, height=9)
        summary_text.pack(fill="x", expand=True)

        trip_summary_frame = ttk.LabelFrame(
            summary_content,
            text="Bilan trajet",
            padding=10,
            style="Bus.TLabelframe",
        )
        trip_summary_frame.pack(fill="x", expand=False, pady=10)
        trip_summary_text = tk.Text(trip_summary_frame)
        trip_summary_text.insert("1.0", format_operation_overview(results))
        self._configure_readonly_text(trip_summary_text, height=9)
        trip_summary_text.pack(fill="x", expand=True)

        bus_frame = ttk.LabelFrame(
            summary_content,
            text="Paramètres du bus",
            padding=10,
            style="Bus.TLabelframe",
        )
        bus_frame.pack(fill="x", expand=False, pady=(0, 10))
        bus_text = tk.Text(bus_frame)
        bus_text.insert("1.0", format_results_bus_parameters(results))
        self._configure_readonly_text(bus_text, height=8)
        bus_text.pack(fill="x", expand=True)

        compare_frame = ttk.Frame(summary_content)
        compare_frame.pack(fill="both", expand=True, pady=10)
        compare_frame.columnconfigure(0, weight=1)
        compare_frame.columnconfigure(1, weight=1)
        compare_frame.rowconfigure(0, weight=1)

        scenario_frame = ttk.LabelFrame(
            compare_frame,
            text="Comparaison de scénarios",
            padding=10,
            style="Bus.TLabelframe",
        )
        scenario_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        scenario_frame.columnconfigure(0, weight=1)
        scenario_frame.rowconfigure(1, weight=1)

        scenario_text = tk.Text(scenario_frame)
        scenario_text.insert("1.0", format_scenario_summary(results))
        self._configure_readonly_text(scenario_text, height=4)
        scenario_text.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        scenario_columns = ("name", "energy", "specific", "delta")
        scenario_tree = ttk.Treeview(
            scenario_frame,
            columns=scenario_columns,
            show="headings",
            height=4,
            style="Bus.Treeview",
        )
        scenario_headings = {
            "name": "Scénario",
            "energy": "Énergie (kWh)",
            "specific": "Conso (kWh/km)",
            "delta": "Écart",
        }
        for column in scenario_columns:
            scenario_tree.heading(column, text=scenario_headings[column])
            scenario_tree.column(column, anchor="center", width=130 if column != "name" else 150)

        for scenario in results.get("scenario_comparisons", []):
            delta_text = (
                "référence"
                if scenario["is_reference"]
                else f"{scenario['delta_energy_kwh']:+.4f} kWh"
            )
            scenario_tree.insert(
                "",
                "end",
                values=(
                    scenario["name"],
                    f"{scenario['total_energy_kwh']:.4f}",
                    f"{scenario['specific_consumption_kwh_km']:.4f}",
                    delta_text,
                ),
            )

        scenario_tree.grid(row=1, column=0, sticky="nsew")
        scenario_chart_frame = tk.Frame(scenario_frame, bg=UI_PALETTE["white"])
        scenario_chart_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        scenario_chart_frame.columnconfigure(0, weight=1)
        scenario_chart_frame.rowconfigure(0, weight=1)

        scenario_canvas = tk.Canvas(
            scenario_chart_frame,
            height=280,
            background=UI_PALETTE["white"],
            highlightthickness=1,
            highlightbackground=UI_PALETTE["line"],
        )
        scenario_canvas.grid(row=0, column=0, sticky="nsew")

        scenario_y_scroll = ttk.Scrollbar(
            scenario_chart_frame,
            orient="vertical",
            command=scenario_canvas.yview,
        )
        scenario_y_scroll.grid(row=0, column=1, sticky="ns")
        scenario_canvas.configure(yscrollcommand=scenario_y_scroll.set)

        validation_frame = ttk.LabelFrame(
            compare_frame,
            text="Validation historique",
            padding=10,
            style="Bus.TLabelframe",
        )
        validation_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        validation_text = tk.Text(validation_frame)
        validation_text.insert("1.0", format_validation_summary(results))
        self._configure_readonly_text(validation_text, height=14)
        validation_text.pack(fill="both", expand=True)

        stops_frame = ttk.LabelFrame(
            summary_content,
            text="Arrêts du trajet",
            padding=10,
            style="Bus.TLabelframe",
        )
        stops_frame.pack(fill="x", expand=False, pady=10)

        stops_text = tk.Text(stops_frame)
        stops_text.insert("1.0", format_stop_sequences(gtfs_data))
        self._configure_readonly_text(stops_text, height=4)
        stops_text.pack(fill="x", expand=True)

        filter_frame = ttk.LabelFrame(
            segments_content,
            text="Filtres",
            padding=10,
            style="Bus.TLabelframe",
        )
        filter_frame.pack(fill="x", expand=False)
        ttk.Label(filter_frame, text="Recherche de segment").grid(row=0, column=0, sticky="w", padx=(0, 6))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(filter_frame, textvariable=search_var, width=35)
        search_entry.grid(row=0, column=1, sticky="w", padx=(0, 12))

        ttk.Label(filter_frame, text="Virages").grid(row=0, column=2, sticky="w", padx=(0, 6))
        turn_filter_var = tk.StringVar(value="Tous")
        turn_filter_box = ttk.Combobox(
            filter_frame,
            textvariable=turn_filter_var,
            state="readonly",
            width=18,
            values=["Tous", "Avec virages", "Virages marqués", "Sans virage"],
        )
        turn_filter_box.grid(row=0, column=3, sticky="w", padx=(0, 12))

        ttk.Label(filter_frame, text="Pente abs. min. (rad)").grid(row=0, column=4, sticky="w", padx=(0, 6))
        min_slope_var = tk.StringVar(value="0.0")
        min_slope_entry = ttk.Entry(filter_frame, textvariable=min_slope_var, width=10)
        min_slope_entry.grid(row=0, column=5, sticky="w", padx=(0, 12))

        filter_info_var = tk.StringVar(value="")
        ttk.Label(filter_frame, textvariable=filter_info_var).grid(row=0, column=6, sticky="e")

        table_frame = ttk.LabelFrame(
            segments_content,
            text="Segments",
            padding=10,
            style="Bus.TLabelframe",
        )
        table_frame.pack(fill="both", expand=True, pady=(10, 0))

        columns = (
            "name",
            "distance_m",
            "time_s",
            "speed_km_h",
            "slope_rad",
            "acceleration_m_s2",
            "sharp_turn_count",
            "turn_penalty_kw",
            "total_power_kw",
            "energy_kwh",
        )
        tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=16,
            style="Bus.Treeview",
        )
        headings = {
            "name": "Segment",
            "distance_m": "Distance (m)",
            "time_s": "Temps (s)",
            "speed_km_h": "Vitesse (km/h)",
            "slope_rad": "Pente (rad)",
            "acceleration_m_s2": "Accél. (m/s²)",
            "sharp_turn_count": "Virages",
            "turn_penalty_kw": "Virages (kW)",
            "total_power_kw": "Puissance (kW)",
            "energy_kwh": "Énergie (kWh)",
        }
        widths = {
            "name": 280,
            "distance_m": 90,
            "time_s": 80,
            "speed_km_h": 100,
            "slope_rad": 90,
            "acceleration_m_s2": 100,
            "sharp_turn_count": 70,
            "turn_penalty_kw": 95,
            "total_power_kw": 100,
            "energy_kwh": 100,
        }

        for column in columns:
            tree.heading(column, text=headings[column])
            tree.column(column, width=widths[column], anchor="center")

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        def draw_scenario_chart(*_: Any) -> None:
            scenario_canvas.delete("all")
            comparisons = results.get("scenario_comparisons", [])
            visible_width = max(scenario_canvas.winfo_width(), 560)
            visible_height = max(scenario_canvas.winfo_height(), 280)
            chart_title = (
                "Énergie cumulée par scénario"
                if results.get("operation_multiplier", 1) > 1
                else "Énergie totale par scénario"
            )
            chart_subtitle = (
                "Lecture verticale avec défilement local si la liste des scénarios s'allonge."
            )
            if results.get("operation_multiplier", 1) > 1:
                chart_subtitle = (
                    "Les valeurs sont cumulées selon le nombre d'allers-retours et de bus défini dans l'analyse."
                )

            if not comparisons:
                scenario_canvas.create_text(
                    24,
                    32,
                    text="Aucune comparaison disponible.",
                    anchor="w",
                    fill=UI_PALETTE["steel"],
                    font=("Segoe UI", 10),
                )
                scenario_canvas.configure(scrollregion=(0, 0, visible_width, visible_height))
                return

            width = visible_width
            title_height = 56
            row_height = 66
            bottom_padding = 26
            height = max(
                visible_height,
                title_height + bottom_padding + (len(comparisons) * row_height),
            )

            margin_left = 180
            margin_right = 86
            margin_top = 58
            bar_height = 24
            plot_width = max(width - margin_left - margin_right, 180)

            values = [scenario["total_energy_kwh"] for scenario in comparisons]
            max_value = max(max(values), 0.0)
            value_range = max(max_value, 1.0)

            scenario_canvas.create_text(
                24,
                20,
                anchor="w",
                text=chart_title,
                fill=UI_PALETTE["ink"],
                font=("Bahnschrift SemiBold", 12),
            )
            scenario_canvas.create_text(
                24,
                38,
                anchor="w",
                text=chart_subtitle,
                fill=UI_PALETTE["steel"],
                font=("Segoe UI", 9),
            )

            grid_steps = 4
            for step_index in range(grid_steps + 1):
                tick_value = value_range * step_index / grid_steps
                x_tick = margin_left + (plot_width * step_index / grid_steps)
                line_color = "#dbe5ec" if step_index < grid_steps else "#6b7280"
                scenario_canvas.create_line(
                    x_tick,
                    margin_top,
                    x_tick,
                    height - bottom_padding,
                    fill=line_color,
                    dash=(3, 5) if step_index < grid_steps else (),
                    width=1 if step_index < grid_steps else 1.4,
                )
                scenario_canvas.create_text(
                    x_tick,
                    height - 10,
                    text=f"{tick_value:.1f}",
                    anchor="n",
                    fill=UI_PALETTE["steel"],
                    font=("Segoe UI", 9),
                )

            for index, scenario in enumerate(comparisons):
                top_y = margin_top + (index * row_height)
                center_y = top_y + (row_height / 2)
                value = scenario["total_energy_kwh"]
                bar_length = (max(value, 0.0) / value_range) * plot_width
                x0 = margin_left
                x1 = margin_left + bar_length
                y0 = center_y - (bar_height / 2)
                y1 = center_y + (bar_height / 2)
                fill_color = "#3f7d58" if scenario["is_reference"] else "#2f6db2"
                outline_color = "#2d5b41" if scenario["is_reference"] else "#1f4f86"

                scenario_canvas.create_text(
                    24,
                    center_y - 10,
                    text=scenario["name"],
                    anchor="w",
                    fill=UI_PALETTE["ink"],
                    font=("Segoe UI Semibold", 10),
                    width=140,
                    justify="left",
                )

                scenario_canvas.create_rectangle(
                    margin_left,
                    y0,
                    margin_left + plot_width,
                    y1,
                    fill="#f3f6f9",
                    outline=UI_PALETTE["line"],
                    width=1,
                )
                scenario_canvas.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    fill=fill_color,
                    outline=outline_color,
                    width=1,
                )

                value_label = f"{value:.2f} kWh"
                label_x = min(x1 + 12, width - 24)
                scenario_canvas.create_text(
                    label_x,
                    center_y,
                    text=value_label,
                    anchor="w",
                    fill=UI_PALETTE["ink"],
                    font=("Segoe UI Semibold", 9),
                )

                if scenario["is_reference"]:
                    scenario_canvas.create_text(
                        24,
                        center_y + 12,
                        text="Référence",
                        anchor="w",
                        fill=UI_PALETTE["steel"],
                        font=("Segoe UI", 8),
                    )

            scenario_canvas.configure(scrollregion=(0, 0, width, height))

        def scroll_scenario_chart(event: Any) -> str:
            delta = getattr(event, "delta", 0)
            if not delta:
                return "break"
            scenario_canvas.yview_scroll(int(-delta / 120), "units")
            return "break"

        def segment_matches_filters(segment: Dict[str, Any]) -> bool:
            search_text = normalize_text(search_var.get().strip())
            if search_text and search_text not in normalize_text(segment["name"]):
                return False

            filter_value = turn_filter_var.get()
            if filter_value == "Avec virages" and segment["turn_points_count"] <= 0:
                return False
            if filter_value == "Virages marqués" and segment["sharp_turn_count"] <= 0:
                return False
            if filter_value == "Sans virage" and segment["turn_points_count"] > 0:
                return False

            try:
                min_slope = float(min_slope_var.get() or 0.0)
            except ValueError:
                min_slope = 0.0

            return abs(segment["slope_rad"]) >= max(min_slope, 0.0)

        def refresh_segments_table(*_: Any) -> None:
            for item_id in tree.get_children():
                tree.delete(item_id)

            filtered_segments = [
                segment for segment in results["segments"] if segment_matches_filters(segment)
            ]
            filter_info_var.set(f"{len(filtered_segments)} segment(s) affichés")

            for seg in filtered_segments:
                tree.insert(
                    "",
                    "end",
                    values=(
                        seg["name"],
                        f"{seg['distance_m']:.1f}",
                        f"{seg['time_s']:.1f}",
                        f"{seg['speed_km_h']:.2f}",
                        f"{seg['slope_rad']:.5f}",
                        f"{seg['acceleration_m_s2']:.4f}",
                        f"{seg['sharp_turn_count']}",
                        f"{seg['turn_penalty_kw']:.2f}",
                        f"{seg['total_power_kw']:.2f}",
                        f"{seg['energy_kwh']:.4f}",
                    ),
                )

        def reset_filters() -> None:
            search_var.set("")
            turn_filter_var.set("Tous")
            min_slope_var.set("0.0")
            refresh_segments_table()

        ttk.Button(filter_frame, text="Réinitialiser", command=reset_filters).grid(
            row=0,
            column=7,
            sticky="e",
            padx=(12, 0),
        )

        search_var.trace_add("write", refresh_segments_table)
        min_slope_var.trace_add("write", refresh_segments_table)
        turn_filter_box.bind("<<ComboboxSelected>>", refresh_segments_table)
        scenario_canvas.bind("<Configure>", draw_scenario_chart)
        scenario_canvas.bind("<MouseWheel>", scroll_scenario_chart)
        bind_canvas_mousewheel(summary_content, summary_canvas)
        bind_canvas_mousewheel(segments_content, segments_canvas)

        refresh_segments_table()
        self.root.after(50, draw_scenario_chart)


def launch_unified_gui(arguments: argparse.Namespace) -> None:
    app = UnifiedBusApplication(arguments)
    app.run()
