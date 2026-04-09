import argparse
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, List

from altimetry_services import describe_altimetry_source, select_local_altimetry_dataset
from app_models import BusParameters
from gtfs_services import (
    compute_selected_gtfs_bounds_from_feed,
    discover_gtfs_feeds,
    load_gtfs_feed,
    normalize_text,
    preview_trip_selection,
    select_gtfs_feed,
)
from project_paths import EXPORTS_DIR, PROJECT_ROOT, get_altimetry_search_root, get_gtfs_search_root
from validation_services import discover_legacy_validation_files
from window_layout import apply_main_window_geometry, capture_main_window_geometry

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:
    tk = None
    ttk = None
    messagebox = None


UI_PALETTE = {
    "ink": "#17324d",
    "steel": "#5f7892",
    "mist": "#eef4f8",
    "sand": "#f5efe6",
    "teal": "#117a8b",
    "amber": "#d98b2b",
    "night": "#0f2234",
    "white": "#ffffff",
    "line": "#d7e2ea",
    "success": "#2d6a4f",
}

_GTFS_DISCOVERY_CACHE: Dict[tuple[str, str], List[Dict[str, str]]] = {}
_GTFS_FEED_CACHE: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
_VALIDATION_REFERENCE_CACHE: Dict[str, List[Dict[str, str]]] = {}

BUS_PARAMETER_FIELDS = [
    ("mass_kg", "Masse du bus", "kg"),
    ("g", "Gravité", "m/s²"),
    ("air_density", "Densité de l’air", "kg/m³"),
    ("rolling_coeff", "Coefficient de roulement", ""),
    ("frontal_area_m2", "Surface frontale", "m²"),
    ("drag_coeff", "Coefficient de traînée", ""),
    ("aux_power_kw", "Puissance auxiliaire", "kW"),
]


def discover_gtfs_feeds_cached(search_root: Path, data_mode: str) -> List[Dict[str, str]]:
    cache_key = (str(search_root.resolve()), data_mode)
    if cache_key not in _GTFS_DISCOVERY_CACHE:
        _GTFS_DISCOVERY_CACHE[cache_key] = discover_gtfs_feeds(search_root, data_mode=data_mode)
    return list(_GTFS_DISCOVERY_CACHE[cache_key])


def load_gtfs_feed_cached(gtfs_dir: Path) -> Dict[str, List[Dict[str, str]]]:
    cache_key = str(gtfs_dir.resolve())
    if cache_key not in _GTFS_FEED_CACHE:
        _GTFS_FEED_CACHE[cache_key] = load_gtfs_feed(gtfs_dir)
    return _GTFS_FEED_CACHE[cache_key]


def discover_legacy_validation_files_cached(search_root: Path) -> List[Dict[str, str]]:
    cache_key = str(search_root.resolve())
    if cache_key not in _VALIDATION_REFERENCE_CACHE:
        _VALIDATION_REFERENCE_CACHE[cache_key] = discover_legacy_validation_files(search_root)
    return list(_VALIDATION_REFERENCE_CACHE[cache_key])


def clone_bus_parameters(bus: BusParameters) -> BusParameters:
    return BusParameters(**{field.name: getattr(bus, field.name) for field in fields(BusParameters)})


def bus_parameters_to_dict(bus: BusParameters) -> Dict[str, float]:
    return {field.name: float(getattr(bus, field.name)) for field in fields(BusParameters)}


def format_bus_parameters_summary(bus: BusParameters, use_default: bool) -> str:
    mode_label = "Valeurs par défaut" if use_default else "Paramètres personnalisés"
    mass_label = f"{bus.mass_kg:,.0f}".replace(",", " ")
    return (
        f"{mode_label} : masse {mass_label} kg | "
        f"surface frontale {bus.frontal_area_m2:.2f} m² | "
        f"Cx {bus.drag_coeff:.2f} | "
        f"Crr {bus.rolling_coeff:.3f} | "
        f"Puissance auxiliaire {bus.aux_power_kw:.1f} kW"
    )


def format_altimetry_preview(metadata: Dict[str, Any]) -> str:
    bounds = metadata.get("bounds")

    def format_bounds_suffix() -> str:
        if not bounds:
            return ""
        return (
            " | emprise GTFS : "
            f"lat {bounds['min_lat']:.4f}-{bounds['max_lat']:.4f}, "
            f"lon {bounds['min_lon']:.4f}-{bounds['max_lon']:.4f}"
        )

    mode = metadata.get("mode", "disabled")
    if mode == "pending":
        return metadata.get(
            "label",
            "Choisissez un réseau et une ligne pour déterminer automatiquement la source altimétrique.",
        )
    if mode == "error":
        return metadata.get(
            "label",
            "La source altimétrique n'a pas pu être déterminée automatiquement.",
        )
    if mode == "online":
        resource_name = metadata.get("resource_name", "ign_rge_alti_wld")
        return (
            f"Source détectée : API altimétrique IGN en ligne | base : {resource_name}"
            f"{format_bounds_suffix()}."
        )
    if mode == "local":
        dataset_names = metadata.get("dataset_names", [])
        dataset_text = ", ".join(dataset_names[:2])
        if len(dataset_names) > 2:
            dataset_text = f"{dataset_text}, +{len(dataset_names) - 2} autre(s)"
        if dataset_text:
            return (
                f"Source détectée : {dataset_text}. "
                f"{metadata.get('tile_count', 0)} tuile(s) locale(s) seront mobilisées automatiquement"
                f"{format_bounds_suffix()}."
            )
        return metadata.get("label", "Source altimétrique locale détectée.")
    if mode == "local_missing":
        return (
            "Aucune tuile locale téléchargée ne couvre actuellement la zone GTFS sélectionnée. "
            "Le calcul restera possible, mais sans enrichissement altimétrique local."
        )
    if mode == "disabled":
        return "L'altimétrie est désactivée pour cette analyse."
    return metadata.get("label", "Source altimétrique non déterminée.")


def format_gtfs_bounds(bounds: Dict[str, float] | None) -> str:
    if not bounds:
        return "Emprise GTFS : non déterminée"
    return (
        "Emprise GTFS : "
        f"lat {bounds['min_lat']:.4f}-{bounds['max_lat']:.4f} | "
        f"lon {bounds['min_lon']:.4f}-{bounds['max_lon']:.4f}"
    )


def format_bus_parameters_details(bus: BusParameters, use_default: bool) -> str:
    mode_label = "Valeurs par défaut" if use_default else "Paramètres personnalisés"
    return "\n".join(
        [
            f"Mode : {mode_label}",
            f"Masse du bus : {bus.mass_kg:.1f} kg",
            f"Gravité : {bus.g:.3f} m/s²",
            f"Densité de l’air : {bus.air_density:.3f} kg/m³",
            f"Coefficient de roulement : {bus.rolling_coeff:.4f}",
            f"Surface frontale : {bus.frontal_area_m2:.2f} m²",
            f"Coefficient de traînée : {bus.drag_coeff:.3f}",
            f"Puissance auxiliaire : {bus.aux_power_kw:.2f} kW",
        ]
    )


def validate_bus_parameters_values(values: Dict[str, float]) -> str | None:
    strictly_positive_fields = {
        "mass_kg": "La masse du bus doit être strictement positive.",
        "g": "La gravité doit être strictement positive.",
        "air_density": "La densité de l’air doit être strictement positive.",
        "frontal_area_m2": "La surface frontale doit être strictement positive.",
        "aux_power_kw": "La puissance auxiliaire doit être strictement positive ou nulle.",
    }
    non_negative_fields = {
        "rolling_coeff": "Le coefficient de roulement doit être positif ou nul.",
        "drag_coeff": "Le coefficient de traînée doit être positif ou nul.",
        "aux_power_kw": "La puissance auxiliaire doit être positive ou nulle.",
    }

    for field_name, error_message in strictly_positive_fields.items():
        value = values[field_name]
        if field_name == "aux_power_kw":
            if value < 0:
                return error_message
        elif value <= 0:
            return error_message

    for field_name, error_message in non_negative_fields.items():
        if values[field_name] < 0:
            return error_message

    return None


