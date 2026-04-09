import tkinter as tk
from tkinter import messagebox

from project_paths import IMAGES_DIR


PALETTE = {
    "ink": "#17324d",
    "steel": "#5f7892",
    "mist": "#eef4f8",
    "sand": "#f5efe6",
    "teal": "#117a8b",
    "amber": "#d98b2b",
    "night": "#0f2234",
    "white": "#ffffff",
}


def open_method_dialog(parent: tk.Tk) -> None:
    text = (
        "Chaîne de traitement retenue\n\n"
        "1. Sélection d'un réseau GTFS et d'une ligne.\n"
        "2. Reconstruction du trajet à partir des arrêts, des shapes et des horaires.\n"
        "3. Enrichissement géographique par altimétrie et métriques de virage.\n"
        "4. Calcul énergétique segmentaire et bilan de trajet.\n"
        "5. Comparaison de scénarios et validation historique éventuelle.\n\n"
        "L'outil vise une lecture d'ingénierie : hypothèses visibles, sources explicites "
        "et indicateurs directement exploitables pour une étude de dimensionnement."
    )
    messagebox.showinfo("Méthode d'analyse", text, parent=parent)


def open_scope_dialog(parent: tk.Tk) -> None:
    text = (
        "Périmètre du programme\n\n"
        "- Données GTFS locales ou en ligne\n"
        "- Altimétrie locale ou service en ligne\n"
        "- Calculs de pente, d'accélération, de virages, de puissance et d'énergie\n"
        "- Comparaison de scénarios et validation historique\n\n"
        "La page d'accueil sert uniquement à cadrer l'usage et à lancer le parcours d'analyse."
    )
    messagebox.showinfo("Périmètre de l'outil", text, parent=parent)


def create_chip(parent: tk.Widget, title: str, value: str) -> tk.Frame:
    chip = tk.Frame(
        parent,
        bg=PALETTE["white"],
        padx=14,
        pady=12,
        highlightbackground="#d7e2ea",
        highlightthickness=1,
    )
    tk.Label(
        chip,
        text=title,
        font=("Bahnschrift SemiBold", 10),
        fg=PALETTE["steel"],
        bg=PALETTE["white"],
    ).pack(anchor="w")
    tk.Label(
        chip,
        text=value,
        font=("Segoe UI Semibold", 11),
        fg=PALETTE["ink"],
        bg=PALETTE["white"],
        justify="left",
        wraplength=250,
    ).pack(anchor="w", pady=(4, 0))
    return chip


def create_card(parent: tk.Widget, title: str, body: str, accent: str) -> tk.Frame:
    card = tk.Frame(
        parent,
        bg=PALETTE["white"],
        highlightbackground="#d7e2ea",
        highlightthickness=1,
    )
    stripe = tk.Frame(card, bg=accent, width=8)
    stripe.pack(side="left", fill="y")
    body_frame = tk.Frame(card, bg=PALETTE["white"], padx=14, pady=12)
    body_frame.pack(side="left", fill="both", expand=True)
    tk.Label(
        body_frame,
        text=title,
        font=("Bahnschrift SemiBold", 13),
        fg=PALETTE["ink"],
        bg=PALETTE["white"],
    ).pack(anchor="w")
    tk.Label(
        body_frame,
        text=body,
        font=("Segoe UI", 10),
        fg=PALETTE["steel"],
        bg=PALETTE["white"],
        justify="left",
        wraplength=300,
    ).pack(anchor="w", pady=(6, 0))
    return card


def load_home_image(filename: str, max_width: int) -> tk.PhotoImage | None:
    if not IMAGES_DIR.exists():
        return None

    image_path = IMAGES_DIR / filename
    if not image_path.exists():
        image_path = None
        for candidate in IMAGES_DIR.iterdir():
            if filename.lower() in candidate.name.lower():
                image_path = candidate
                break

    if image_path is None or not image_path.exists():
        return None

    try:
        image = tk.PhotoImage(file=str(image_path))
    except tk.TclError:
        return None

    if image.width() > max_width:
        shrink_factor = max(1, -(-image.width() // max_width))
        image = image.subsample(shrink_factor, shrink_factor)

    return image


def create_logo_badge(
    parent: tk.Widget,
    image: tk.PhotoImage | None,
) -> tk.Frame:
    badge = tk.Frame(
        parent,
        bg=PALETTE["white"],
        padx=12,
        pady=12,
        highlightbackground="#d7e2ea",
        highlightthickness=1,
    )
    if image is not None:
        tk.Label(badge, image=image, bg=PALETTE["white"]).pack(anchor="center")
    else:
        tk.Label(
            badge,
            text="Image indisponible",
            font=("Segoe UI Semibold", 10),
            fg=PALETTE["steel"],
            bg=PALETTE["white"],
        ).pack(anchor="center")
    return badge
