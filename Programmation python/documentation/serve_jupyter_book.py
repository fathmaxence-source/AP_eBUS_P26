from __future__ import annotations

import functools
import http.server
import os
import socket
import webbrowser
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
HTML_DIR = BASE_DIR / "jupyter_book_outil_bus" / "_build" / "html"
HOST = "127.0.0.1"
PORT_RANGE = range(8934, 8955)


def find_available_port() -> int:
    requested_port = os.environ.get("JUPYTER_BOOK_PORT")
    if requested_port:
        try:
            requested = int(requested_port)
        except ValueError as exc:
            raise ValueError("La variable JUPYTER_BOOK_PORT doit être un entier valide.") from exc
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            candidate.bind((HOST, requested))
        return requested

    for port in PORT_RANGE:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                candidate.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError("Aucun port disponible n'a ete trouve pour servir la documentation.")


def main() -> None:
    if not HTML_DIR.exists():
        raise FileNotFoundError(
            "La documentation HTML est introuvable. Le dossier attendu est : "
            f"{HTML_DIR}"
        )

    port = find_available_port()
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(HTML_DIR),
    )
    server = http.server.ThreadingHTTPServer((HOST, port), handler)
    url = f"http://{HOST}:{port}/"

    print("Documentation Jupyter disponible ici :")
    print(url)
    print("Fermez cette fenetre pour arreter le serveur local.")
    print()

    if os.environ.get("JUPYTER_BOOK_NO_BROWSER") != "1":
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