def show_bus_parameters_dialog(
    parent: Any,
    initial_bus: BusParameters,
    use_default: bool,
) -> tuple[BusParameters, bool] | None:
    if tk is None or ttk is None or messagebox is None:
        return None

    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title("Paramètres du bus")
    dialog.transient(parent)
    dialog.grab_set()
    dialog.geometry("760x520")
    dialog.minsize(720, 500)
    dialog.configure(bg=UI_PALETTE["sand"])
    configure_app_theme(dialog)

    default_bus = BusParameters()
    current_bus = clone_bus_parameters(initial_bus)
    result: Dict[str, Any] = {"value": None}

    create_hero_banner(
        dialog,
        "Paramètres du bus",
        "Choisissez les valeurs par défaut du modèle ou renseignez un jeu de paramètres personnalisé.",
    )

    container, content, canvas = create_vertical_scrollable_area(dialog, padding=16)
    container.pack(fill="both", expand=True, padx=16, pady=(0, 12))
    container.configure(style="Bus.TFrame")
    content.configure(style="Bus.TFrame")
    canvas.configure(bg=UI_PALETTE["sand"])

    card = create_surface_card(content, padding=(18, 18))
    card.pack(fill="x", expand=True)
    create_card_title(
        card,
        "Configuration physique",
        "Les valeurs seront utilisées directement dans le calcul énergétique du trajet et dans le bilan final.",
    )

    toggle_frame = tk.Frame(card, bg=UI_PALETTE["white"])
    toggle_frame.pack(fill="x", pady=(14, 10))
    use_default_var = tk.BooleanVar(value=use_default)
    ttk.Checkbutton(
        toggle_frame,
        text="Utiliser les valeurs par défaut de l’outil",
        variable=use_default_var,
        style="Bus.TCheckbutton",
    ).pack(anchor="w")

    help_label = tk.Label(
        toggle_frame,
        text="Décochez cette option pour saisir un modèle de bus spécifique à votre étude.",
        font=("Segoe UI", 10),
        fg=UI_PALETTE["steel"],
        bg=UI_PALETTE["white"],
        justify="left",
        wraplength=620,
    )
    help_label.pack(anchor="w", pady=(6, 0))

    form_frame = tk.Frame(card, bg=UI_PALETTE["white"])
    form_frame.pack(fill="x", pady=(6, 0))
    form_frame.columnconfigure(1, weight=1)

    value_vars: Dict[str, Any] = {}
    entry_widgets: Dict[str, Any] = {}

    def set_entry_values(bus: BusParameters) -> None:
        for field_name, _, _ in BUS_PARAMETER_FIELDS:
            value_vars[field_name].set(str(getattr(bus, field_name)))

    for row_index, (field_name, label_text, unit_text) in enumerate(BUS_PARAMETER_FIELDS):
        tk.Label(
            form_frame,
            text=label_text,
            font=("Segoe UI Semibold", 10),
            fg=UI_PALETTE["ink"],
            bg=UI_PALETTE["white"],
        ).grid(row=row_index, column=0, sticky="w", pady=6, padx=(0, 10))

        value_var = tk.StringVar(value=str(getattr(current_bus, field_name)))
        entry = ttk.Entry(form_frame, textvariable=value_var, width=20, style="Bus.TEntry")
        entry.grid(row=row_index, column=1, sticky="ew", pady=6)

        tk.Label(
            form_frame,
            text=unit_text,
            font=("Segoe UI", 10),
            fg=UI_PALETTE["steel"],
            bg=UI_PALETTE["white"],
        ).grid(row=row_index, column=2, sticky="w", pady=6, padx=(10, 0))

        value_vars[field_name] = value_var
        entry_widgets[field_name] = entry

    summary_var = tk.StringVar(
        value=format_bus_parameters_summary(
            default_bus if use_default_var.get() else current_bus,
            use_default_var.get(),
        )
    )
    summary_label = tk.Label(
        card,
        textvariable=summary_var,
        font=("Segoe UI", 10),
        fg=UI_PALETTE["steel"],
        bg=UI_PALETTE["white"],
        justify="left",
        wraplength=620,
    )
    summary_label.pack(anchor="w", pady=(14, 0))

    buttons = tk.Frame(dialog, bg=UI_PALETTE["sand"])
    buttons.pack(fill="x", padx=16, pady=(0, 16))

    def refresh_bus_state() -> None:
        bus_source = default_bus if use_default_var.get() else current_bus
        if use_default_var.get():
            set_entry_values(default_bus)
        for entry in entry_widgets.values():
            entry.configure(state="disabled" if use_default_var.get() else "normal")
        summary_var.set(format_bus_parameters_summary(bus_source, use_default_var.get()))

    def confirm_dialog() -> None:
        nonlocal current_bus
        if use_default_var.get():
            result["value"] = (clone_bus_parameters(default_bus), True)
            dialog.destroy()
            return

        raw_values: Dict[str, float] = {}
        for field_name, label_text, _ in BUS_PARAMETER_FIELDS:
            raw_text = value_vars[field_name].get().strip().replace(",", ".")
            try:
                raw_values[field_name] = float(raw_text)
            except ValueError:
                messagebox.showerror(
                    "Valeur invalide",
                    f"La valeur saisie pour « {label_text} » n’est pas un nombre valide.",
                    parent=dialog,
                )
                return

        validation_error = validate_bus_parameters_values(raw_values)
        if validation_error is not None:
            messagebox.showerror("Paramètres du bus", validation_error, parent=dialog)
            return

        current_bus = BusParameters(**raw_values)
        result["value"] = (clone_bus_parameters(current_bus), False)
        dialog.destroy()

    def cancel_dialog() -> None:
        dialog.destroy()

    use_default_var.trace_add("write", lambda *_: refresh_bus_state())

    cancel_button = create_secondary_button(buttons, "Annuler", cancel_dialog)
    cancel_button.pack(side="right")
    create_primary_button(buttons, "Valider les paramètres", confirm_dialog).pack(
        side="right",
        padx=(0, 8),
    )

    refresh_bus_state()
    bind_canvas_mousewheel(content, canvas, excluded_classes=("TCombobox",))
    dialog.bind("<Escape>", lambda event: cancel_dialog())
    dialog.bind("<Return>", lambda event: confirm_dialog())
    dialog.after_idle(lambda: next(iter(entry_widgets.values())).focus_set())
    dialog.deiconify()
    dialog.wait_window()
    return result["value"]


