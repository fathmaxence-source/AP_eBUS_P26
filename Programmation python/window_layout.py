from __future__ import annotations

from typing import Any


MAIN_WINDOW_DEFAULT_GEOMETRY = "1260x820"
MAIN_WINDOW_MIN_WIDTH = 1160
MAIN_WINDOW_MIN_HEIGHT = 760

_current_main_window_geometry = MAIN_WINDOW_DEFAULT_GEOMETRY


def apply_main_window_geometry(window: Any) -> None:
    window.geometry(_current_main_window_geometry)
    window.minsize(MAIN_WINDOW_MIN_WIDTH, MAIN_WINDOW_MIN_HEIGHT)


def capture_main_window_geometry(window: Any) -> None:
    global _current_main_window_geometry
    try:
        _current_main_window_geometry = window.geometry()
    except Exception:
        _current_main_window_geometry = MAIN_WINDOW_DEFAULT_GEOMETRY
