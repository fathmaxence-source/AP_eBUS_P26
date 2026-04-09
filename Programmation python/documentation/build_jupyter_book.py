import os
import runpy
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
BOOK_DIR = BASE_DIR / "jupyter_book_outil_bus"
NODE_DIR = BASE_DIR / ".jb_node" / "Scripts"
MYST_CONFIG = BOOK_DIR / "myst.yml"


def main() -> None:
    if not BOOK_DIR.exists():
        raise FileNotFoundError(f"Dossier du livre introuvable : {BOOK_DIR}")

    if not MYST_CONFIG.exists():
        raise FileNotFoundError(
            "Configuration MyST introuvable. Le fichier attendu est : "
            f"{MYST_CONFIG}"
        )

    if not NODE_DIR.exists():
        raise FileNotFoundError(
            "Node.js local introuvable. Le dossier attendu est : "
            f"{NODE_DIR}"
        )

    os.environ["PATH"] = str(NODE_DIR) + os.pathsep + os.environ.get("PATH", "")
    os.chdir(BOOK_DIR)

    cli_args = sys.argv[1:] if len(sys.argv) > 1 else ["build", "--html"]
    sys.argv = ["jupyter-book", *cli_args]
    runpy.run_module("jupyter_book", run_name="__main__")


if __name__ == "__main__":
    main()