def configure_app_theme(root: Any) -> None:
    root.configure(bg=UI_PALETTE["sand"])
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("Bus.TFrame", background=UI_PALETTE["sand"])
    style.configure("BusCard.TFrame", background=UI_PALETTE["white"])
    style.configure(
        "Bus.TLabel",
        background=UI_PALETTE["sand"],
        foreground=UI_PALETTE["ink"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "Muted.TLabel",
        background=UI_PALETTE["sand"],
        foreground=UI_PALETTE["steel"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "BusCardTitle.TLabel",
        background=UI_PALETTE["white"],
        foreground=UI_PALETTE["ink"],
        font=("Bahnschrift SemiBold", 13),
    )
    style.configure(
        "BusCardBody.TLabel",
        background=UI_PALETTE["white"],
        foreground=UI_PALETTE["steel"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "BusNotebook.TNotebook",
        background=UI_PALETTE["sand"],
        borderwidth=0,
        tabmargins=(0, 0, 0, 0),
    )
    style.configure(
        "BusNotebook.TNotebook.Tab",
        background=UI_PALETTE["mist"],
        foreground=UI_PALETTE["ink"],
        padding=(18, 8),
        font=("Segoe UI Semibold", 10),
        borderwidth=0,
    )
    style.map(
        "BusNotebook.TNotebook.Tab",
        background=[("selected", UI_PALETTE["white"])],
        foreground=[("selected", UI_PALETTE["night"])],
    )
    style.configure(
        "Bus.TLabelframe",
        background=UI_PALETTE["white"],
        borderwidth=1,
        relief="solid",
        bordercolor=UI_PALETTE["line"],
    )
    style.configure(
        "Bus.TLabelframe.Label",
        background=UI_PALETTE["white"],
        foreground=UI_PALETTE["ink"],
        font=("Bahnschrift SemiBold", 12),
    )
    style.configure(
        "Bus.TEntry",
        fieldbackground=UI_PALETTE["white"],
        bordercolor=UI_PALETTE["line"],
        padding=6,
    )
    style.configure(
        "Bus.TCombobox",
        fieldbackground=UI_PALETTE["white"],
        bordercolor=UI_PALETTE["line"],
        padding=6,
    )
    style.configure(
        "Bus.TCheckbutton",
        background=UI_PALETTE["white"],
        foreground=UI_PALETTE["ink"],
        font=("Segoe UI", 10),
    )
    style.configure(
        "Bus.Treeview",
        background=UI_PALETTE["white"],
        fieldbackground=UI_PALETTE["white"],
        foreground=UI_PALETTE["ink"],
        rowheight=28,
        borderwidth=0,
        font=("Segoe UI", 9),
    )
    style.configure(
        "Bus.Treeview.Heading",
        background=UI_PALETTE["mist"],
        foreground=UI_PALETTE["ink"],
        font=("Segoe UI Semibold", 9),
        relief="flat",
    )
    style.map(
        "Bus.Treeview",
        background=[("selected", "#dbeafe")],
        foreground=[("selected", UI_PALETTE["ink"])],
    )


def create_hero_banner(
    parent: Any,
    title: str,
    subtitle: str,
) -> Any:
    hero = tk.Frame(parent, bg=UI_PALETTE["night"], padx=28, pady=22)
    hero.pack(fill="x", padx=20, pady=(20, 12))
    tk.Label(
        hero,
        text=title,
        font=("Bahnschrift SemiBold", 20),
        fg=UI_PALETTE["white"],
        bg=UI_PALETTE["night"],
        justify="left",
    ).pack(anchor="w")
    tk.Label(
        hero,
        text=subtitle,
        font=("Segoe UI", 10),
        fg="#d9e6f1",
        bg=UI_PALETTE["night"],
        justify="left",
        wraplength=920,
    ).pack(anchor="w", pady=(10, 0))
    return hero


def create_path_strip(parent: Any, active_step: str) -> Any:
    frame = tk.Frame(parent, bg=UI_PALETTE["sand"])
    frame.pack(fill="x", padx=20, pady=(0, 12))
    steps = ["Accueil", "Sélection", "Résultats"]
    for index, step in enumerate(steps):
        is_active = step == active_step
        tk.Label(
            frame,
            text=step,
            font=("Segoe UI Semibold", 10),
            bg=UI_PALETTE["teal"] if is_active else UI_PALETTE["white"],
            fg=UI_PALETTE["white"] if is_active else UI_PALETTE["ink"],
            padx=12,
            pady=8,
            highlightbackground=UI_PALETTE["line"],
            highlightthickness=1,
        ).pack(side="left")
        if index < len(steps) - 1:
            tk.Label(
                frame,
                text=">",
                font=("Bahnschrift SemiBold", 11),
                bg=UI_PALETTE["sand"],
                fg=UI_PALETTE["steel"],
                padx=8,
            ).pack(side="left")
    return frame


def create_surface_card(parent: Any, padding: tuple[int, int] = (16, 16)) -> Any:
    card = tk.Frame(
        parent,
        bg=UI_PALETTE["white"],
        padx=padding[0],
        pady=padding[1],
        highlightbackground=UI_PALETTE["line"],
        highlightthickness=1,
    )
    return card


def create_card_title(parent: Any, title: str, body: str | None = None) -> None:
    tk.Label(
        parent,
        text=title,
        font=("Bahnschrift SemiBold", 14),
        fg=UI_PALETTE["ink"],
        bg=UI_PALETTE["white"],
    ).pack(anchor="w")
    if body:
        tk.Label(
            parent,
            text=body,
            font=("Segoe UI", 10),
            fg=UI_PALETTE["steel"],
            bg=UI_PALETTE["white"],
            justify="left",
            wraplength=760,
        ).pack(anchor="w", pady=(6, 0))


def create_metric_tile(parent: Any, label: str, value: str, width: int = 190) -> Any:
    tile = tk.Frame(
        parent,
        bg=UI_PALETTE["mist"],
        padx=14,
        pady=12,
        width=width,
        highlightbackground=UI_PALETTE["line"],
        highlightthickness=1,
    )
    tile.pack_propagate(False)
    tk.Label(
        tile,
        text=label,
        font=("Segoe UI", 9),
        fg=UI_PALETTE["steel"],
        bg=UI_PALETTE["white"],
    ).pack(anchor="w")
    tk.Label(
        tile,
        text=value,
        font=("Segoe UI Semibold", 12),
        fg=UI_PALETTE["ink"],
        bg=UI_PALETTE["mist"],
        wraplength=width - 20,
        justify="left",
    ).pack(anchor="w", pady=(4, 0))
    return tile


def create_primary_button(parent: Any, text: str, command: Any) -> Any:
    return tk.Button(
        parent,
        text=text,
        command=command,
        font=("Bahnschrift SemiBold", 12),
        bg=UI_PALETTE["teal"],
        fg=UI_PALETTE["white"],
        activebackground="#0d6270",
        activeforeground=UI_PALETTE["white"],
        relief="flat",
        padx=16,
        pady=10,
        cursor="hand2",
    )


def create_secondary_button(parent: Any, text: str, command: Any) -> Any:
    return tk.Button(
        parent,
        text=text,
        command=command,
        font=("Segoe UI Semibold", 10),
        bg=UI_PALETTE["white"],
        fg=UI_PALETTE["ink"],
        activebackground="#e8eef5",
        relief="flat",
        padx=14,
        pady=10,
        cursor="hand2",
    )


def configure_readonly_text(widget: Any, height: int) -> None:
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


def create_vertical_scrollable_area(
    parent: Any,
    padding: int | tuple[int, ...] = 0,
) -> tuple[Any, Any, Any]:
    container = ttk.Frame(parent)
    canvas = tk.Canvas(container, highlightthickness=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)

    container.columnconfigure(0, weight=1)
    container.rowconfigure(0, weight=1)
    canvas.grid(row=0, column=0, sticky="nsew")
    scrollbar.grid(row=0, column=1, sticky="ns")

    content = ttk.Frame(canvas, padding=padding)
    window_id = canvas.create_window((0, 0), window=content, anchor="nw")

    def update_scrollregion(_: Any = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def resize_content(event: Any) -> None:
        canvas.itemconfigure(window_id, width=event.width)

    content.bind("<Configure>", update_scrollregion)
    canvas.bind("<Configure>", resize_content)
    return container, content, canvas


def bind_canvas_mousewheel(
    widget: Any,
    canvas: Any,
    excluded_classes: tuple[str, ...] = ("Treeview",),
) -> None:
    def on_mousewheel(event: Any) -> str | None:
        target = event.widget
        if target is not None and target.winfo_class() in excluded_classes:
            return None
        delta = getattr(event, "delta", 0)
        if not delta:
            return None
        canvas.yview_scroll(int(-delta / 120), "units")
        return "break"

    widget.bind("<MouseWheel>", on_mousewheel, add="+")
    for child in widget.winfo_children():
        bind_canvas_mousewheel(child, canvas, excluded_classes)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calcule la consommation d'un bus électrique à partir d'un feed GTFS."
    )
    parser.add_argument(
        "--data-mode",
        type=str,
        choices=("local", "online"),
        default="local",
        help="Source des données GTFS et altimétriques : local ou online.",
    )
    parser.add_argument(
        "--gtfs-version-key",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--gtfs-path",
        type=str,
        default=None,
        help="Chemin du dossier GTFS. Si absent, le script cherche un feed GTFS dans le dossier courant.",
    )
    parser.add_argument(
        "--network",
        type=str,
        default=None,
        help="Nom de commune, dossier ou réseau GTFS à analyser.",
    )
    parser.add_argument(
        "--list-networks",
        action="store_true",
        help="Affiche les réseaux GTFS trouvés dans le dossier courant puis quitte.",
    )
    parser.add_argument(
        "--list-lines",
        action="store_true",
        help="Affiche les lignes du réseau GTFS sélectionné puis quitte.",
    )
    parser.add_argument(
        "--line",
        type=str,
        default=None,
        help="Ligne à étudier. Accepte par exemple 1, D1, ou une partie du nom de ligne.",
    )
    parser.add_argument(
        "--trip-id",
        type=str,
        default=None,
        help="Trip GTFS à analyser. Si absent, le script choisit automatiquement un trip représentatif.",
    )
    parser.add_argument(
        "--route-id",
        type=str,
        default=None,
        help="Filtre route_id GTFS.",
    )
    parser.add_argument(
        "--direction-id",
        type=str,
        default=None,
        help="Filtre direction_id GTFS.",
    )
    parser.add_argument(
        "--max-segments",
        type=int,
        default=10,
        help="Nombre maximum de segments à analyser pour l'affichage.",
    )
    parser.add_argument(
        "--round-trips",
        dest="round_trip_count",
        type=int,
        default=1,
        help="Nombre d'allers-retours du trajet de référence à cumuler dans le bilan.",
    )
    parser.add_argument(
        "--bus-count",
        type=int,
        default=1,
        help="Nombre de bus à prendre en compte dans le bilan cumulé.",
    )
    parser.add_argument(
        "--disable-altimetry",
        action="store_true",
        help="Désactive l'enrichissement d'altitude depuis les tuiles IGN.",
    )
    parser.add_argument(
        "--validation-file",
        type=str,
        default=None,
        help="Fichier BD_Ligne*.xlsx utilise comme reference historique de validation.",
    )
    parser.add_argument(
        "--export-report",
        action="store_true",
        help="Génère un rapport HTML de synthèse après l’analyse.",
    )
    parser.add_argument(
        "--report-output",
        type=str,
        default=None,
        help="Chemin du rapport HTML à générer. Si absent, un fichier est créé dans exports/rapports.",
    )
    return parser.parse_args()


def resolve_gtfs_directory(args: argparse.Namespace) -> Path:
    return select_gtfs_feed(
        search_root=get_gtfs_search_root(args.data_mode),
        gtfs_path=args.gtfs_path,
        network_name=args.network,
        data_mode=args.data_mode,
        version_key=args.gtfs_version_key,
    )


def validate_selection_args(args: argparse.Namespace) -> None:
    if args.list_networks or args.list_lines:
        return

    if args.trip_id or args.route_id or args.line:
        return

    raise ValueError(
        "Aucune ligne n'a été sélectionnée. "
        "Utilisez --line <ligne>, ou a defaut --route-id <route_id> / --trip-id <trip_id>. "
        "Vous pouvez lister les lignes avec --list-lines."
    )


def should_launch_gui(args: argparse.Namespace) -> bool:
    return not any(
        [
            args.gtfs_path,
            args.network,
            args.list_networks,
            args.list_lines,
            args.line,
            args.trip_id,
            args.route_id,
        ]
    )


def build_route_labels(routes: List[Dict[str, str]]) -> List[str]:
    labels = []
    for route in routes:
        route_id = route.get("route_id", "")
        short_name = route.get("route_short_name", "")
        long_name = route.get("route_long_name", "")
        labels.append(f"{short_name} | {long_name} | route_id={route_id}")
    return labels


def build_feed_label(feed: Dict[str, str]) -> str:
    covered_area = feed.get("covered_area", "").strip()
    if covered_area:
        return f"{feed['agency_name']} | zone={covered_area}"
    return f"{feed['agency_name']} | dossier={feed['name']}"


def build_validation_label(reference: Dict[str, str]) -> str:
    return f"{reference['sheet_name']} | {Path(reference['path']).name}"


def filter_labels(labels: List[str], query: str) -> List[str]:
    normalized_query = normalize_text(query.strip())
    if not normalized_query:
        return labels
    return [label for label in labels if normalized_query in normalize_text(label)]


def Aide_sélection() -> None:
    """Affiche l’aide contextuelle de la page de sélection."""
    if messagebox is None:
        return

    messagebox.showinfo(
        "Aide - sélection",
        "Cette fenêtre permet de choisir les données à analyser.\n\n"
        "- Mode de données : utilise soit vos fichiers locaux, soit les services en ligne.\n"
        "- Réseau GTFS : tapez les premières lettres pour filtrer, par exemple « Com ».\n"
        "- Ligne : même principe pour retrouver rapidement une ligne.\n"
        "- Direction : laissez vide pour compter l'aller et le retour de la ligne, ou saisissez un direction_id pour limiter à un seul sens.\n"
        "- Nombre d'allers-retours / répétitions : multiplie le trajet de référence retenu.\n"
        "- Nombre de bus : applique le cumul à l'échelle de la flotte affectée à la ligne.\n"
        "- Validation historique : optionnel, permet de comparer le trajet actuel à un fichier BD_Ligne*.xlsx.\n"
        "- Altimétrie IGN : active ou désactive l'enrichissement du relief.\n\n"
        "Le programme choisira ensuite un trajet représentatif de la ligne sélectionnée.",
    )


def Aide_résultat() -> None:
    """Affiche l’aide contextuelle de la page de résultats."""
    if messagebox is None:
        return

    messagebox.showinfo(
        "Aide - résultats",
        "La fenêtre de résultats contient trois idées reprises de l'ancien outil :\n\n"
        "- un bloc de comparaison de scénarios de calcul,\n"
        "- des filtres pour explorer les segments importants,\n"
        "- une aide à la validation historique via les fichiers BD_Ligne*.xlsx.\n\n"
        "Utilisez l'onglet Segments pour filtrer la liste, et l'onglet Résumé pour comparer les hypothèses.",
    )


def message_erreur_appli(
    args: argparse.Namespace,
    allow_home: bool = False,
) -> argparse.Namespace | None:
    """Ouvre la fenêtre principale de sélection.

    Le nom historique est conservé pour rester compatible avec les renommages
    déjà effectués dans le projet.
    """
    if tk is None or ttk is None or messagebox is None:
        raise RuntimeError(
            "Tkinter n'est pas disponible sur cet interpreteur Python. "
            "Utilisez les arguments en ligne de commande ou installez Python avec Tk."
        )

    root = tk.Tk()
    root.withdraw()
    root.title("Sélection du réseau et de la ligne")
    apply_main_window_geometry(root)
    configure_app_theme(root)

    result: Dict[str, Any] = {"action": "cancel"}
    feeds: List[Dict[str, str]] = []
    filtered_feeds: List[Dict[str, str]] = []
    validation_references: List[Dict[str, str]] = []
    filtered_validation_references: List[Dict[str, str]] = []
    all_route_labels: List[str] = []
    filtered_route_labels: List[str] = []
    loaded_feed: Dict[str, List[Dict[str, str]]] | None = None
    loaded_gtfs_dir: Path | None = None
    selected_bus_parameters = clone_bus_parameters(
        getattr(args, "bus_parameters", BusParameters())
    )
    use_default_bus_parameters = getattr(args, "use_default_bus_parameters", True)
    create_hero_banner(
        root,
        "Préparation de l’analyse",
        "Définissez ici le périmètre d’étude et vérifiez le trajet retenu avant le lancement.",
    )
    create_path_strip(root, "Sélection")

    frame_container, frame, frame_canvas = create_vertical_scrollable_area(root, padding=16)
    frame_container.pack(fill="both", expand=True)
    frame_container.configure(style="Bus.TFrame")
    frame.configure(style="BusCard.TFrame")
    frame_canvas.configure(bg=UI_PALETTE["sand"])

    title_frame = tk.Frame(frame, bg=UI_PALETTE["white"])
    title_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    tk.Label(
        title_frame,
        text="Paramètres d’analyse",
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
    mode_var = tk.StringVar(value=args.data_mode)
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
    direction_var = tk.StringVar(value="")
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
    max_segments_var = tk.StringVar(value=str(args.max_segments))
    max_segments_entry = ttk.Entry(frame, textvariable=max_segments_var, width=10)
    max_segments_entry.grid(row=6, column=1, sticky="w", pady=6)
    ttk.Label(
        frame,
        text="La valeur proposée correspond au nombre total de segments du trajet retenu, mais reste modifiable.",
        wraplength=520,
    ).grid(row=6, column=1, sticky="w", padx=(90, 0), pady=6)

    ttk.Label(frame, text="Validation historique").grid(row=7, column=0, sticky="w", pady=6)
    validation_var = tk.StringVar(value="Aucune")
    validation_box = ttk.Combobox(
        frame,
        textvariable=validation_var,
        state="normal",
        width=70,
        values=["Aucune"],
    )
    validation_box.grid(row=7, column=1, sticky="ew", pady=6)

    altimetry_var = tk.BooleanVar(value=not args.disable_altimetry)
    altimetry_check = ttk.Checkbutton(
        frame,
        text="Activer l'altimétrie IGN",
        variable=altimetry_var,
    )
    altimetry_check.grid(row=8, column=1, sticky="w", pady=6)
    ttk.Label(
        frame,
        text=(
            "En mode local, les tuiles altimétriques téléchargées sont sélectionnées "
            "automatiquement selon l'emprise géographique du GTFS retenu."
        ),
        wraplength=520,
        justify="left",
    ).grid(row=8, column=1, sticky="w", padx=(190, 0), pady=6)

    ttk.Label(frame, text="Source altimétrique détectée").grid(row=9, column=0, sticky="nw", pady=6)
    altimetry_preview_var = tk.StringVar(
        value="Choisissez un réseau et une ligne pour déterminer automatiquement la base altimétrique."
    )
    ttk.Label(
        frame,
        textvariable=altimetry_preview_var,
        wraplength=640,
        justify="left",
    ).grid(row=9, column=1, sticky="w", pady=6)

    ttk.Label(frame, text="Paramètres du bus").grid(row=10, column=0, sticky="nw", pady=6)
    bus_summary_var = tk.StringVar(
        value=format_bus_parameters_summary(
            selected_bus_parameters,
            use_default_bus_parameters,
        )
    )
    bus_frame = tk.Frame(frame, bg=UI_PALETTE["white"])
    bus_frame.grid(row=10, column=1, sticky="ew", pady=6)
    create_secondary_button(bus_frame, "Configurer le bus", lambda: Selection_paramètres_Bus()).pack(
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
        "Vous pouvez taper les premières lèttres pour filtrer la recherche, par exemple "
        "'Com' pour retrouver Compiègne."
    )
    ttk.Label(frame, text=info_text, wraplength=640).grid(
        row=11,
        column=0,
        columnspan=2,
        sticky="w",
        pady=12,
    )

    route_maps: Dict[str, Dict[str, str]] = {}
    feed_label_map: Dict[str, Dict[str, str]] = {}
    validation_label_map: Dict[str, Dict[str, str]] = {}

    def get_feed_labels(feed_items: List[Dict[str, str]]) -> List[str]:
        return [build_feed_label(feed) for feed in feed_items]

    def find_initial_feed_label() -> str | None:
        preferred_path = str(args.gtfs_path or "")
        preferred_network = str(args.network or "")

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
        preferred_route_id = str(args.route_id or "")
        preferred_line = str(args.line or "")

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
        preferred_path = str(args.validation_file or "")
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

    def Selection_paramètres_Bus() -> None:
        """Ouvre le dialogue de configuration des paramètres du bus."""
        nonlocal selected_bus_parameters, use_default_bus_parameters
        dialog_result = show_bus_parameters_dialog(
            root,
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

        gtfs_dir = select_gtfs_feed(
            search_root=get_gtfs_search_root(mode_var.get()),
            gtfs_path=selected_feed["path"],
            network_name=selected_feed["agency_name"],
            data_mode=mode_var.get(),
            version_key=selected_feed.get("resource_updated"),
        )
        feed = load_gtfs_feed_cached(gtfs_dir)
        loaded_feed = feed
        loaded_gtfs_dir = gtfs_dir
        labels = build_route_labels(feed["routes"])
        all_route_labels = labels
        route_maps.clear()

        for label, route in zip(labels, feed["routes"]):
            route_maps[label] = route

        filter_line_options()
        if filtered_route_labels:
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
                f"{preview['stop_count']} arrêts cumulés | directions={headsign}"
            )
        else:
            trip_preview_var.set(
                "trip_id="
                f"{preview['trip_id']} | {preview['segment_count']} segments disponibles | "
                f"{preview['stop_count']} arrêts | direction={headsign}"
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
            messagebox.showerror("Erreur réseaux", str(exc))
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

        if args.direction_id:
            direction_var.set(args.direction_id)

        preferred_validation_label = find_initial_validation_label()
        if preferred_validation_label is not None:
            current_values = list(validation_box.cget("values"))
            validation_var.set(preferred_validation_label)
            if preferred_validation_label in current_values:
                validation_box.current(current_values.index(preferred_validation_label))

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
            )
            return
        selected_route = resolve_selected_route(accept_single_candidate=True)
        if selected_route is None:
            messagebox.showerror(
                "Sélection incomplète",
                "Choisissez une ligne dans la liste ou affinez la recherche.",
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
            )
            return

        try:
            max_segments = int(max_segments_var.get())
        except ValueError:
            messagebox.showerror("Valeur invalide", "Le nombre maximal de segments doit être un entier.")
            return

        args.data_mode = mode_var.get()
        args.network = selected_feed["agency_name"]
        args.gtfs_path = selected_feed["path"]
        args.gtfs_version_key = selected_feed.get("resource_updated")
        args.line = selected_route.get("route_short_name") or selected_route["route_id"]
        args.route_id = selected_route["route_id"]
        args.direction_id = direction_var.get().strip() or None
        args.max_segments = max_segments
        args.disable_altimetry = not altimetry_var.get()
        args.validation_file = None if selected_validation is None else selected_validation["path"]
        args.bus_parameters = clone_bus_parameters(selected_bus_parameters)
        args.use_default_bus_parameters = use_default_bus_parameters
        result["action"] = "confirm"
        capture_main_window_geometry(root)
        root.destroy()

    def cancel_selection() -> None:
        result["action"] = "cancel"
        capture_main_window_geometry(root)
        root.destroy()

    def return_home() -> None:
        result["action"] = "home"
        capture_main_window_geometry(root)
        root.destroy()

    buttons = tk.Frame(frame, bg=UI_PALETTE["white"])
    buttons.grid(row=12, column=0, columnspan=2, sticky="ew", pady=16)
    create_secondary_button(buttons, "Aide", Aide_sélection).pack(side="left")
    create_secondary_button(buttons, "Annuler", cancel_selection).pack(side="right")
    if allow_home:
        create_secondary_button(buttons, "Retour à l’accueil", return_home).pack(
            side="right",
            padx=8,
        )
    create_primary_button(buttons, "Lancer l’analyse", confirm_selection).pack(side="right", padx=8)

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
    root.protocol("WM_DELETE_WINDOW", cancel_selection)
    root.bind("<Return>", lambda event: confirm_selection())
    root.bind("<Escape>", lambda event: cancel_selection())
    root.after_idle(network_box.focus_set)
    root.deiconify()

    root.mainloop()

    if result["action"] == "confirm":
        return args

    if allow_home:
        return None

    if result["action"] != "confirm":
        raise SystemExit(0)


def get_trip_summaries(gtfs_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    trip_summaries = gtfs_data.get("trip_summaries")
    if trip_summaries:
        return trip_summaries

    trip = gtfs_data.get("trip", {})
    stop_names = gtfs_data.get("stop_names", [])
    return [
        {
            "trip_id": trip.get("trip_id", ""),
            "headsign": trip.get("trip_headsign", ""),
            "direction_id": trip.get("direction_id", ""),
            "stop_names": stop_names,
            "segment_count": max(len(stop_names) - 1, 0),
        }
    ]


def format_trip_selection_details(gtfs_data: Dict[str, Any]) -> str:
    trip_summaries = get_trip_summaries(gtfs_data)
    if len(trip_summaries) == 1:
        summary = trip_summaries[0]
        direction = summary.get("headsign") or summary.get("direction_id") or "N/A"
        return (
            f"Trajet GTFS sélectionné : {summary['trip_id']} | "
            f"direction={direction} | {summary['segment_count']} segments"
        )

    lines = [f"Trajets GTFS analyses : {len(trip_summaries)} (aller/retour)"]
    for summary in trip_summaries:
        direction = summary.get("headsign") or summary.get("direction_id") or "N/A"
        lines.append(
            f"- {summary['trip_id']} | direction={direction} | {summary['segment_count']} segments"
        )
    return "\n".join(lines)


def format_stop_sequences(gtfs_data: Dict[str, Any]) -> str:
    trip_summaries = get_trip_summaries(gtfs_data)
    lines: List[str] = []
    for summary in trip_summaries:
        direction = summary.get("headsign") or summary.get("direction_id") or "N/A"
        lines.append(f"{summary['trip_id']} | direction={direction}")
        lines.append("  " + " -> ".join(summary.get("stop_names", [])))
    return "\n".join(lines)


def get_reference_distance_km(results: Dict[str, Any]) -> float:
    return float(results.get("reference_total_distance_km", results.get("total_distance_km", 0.0)))


def get_reference_energy_kwh(results: Dict[str, Any]) -> float:
    return float(results.get("reference_total_energy_kwh", results.get("total_energy_kwh", 0.0)))


def get_reference_turn_energy_kwh(results: Dict[str, Any]) -> float:
    return float(results.get("reference_total_turn_energy_kwh", results.get("total_turn_energy_kwh", 0.0)))


def get_reference_turn_points(results: Dict[str, Any]) -> int:
    return int(results.get("reference_total_turn_points", results.get("total_turn_points", 0)))


def get_reference_sharp_turns(results: Dict[str, Any]) -> int:
    return int(results.get("reference_total_sharp_turns", results.get("total_sharp_turns", 0)))


def get_analysis_unit_label(results: Dict[str, Any]) -> str:
    return str(results.get("analysis_unit_label", "trajet sélectionné"))


def get_analysis_count_label(results: Dict[str, Any]) -> str:
    if get_analysis_unit_label(results) == "aller-retour":
        return "Nombre d'allers-retours"
    return "Nombre de répétitions du trajet"


def format_operation_overview(results: Dict[str, Any]) -> str:
    lines = [
        f"Unité de référence : {get_analysis_unit_label(results)}",
        f"{get_analysis_count_label(results)} : {results.get('analysis_unit_count', 1)}",
        f"Nombre de bus : {results.get('bus_count', 1)}",
        f"Multiplicateur global : {results.get('operation_multiplier', 1)}",
        f"Distance du trajet de référence : {get_reference_distance_km(results):.3f} km",
        f"Énergie du trajet de référence : {get_reference_energy_kwh(results):.4f} kWh",
        f"Distance cumulée : {results['total_distance_km']:.3f} km",
        f"Énergie cumulée : {results['total_energy_kwh']:.4f} kWh",
        f"Consommation spécifique : {results['specific_consumption_kwh_km']:.4f} kWh/km",
    ]
    return "\n".join(lines)


def format_results_summary(gtfs_data: Dict[str, Any], results: Dict[str, Any]) -> str:
    altimetry_label = gtfs_data.get(
        "altimetry_label",
        "oui" if gtfs_data.get("altimetry_enabled") else "non",
    )
    lines = [
        f"Mode de données : {gtfs_data.get('data_mode', 'local')}",
        f"Réseau GTFS : {gtfs_data['gtfs_dir']}",
        f"Route GTFS : {gtfs_data['trip'].get('route_id', '')}",
        f"Ligne courte : {gtfs_data['route'].get('route_short_name', 'N/A')}",
        f"Nom de route : {gtfs_data['route_name'] or 'N/A'}",
        format_trip_selection_details(gtfs_data),
        f"Source altimétrique : {altimetry_label}",
        format_gtfs_bounds(gtfs_data.get("gtfs_bounds")),
        f"Paramètres du bus : {'par défaut' if results.get('bus_parameters_mode') == 'default' else 'personnalisés'}",
        f"Segments analysés (trajet de référence) : {len(results['segments'])}",
        f"{get_analysis_count_label(results)} : {results.get('analysis_unit_count', 1)}",
        f"Nombre de bus : {results.get('bus_count', 1)}",
        f"Distance du trajet de référence : {get_reference_distance_km(results):.3f} km",
        f"Énergie du trajet de référence : {get_reference_energy_kwh(results):.4f} kWh",
        f"Distance cumulée : {results['total_distance_km']:.3f} km",
        f"Énergie cumulée : {results['total_energy_kwh']:.4f} kWh",
        f"Consommation spécifique : {results['specific_consumption_kwh_km']:.4f} kWh/km",
        f"Virages détectés (trajet de référence) : {get_reference_turn_points(results)}",
        f"Virages marqués (trajet de référence) : {get_reference_sharp_turns(results)}",
        f"Angle maximal détecté : {results['max_turn_angle_deg']:.1f}°",
        f"Surcoût énergétique des virages (référence) : {get_reference_turn_energy_kwh(results):.4f} kWh",
        f"Surcoût énergétique des virages (cumulé) : {results['total_turn_energy_kwh']:.4f} kWh",
        f"Validation historique : {results['historical_validation']['reference_name'] if results.get('historical_validation') else 'aucune'}",
        f"Scénarios comparés : {len(results.get('scenario_comparisons', []))}",
    ]
    return "\n".join(lines)


def format_scenario_summary(results: Dict[str, Any]) -> str:
    comparisons = results.get("scenario_comparisons", [])
    if not comparisons:
        return "Aucun scénario comparé."

    lines = []
    if results.get("operation_multiplier", 1) > 1:
        lines.append(
            "Les énergies ci-dessous sont cumulées sur l'exploitation paramétrée."
        )
    for scenario in comparisons:
        delta_text = (
            "référence"
            if scenario["is_reference"]
            else f"{scenario['delta_energy_kwh']:+.4f} kWh ({scenario['delta_energy_pct']:+.1f} %)"
        )
        lines.append(
            f"{scenario['name']} : {scenario['total_energy_kwh']:.4f} kWh | "
            f"{scenario['specific_consumption_kwh_km']:.4f} kWh/km | {delta_text}"
        )
    return "\n".join(lines)


def format_validation_summary(results: Dict[str, Any]) -> str:
    validation = results.get("historical_validation")
    if not validation:
        return "Aucune référence historique sélectionnée."

    legacy = validation["legacy"]
    current = validation["current"]
    lines = [
        f"Référence : {validation['reference_name']}",
        f"Feuille : {validation['sheet_name']}",
        f"Distance actuelle : {current['total_distance_km']:.3f} km",
        f"Distance historique : {legacy['total_distance_km']:.3f} km",
        f"Écart de distance : {validation['distance_gap_km']:+.3f} km ({validation['distance_gap_pct']:+.1f} %)",
        f"Points actuels / historiques : {current['point_count']} / {legacy['point_count']}",
        f"Arrêts actuels / historiques : {current['stop_count']} / {legacy['stop_count']}",
        f"Écart de pas moyen : {validation['mean_step_gap_m']:+.1f} m",
        f"Écart de pente absolue moyenne : {validation['mean_abs_alpha_gap_rad']:+.5f} rad",
    ]

    if validation["start_gap_m"] is not None:
        lines.append(f"Écart du point de départ : {validation['start_gap_m']:.1f} m")
    if validation["end_gap_m"] is not None:
        lines.append(f"Écart du point d'arrivée : {validation['end_gap_m']:.1f} m")
    if results.get("operation_multiplier", 1) > 1:
        lines.append(
            "La validation historique est effectuée sur le trajet de référence, avant cumul des allers-retours et des bus."
        )
    lines.append(
        "Note : la comparaison est pertinente si le trajet analysé couvre la même portion que la référence historique."
    )

    return "\n".join(lines)


def format_results_bus_parameters(results: Dict[str, Any]) -> str:
    bus_values = results.get("bus_parameters")
    if not bus_values:
        return "Les paramètres du bus ne sont pas disponibles pour cette analyse."

    bus = BusParameters(**bus_values)
    return format_bus_parameters_details(
        bus,
        results.get("bus_parameters_mode") == "default",
    )


def print_results_console(gtfs_data: Dict[str, Any], results: Dict[str, Any]) -> None:
    altimetry_label = gtfs_data.get(
        "altimetry_label",
        "oui" if gtfs_data.get("altimetry_enabled") else "non",
    )
    print("=" * 80)
    print("CONFIGURATION GTFS")
    print("=" * 80)
    print(f"Mode de données           : {gtfs_data.get('data_mode', 'local')}")
    print(f"Dossier GTFS              : {gtfs_data['gtfs_dir']}")
    print(f"Route GTFS                : {gtfs_data['trip'].get('route_id', '')}")
    print(f"Ligne courte              : {gtfs_data['route'].get('route_short_name', 'N/A')}")
    print(f"Nom de route              : {gtfs_data['route_name'] or 'N/A'}")
    print(format_trip_selection_details(gtfs_data))
    print(f"Source altimétrique       : {altimetry_label}")
    print(format_gtfs_bounds(gtfs_data.get("gtfs_bounds")))
    print(
        "Paramètres du bus         : "
        f"{'par défaut' if results.get('bus_parameters_mode') == 'default' else 'personnalisés'}"
    )
    print(f"Segments analysés         : {len(results['segments'])}")
    print(f"{get_analysis_count_label(results):24}: {results.get('analysis_unit_count', 1)}")
    print(f"Nombre de bus            : {results.get('bus_count', 1)}")
    print("Arrêts du trajet          :")
    print(format_stop_sequences(gtfs_data))
    print("Détail des paramètres     :")
    for line in format_results_bus_parameters(results).splitlines():
        print(f"  {line}")
    print()
    print("RESULTATS PAR SEGMENT")
    print("=" * 80)
    for seg in results["segments"]:
        print(f"{seg['name']}")
        print(f"  Distance                 : {seg['distance_m']:.1f} m")
        print(f"  Temps                    : {seg['time_s']:.1f} s")
        print(f"  Vitesse moyenne          : {seg['speed_km_h']:.2f} km/h")
        print(f"  Pente moyenne            : {seg['slope_rad']:.5f} rad")
        print(f"  Pente absolue moyenne    : {seg['abs_slope_rad']:.5f} rad")
        print(f"  Accélération             : {seg['acceleration_m_s2']:.4f} m/s²")
        print(f"  Puissance totale         : {seg['total_power_kw']:.2f} kW")
        print(f"  Énergie segment          : {seg['energy_kwh']:.4f} kWh")
        print(f"  Virages détectés         : {seg['turn_points_count']}")
        print(f"  Virages marqués          : {seg['sharp_turn_count']}")
        print(f"  Angle moyen virage       : {seg['weighted_turn_angle_deg']:.1f}°")
        print(f"  Angle max virage         : {seg['max_turn_angle_deg']:.1f}°")
        print(f"  Surcoût virages          : {seg['turn_energy_kwh']:.4f} kWh")
        print(f"  Source pente             : {seg['slope_source']}")
        print(f"  Source accélération      : {seg['acceleration_source']}")
        if seg["gps_points_count"] > 0:
            print(f"  Points GPS utilises      : {seg['gps_points_count']}")
            print(f"  Distance issue du GPS    : {seg['distance_from_geo_m']:.1f} m")
        print("-" * 80)

    print()
    print("=" * 80)
    print("BILAN TRAJET")
    print("=" * 80)
    print(f"Distance trajet référence   : {get_reference_distance_km(results):.3f} km")
    print(f"Énergie trajet référence    : {get_reference_energy_kwh(results):.4f} kWh")
    print(f"Distance cumulée            : {results['total_distance_km']:.3f} km")
    print(f"Énergie cumulée             : {results['total_energy_kwh']:.4f} kWh")
    print(f"Consommation spécifique     : {results['specific_consumption_kwh_km']:.4f} kWh/km")
    print(f"Virages détectés (réf.)     : {get_reference_turn_points(results)}")
    print(f"Virages marqués (réf.)      : {get_reference_sharp_turns(results)}")
    print(f"Angle max détecté           : {results['max_turn_angle_deg']:.1f}°")
    print(f"Surcoût énergie virages réf.: {get_reference_turn_energy_kwh(results):.4f} kWh")
    print(f"Surcoût énergie virages cum.: {results['total_turn_energy_kwh']:.4f} kWh")

    print()
    print("=" * 80)
    print("SCENARIOS DE CALCUL")
    print("=" * 80)
    print(format_scenario_summary(results))

    print()
    print("=" * 80)
    print("VALIDATION HISTORIQUE")
    print("=" * 80)
    print(format_validation_summary(results))


def show_results_gui(
    gtfs_data: Dict[str, Any],
    results: Dict[str, Any],
    allow_home: bool = False,
) -> str:
    if tk is None or ttk is None:
        return "close"

    root = tk.Tk()
    root.withdraw()
    root.title("Résultats de l’analyse")
    apply_main_window_geometry(root)
    configure_app_theme(root)
    result_state = {"action": "close"}

    def Fermer_résultat() -> None:
        """Ferme la fenêtre de résultats en mémorisant sa géométrie."""
        result_state["action"] = "close"
        capture_main_window_geometry(root)
        root.destroy()

    def Retour_sélection() -> None:
        """Revient à la sélection en conservant la taille de fenêtre courante."""
        result_state["action"] = "back"
        capture_main_window_geometry(root)
        root.destroy()

    def Retour_accueil() -> None:
        """Revient à l’accueil en conservant la taille de fenêtre courante."""
        result_state["action"] = "home"
        capture_main_window_geometry(root)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", Fermer_résultat)

    route_label = gtfs_data["route"].get("route_short_name", "") or gtfs_data["trip"].get("route_id", "")
    create_hero_banner(
        root,
        f"Résultats de la ligne {route_label}",
        "Le calcul est terminé. Consultez le bilan, comparez les scénarios et explorez les segments filtrés.",
    )
    create_path_strip(root, "Résultats")

    metrics_bar = tk.Frame(root, bg=UI_PALETTE["sand"])
    metrics_bar.pack(fill="x", padx=20, pady=(0, 12))
    create_metric_tile(metrics_bar, "Distance totale", f"{results['total_distance_km']:.3f} km").pack(
        side="left",
        padx=(0, 10),
    )
    create_metric_tile(metrics_bar, "Énergie totale", f"{results['total_energy_kwh']:.4f} kWh").pack(
        side="left",
        padx=(0, 10),
    )
    create_metric_tile(
        metrics_bar,
        "Consommation spécifique",
        f"{results['specific_consumption_kwh_km']:.4f} kWh/km",
        width=220,
    ).pack(side="left")

    toolbar = tk.Frame(root, bg=UI_PALETTE["sand"])
    toolbar.pack(fill="x", padx=20, pady=(0, 10))
    create_secondary_button(toolbar, "Aide", Aide_résultat).pack(side="left")
    create_secondary_button(toolbar, "Fermer", Fermer_résultat).pack(side="right")
    if allow_home:
        create_secondary_button(toolbar, "Retour à l’accueil", Retour_accueil).pack(
            side="right",
            padx=(0, 8),
        )
    create_primary_button(toolbar, "Retour à la sélection", Retour_sélection).pack(
        side="right",
        padx=(0, 8),
    )

    notebook = ttk.Notebook(root, style="BusNotebook.TNotebook")
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

    summary_frame = ttk.LabelFrame(summary_content, text="Résumé général", padding=10, style="Bus.TLabelframe")
    summary_frame.pack(fill="x", expand=False)
    summary_text = tk.Text(summary_frame)
    summary_text.insert("1.0", format_results_summary(gtfs_data, results))
    configure_readonly_text(summary_text, height=9)
    summary_text.configure(state="disabled")
    summary_text.pack(fill="x", expand=True)

    trip_summary_frame = ttk.LabelFrame(summary_content, text="Bilan trajet", padding=10, style="Bus.TLabelframe")
    trip_summary_frame.pack(fill="x", expand=False, pady=10)
    trip_summary_text = tk.Text(trip_summary_frame)
    trip_summary_text.insert(
        "1.0",
        "\n".join(
            [
                f"Distance totale : {results['total_distance_km']:.3f} km",
                f"Énergie totale : {results['total_energy_kwh']:.4f} kWh",
                f"Consommation spécifique : {results['specific_consumption_kwh_km']:.4f} kWh/km",
            ]
        ),
    )
    configure_readonly_text(trip_summary_text, height=4)
    trip_summary_text.configure(state="disabled")
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
    configure_readonly_text(bus_text, height=8)
    bus_text.configure(state="disabled")
    bus_text.pack(fill="x", expand=True)

    compare_frame = ttk.Frame(summary_content)
    compare_frame.pack(fill="both", expand=True, pady=10)
    compare_frame.columnconfigure(0, weight=1)
    compare_frame.columnconfigure(1, weight=1)
    compare_frame.rowconfigure(0, weight=1)

    scenario_frame = ttk.LabelFrame(compare_frame, text="Comparaison de scénarios", padding=10, style="Bus.TLabelframe")
    scenario_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
    scenario_frame.columnconfigure(0, weight=1)
    scenario_frame.rowconfigure(1, weight=1)

    scenario_text = tk.Text(scenario_frame)
    scenario_text.insert("1.0", format_scenario_summary(results))
    configure_readonly_text(scenario_text, height=4)
    scenario_text.configure(state="disabled")
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
            "reference"
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

    validation_frame = ttk.LabelFrame(compare_frame, text="Validation historique", padding=10, style="Bus.TLabelframe")
    validation_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
    validation_text = tk.Text(validation_frame)
    validation_text.insert("1.0", format_validation_summary(results))
    configure_readonly_text(validation_text, height=14)
    validation_text.configure(state="disabled")
    validation_text.pack(fill="both", expand=True)

    stops_frame = ttk.LabelFrame(summary_content, text="Arrêts du trajet", padding=10, style="Bus.TLabelframe")
    stops_frame.pack(fill="x", expand=False, pady=10)

    stops_text = tk.Text(stops_frame)
    stops_text.insert("1.0", format_stop_sequences(gtfs_data))
    configure_readonly_text(stops_text, height=4)
    stops_text.configure(state="disabled")
    stops_text.pack(fill="x", expand=True)

    filter_frame = ttk.LabelFrame(segments_content, text="Filtres", padding=10, style="Bus.TLabelframe")
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
        values=["Tous", "Avec virages", "Virages marques", "Sans virage"],
    )
    turn_filter_box.grid(row=0, column=3, sticky="w", padx=(0, 12))

    ttk.Label(filter_frame, text="Pente abs. min. (rad)").grid(row=0, column=4, sticky="w", padx=(0, 6))
    min_slope_var = tk.StringVar(value="0.0")
    min_slope_entry = ttk.Entry(filter_frame, textvariable=min_slope_var, width=10)
    min_slope_entry.grid(row=0, column=5, sticky="w", padx=(0, 12))

    filter_info_var = tk.StringVar(value="")
    ttk.Label(filter_frame, textvariable=filter_info_var).grid(row=0, column=6, sticky="e")

    table_frame = ttk.LabelFrame(segments_content, text="Segments", padding=10, style="Bus.TLabelframe")
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
    tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=16, style="Bus.Treeview")
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

    def Comparaison_scénarios(*_: Any) -> None:
        scenario_canvas.delete("all")
        comparisons = results.get("scenario_comparisons", [])
        visible_width = max(scenario_canvas.winfo_width(), 560)
        visible_height = max(scenario_canvas.winfo_height(), 280)

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
            text="Énergie totale par scénario",
            fill=UI_PALETTE["ink"],
            font=("Bahnschrift SemiBold", 12),
        )
        scenario_canvas.create_text(
            24,
            38,
            anchor="w",
            text="Lecture verticale avec défilement local si la liste des scénarios s’allonge.",
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

    def défilement_scénarios(event: Any) -> str:
        delta = getattr(event, "delta", 0)
        if not delta:
            return "break"
        scenario_canvas.yview_scroll(int(-delta / 120), "units")
        return "break"

    def Filtres_segment(segment: Dict[str, Any]) -> bool:
        search_text = normalize_text(search_var.get().strip())
        if search_text and search_text not in normalize_text(segment["name"]):
            return False

        filter_value = turn_filter_var.get()
        if filter_value == "Avec virages" and segment["turn_points_count"] <= 0:
            return False
        if filter_value == "Virages marques" and segment["sharp_turn_count"] <= 0:
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

        filtered_segments = [segment for segment in results["segments"] if Filtres_segment(segment)]
        filter_info_var.set(f"{len(filtered_segments)} segment(s) affiches")

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
        row=0, column=7, sticky="e", padx=(12, 0)
    )

    search_var.trace_add("write", refresh_segments_table)
    min_slope_var.trace_add("write", refresh_segments_table)
    turn_filter_box.bind("<<ComboboxSelected>>", refresh_segments_table)
    scenario_canvas.bind("<Configure>", Comparaison_scénarios)
    scenario_canvas.bind("<MouseWheel>", défilement_scénarios)
    bind_canvas_mousewheel(summary_content, summary_canvas)
    bind_canvas_mousewheel(segments_content, segments_canvas)

    refresh_segments_table()
    root.after(50, Comparaison_scénarios)
    root.bind("<Escape>", lambda event: Fermer_résultat())
    root.deiconify()
    root.mainloop()
    return result_state["action"]
