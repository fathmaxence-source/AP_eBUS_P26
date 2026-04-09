from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

ASSETS_DIR = PROJECT_ROOT / "assets"
IMAGES_DIR = ASSETS_DIR / "Images"

DATA_DIR = PROJECT_ROOT / "donnees"
GTFS_DATA_DIR = DATA_DIR / "gtfs"
ALTIMETRY_DATA_DIR = DATA_DIR / "altimetrie"

DOCUMENTATION_DIR = PROJECT_ROOT / "documentation"
JUPYTER_BOOK_DIR = DOCUMENTATION_DIR / "jupyter_book_outil_bus"
JUPYTER_HTML_DIR = JUPYTER_BOOK_DIR / "_build" / "html"
JUPYTER_NODE_DIR = DOCUMENTATION_DIR / ".jb_node"
JUPYTER_BUILD_SCRIPT = DOCUMENTATION_DIR / "build_jupyter_book.py"
JUPYTER_SERVER_SCRIPT = DOCUMENTATION_DIR / "serve_jupyter_book.py"

EXPORTS_DIR = PROJECT_ROOT / "exports"

LEGACY_RUNTIME_DIR = PROJECT_ROOT / "Codes AP2025" / "Outil" / "Outil"
EMBEDDED_PYTHON = LEGACY_RUNTIME_DIR / "WPy64-31180" / "python-3.11.8.amd64" / "python.exe"


def get_gtfs_search_root(data_mode: str = "local") -> Path:
    if data_mode == "local" and GTFS_DATA_DIR.exists():
        return GTFS_DATA_DIR
    return PROJECT_ROOT


def get_altimetry_search_root() -> Path:
    if ALTIMETRY_DATA_DIR.exists():
        return ALTIMETRY_DATA_DIR
    return PROJECT_ROOT
