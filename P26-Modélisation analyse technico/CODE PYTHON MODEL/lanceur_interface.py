"""
Lanceur Python dedie a l'interface du simulateur P26.

Le lanceur peut etre ouvert depuis un IDE avec n'importe quel interpreteur :
s'il manque Tkinter ou les dependances scientifiques, il cherche un Python
compatible et relance automatiquement l'interface avec celui-ci.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


MODULES_REQUIS = (
    "tkinter",
    "numpy",
    "pandas",
    "scipy",
    "matplotlib",
    "openpyxl",
)


def construire_parseur_arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lance l'interface graphique du simulateur P26.",
    )
    parser.add_argument(
        "--verifier",
        action="store_true",
        help="Verifie l'interpreteur sans ouvrir la fenetre.",
    )
    return parser


def verifier_modules_courants() -> tuple[bool, str]:
    """
    Verifie que l'interpreteur courant peut ouvrir l'interface et calculer.
    """

    for module in MODULES_REQUIS:
        try:
            __import__(module)
        except Exception as exc:  # noqa: BLE001
            return False, f"module manquant ou invalide : {module} ({exc})"
    return True, ""


def verifier_interpreteur(python_exe: Path) -> tuple[bool, str]:
    """
    Verifie un interpreteur Python sans importer ses modules ici.
    """

    if not python_exe.exists():
        return False, "fichier python.exe introuvable"

    code = "; ".join(f"import {module}" for module in MODULES_REQUIS)
    try:
        resultat = subprocess.run(
            [str(python_exe), "-c", code],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)

    if resultat.returncode == 0:
        return True, ""
    erreur = (resultat.stderr or resultat.stdout).strip()
    return False, erreur or f"code retour {resultat.returncode}"


def lister_interpreteurs_candidats() -> list[Path]:
    """
    Liste les interpreteurs a essayer si le Python courant ne suffit pas.
    """

    candidats: list[Path] = []
    variable_env = os.environ.get("P26_PYTHON_INTERFACE")
    if variable_env:
        candidats.append(Path(variable_env))

    candidats.extend(
        [
            Path.home() / "AppData" / "Local" / "spyder-6" / "python.exe",
            Path.home()
            / "AppData"
            / "Local"
            / "Programs"
            / "Python"
            / "Python313"
            / "python.exe",
        ]
    )

    chemin_courant = Path(sys.executable).resolve()
    candidats_uniques: list[Path] = []
    for candidat in candidats:
        chemin = candidat.resolve()
        if chemin == chemin_courant:
            continue
        if chemin not in candidats_uniques:
            candidats_uniques.append(chemin)
    return candidats_uniques


def trouver_interpreteur_compatible() -> Path | None:
    """
    Trouve un Python capable de lancer l'interface.
    """

    for candidat in lister_interpreteurs_candidats():
        ok, _message = verifier_interpreteur(candidat)
        if ok:
            return candidat
    return None


def relancer_avec_interpreteur(
    python_exe: Path,
    arguments: argparse.Namespace,
) -> None:
    """
    Relance ce lanceur avec un interpreteur compatible.
    """

    commande = [str(python_exe), str(Path(__file__).resolve())]
    if arguments.verifier:
        commande.append("--verifier")
    resultat = subprocess.run(commande, cwd=Path(__file__).resolve().parent)
    raise SystemExit(resultat.returncode)


def main() -> None:
    """
    Ouvre l'interface graphique depuis le dossier du projet.
    """

    arguments = construire_parseur_arguments().parse_args()
    dossier_script = Path(__file__).resolve().parent
    os.chdir(dossier_script)

    interpreteur_ok, erreur_modules = verifier_modules_courants()
    if not interpreteur_ok:
        interpreteur_compatible = trouver_interpreteur_compatible()
        if interpreteur_compatible is not None:
            print(
                "Interpreteur courant incomplet, relance avec : "
                f"{interpreteur_compatible}",
                flush=True,
            )
            relancer_avec_interpreteur(interpreteur_compatible, arguments)

        print("Interface graphique impossible avec cet interpreteur Python.")
        print(f"Interpreteur utilise : {sys.executable}")
        print(f"Erreur              : {erreur_modules}")
        print("")
        print(
            "Solution : utiliser un Python qui inclut Tkinter et les dependances "
            "du projet, ou definir P26_PYTHON_INTERFACE vers ce python.exe."
        )
        raise SystemExit(1)

    if arguments.verifier:
        print("INTERFACE_INTERPRETEUR_OK")
        print(f"Interpreteur : {sys.executable}")
        return

    from interface_simulation import lancer_interface_simulation

    lancer_interface_simulation()


if __name__ == "__main__":
    main()
