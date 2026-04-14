"""
Lanceur Python dedie a l'interface du simulateur P26.

Ce fichier est volontairement tres court pour etre facile a ouvrir depuis
un IDE, un raccourci Python ou tout autre lanceur externe.
"""

from __future__ import annotations

import os
from pathlib import Path

from interface_simulation import lancer_interface_simulation


def main() -> None:
    """
    Ouvre l'interface graphique depuis le dossier du projet.
    """

    dossier_script = Path(__file__).resolve().parent
    os.chdir(dossier_script)
    lancer_interface_simulation()


if __name__ == "__main__":
    main()
