from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GTFS_MODULE_DIR = PROJECT_ROOT / "transfert_groupe_modelisation_gtfs"

if str(GTFS_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(GTFS_MODULE_DIR))

from gtfs_core import (  # noqa: E402
    build_stop_index,
    build_stop_times_index,
    default_search_root,
    discover_gtfs_feeds,
    download_online_gtfs_feed,
    haversine_distance_m,
    load_gtfs_feed,
    normalize_text,
    resolve_route_id_from_selector,
    select_gtfs_feed,
    select_trips_for_analysis,
)


@dataclass
class GTFSBusConfig:
    """
    Parametres de selection du feed GTFS et du profil de bus a simuler.
    """

    data_mode: str = "online"
    search_root: Optional[str] = None
    gtfs_path: Optional[str] = None
    network_name: str = "compiegne"
    line_selector: Optional[str] = "1"
    route_id: Optional[str] = None
    trip_id: Optional[str] = None
    direction_id: Optional[str] = None
    cycle_count: int = 8
    default_stop_duration_s: float = 30.0
    service_date: str = "2025-03-15"
    include_depot_deadhead: bool = True
    depot_deadhead_distance_m: float = 4000.0
    depot_deadhead_speed_m_s: float = 12.0
    depot_name: str = "Depot"


def _resolve_search_root(search_root: Optional[str]) -> Path:
    if search_root:
        return Path(search_root).resolve()
    return default_search_root().resolve()


def _select_gtfs_directory(config: GTFSBusConfig, search_root: Path) -> Path:
    if config.gtfs_path:
        return select_gtfs_feed(
            search_root=search_root,
            gtfs_path=config.gtfs_path,
            network_name=config.network_name,
            data_mode=config.data_mode,
        )

    if config.network_name:
        feeds = discover_gtfs_feeds(search_root, data_mode=config.data_mode)
        network_key = normalize_text(config.network_name)
        exact_matches = [
            feed
            for feed in feeds
            if network_key in {
                normalize_text(feed.get("agency_name", "")),
                normalize_text(feed.get("name", "")),
            }
        ]

        if len(exact_matches) == 1:
            selected_feed = exact_matches[0]
            if config.data_mode == "online":
                return download_online_gtfs_feed(
                    download_url=selected_feed["path"],
                    search_root=search_root,
                    feed_name=selected_feed["agency_name"],
                    version_key=selected_feed.get("resource_updated", ""),
                )
            return Path(selected_feed["path"])

    return select_gtfs_feed(
        search_root=search_root,
        gtfs_path=config.gtfs_path,
        network_name=config.network_name,
        data_mode=config.data_mode,
    )


def _compute_distance_m(
    start_stop_time: dict[str, Any],
    end_stop_time: dict[str, Any],
    start_stop: dict[str, Any],
    end_stop: dict[str, Any],
) -> float:
    if (
        start_stop_time["shape_dist_traveled"] >= 0
        and end_stop_time["shape_dist_traveled"] >= 0
    ):
        distance_m = end_stop_time["shape_dist_traveled"] - start_stop_time["shape_dist_traveled"]
    else:
        distance_m = haversine_distance_m(
            start_stop["lat"],
            start_stop["lon"],
            end_stop["lat"],
            end_stop["lon"],
        )
    return max(distance_m, 0.0)


def _build_trip_rows(
    trip: dict[str, str],
    trip_stop_times: list[dict[str, Any]],
    stops_index: dict[str, dict[str, Any]],
    default_stop_duration_s: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for index in range(len(trip_stop_times) - 1):
        start_stop_time = trip_stop_times[index]
        end_stop_time = trip_stop_times[index + 1]

        segment_time_s = end_stop_time["arrival_seconds"] - start_stop_time["departure_seconds"]
        if segment_time_s <= 0:
            continue

        start_stop = stops_index[start_stop_time["stop_id"]]
        end_stop = stops_index[end_stop_time["stop_id"]]
        distance_m = _compute_distance_m(start_stop_time, end_stop_time, start_stop, end_stop)
        speed_m_s = distance_m / segment_time_s if segment_time_s > 0 else 0.0

        rows.append(
            {
                "Stop": 1,
                "Alpha": 0.0,
                "Distance": distance_m,
                "Velocity": speed_m_s,
                "deltaT": float(segment_time_s),
                "TripID": trip["trip_id"],
                "StartStopName": start_stop["stop_name"],
                "EndStopName": end_stop["stop_name"],
            }
        )

        if index < len(trip_stop_times) - 2 and default_stop_duration_s > 0:
            rows.append(
                {
                    "Stop": 0,
                    "Alpha": 0.0,
                    "Distance": 0.0,
                    "Velocity": 0.0,
                    "deltaT": float(default_stop_duration_s),
                    "TripID": trip["trip_id"],
                    "StartStopName": end_stop["stop_name"],
                    "EndStopName": end_stop["stop_name"],
                }
            )

    return rows


def _build_depot_deadhead_row(
    start_stop_name: str,
    end_stop_name: str,
    trip_id: str,
    distance_m: float,
    speed_m_s: float,
    cycle: int,
) -> dict[str, Any]:
    delta_t_s = distance_m / speed_m_s if speed_m_s > 0 else 0.0
    return {
        "Stop": 1,
        "Alpha": 0.0,
        "Distance": float(distance_m),
        "Velocity": float(speed_m_s),
        "deltaT": float(delta_t_s),
        "TripID": trip_id,
        "StartStopName": start_stop_name,
        "EndStopName": end_stop_name,
        "Cycle": cycle,
    }


def load_single_bus_service(config: GTFSBusConfig) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Construit le profil de circulation d'un seul bus a partir du GTFS.

    Si plusieurs directions existent sur la ligne et qu'aucune direction n'est
    imposee, on prend un trajet representatif par direction pour former un cycle.
    """

    search_root = _resolve_search_root(config.search_root)
    gtfs_dir = _select_gtfs_directory(config, search_root)
    feed = load_gtfs_feed(gtfs_dir)

    stop_times_index = build_stop_times_index(feed["stop_times"])
    stops_index = build_stop_index(feed["stops"])
    resolved_route_id = config.route_id or resolve_route_id_from_selector(
        feed["routes"],
        config.line_selector,
    )

    selected_trips = select_trips_for_analysis(
        trips=feed["trips"],
        stop_times_index=stop_times_index,
        trip_id=config.trip_id,
        route_id=resolved_route_id,
        direction_id=config.direction_id,
    )
    if not selected_trips:
        raise ValueError("Aucun trajet GTFS n'a ete retenu pour la simulation.")

    cycle_rows: list[dict[str, Any]] = []
    first_departure_seconds: Optional[int] = None

    for trip_index, trip in enumerate(selected_trips):
        trip_stop_times = stop_times_index.get(trip["trip_id"], [])
        if len(trip_stop_times) < 2:
            continue

        if first_departure_seconds is None:
            first_departure_seconds = trip_stop_times[0]["departure_seconds"]

        cycle_rows.extend(
            _build_trip_rows(
                trip=trip,
                trip_stop_times=trip_stop_times,
                stops_index=stops_index,
                default_stop_duration_s=config.default_stop_duration_s,
            )
        )

        if trip_index < len(selected_trips) - 1 and config.default_stop_duration_s > 0:
            terminal_stop = stops_index[trip_stop_times[-1]["stop_id"]]
            cycle_rows.append(
                {
                    "Stop": 0,
                    "Alpha": 0.0,
                    "Distance": 0.0,
                    "Velocity": 0.0,
                    "deltaT": float(config.default_stop_duration_s),
                    "TripID": trip["trip_id"],
                    "StartStopName": terminal_stop["stop_name"],
                    "EndStopName": terminal_stop["stop_name"],
                }
            )

    if not cycle_rows or first_departure_seconds is None:
        raise ValueError("Le GTFS selectionne ne contient pas assez de segments exploitables.")

    first_stop = stops_index[stop_times_index[selected_trips[0]["trip_id"]][0]["stop_id"]]
    last_stop = stops_index[stop_times_index[selected_trips[-1]["trip_id"]][-1]["stop_id"]]
    initial_anchor_name = config.depot_name if config.include_depot_deadhead else first_stop["stop_name"]
    all_rows: list[dict[str, Any]] = [
        {
            "Stop": 0,
            "Alpha": 0.0,
            "Distance": 0.0,
            "Velocity": 0.0,
            "deltaT": 0.0,
            "TripID": selected_trips[0]["trip_id"],
            "StartStopName": initial_anchor_name,
            "EndStopName": initial_anchor_name,
            "Cycle": 0,
        }
    ]

    if config.include_depot_deadhead:
        all_rows.append(
            _build_depot_deadhead_row(
                start_stop_name=config.depot_name,
                end_stop_name=first_stop["stop_name"],
                trip_id="DEPOT_OUT",
                distance_m=config.depot_deadhead_distance_m,
                speed_m_s=config.depot_deadhead_speed_m_s,
                cycle=0,
            )
        )

    for cycle_index in range(max(config.cycle_count, 1)):
        for row in cycle_rows:
            cycle_row = row.copy()
            cycle_row["Cycle"] = cycle_index + 1
            all_rows.append(cycle_row)

    if config.include_depot_deadhead:
        all_rows.append(
            _build_depot_deadhead_row(
                start_stop_name=last_stop["stop_name"],
                end_stop_name=config.depot_name,
                trip_id="DEPOT_IN",
                distance_m=config.depot_deadhead_distance_m,
                speed_m_s=config.depot_deadhead_speed_m_s,
                cycle=max(config.cycle_count, 1) + 1,
            )
        )

    tabl = pd.DataFrame(all_rows)
    tabl["PointID"] = range(len(tabl))
    tabl["Time"] = tabl["deltaT"].cumsum()
    tabl["Total_Distance"] = tabl["Distance"].cumsum()

    route = next(
        (
            current_route
            for current_route in feed["routes"]
            if current_route.get("route_id") == selected_trips[0].get("route_id")
        ),
        {},
    )
    first_stop_departure = pd.Timestamp(config.service_date) + pd.to_timedelta(
        first_departure_seconds,
        unit="s",
    )
    deadhead_duration_s = 0.0
    if config.include_depot_deadhead and config.depot_deadhead_speed_m_s > 0:
        deadhead_duration_s = config.depot_deadhead_distance_m / config.depot_deadhead_speed_m_s
    service_start = first_stop_departure - pd.to_timedelta(deadhead_duration_s, unit="s")

    metadata = {
        "gtfs_dir": str(gtfs_dir),
        "route_id": selected_trips[0].get("route_id", ""),
        "route_short_name": route.get("route_short_name", ""),
        "route_long_name": route.get("route_long_name", ""),
        "trip_ids": [trip["trip_id"] for trip in selected_trips],
        "start_time": service_start,
        "first_stop_departure": first_stop_departure,
        "cycle_count": max(config.cycle_count, 1),
        "include_depot_deadhead": config.include_depot_deadhead,
        "depot_deadhead_distance_m": config.depot_deadhead_distance_m,
        "depot_deadhead_speed_m_s": config.depot_deadhead_speed_m_s,
    }
    return tabl, metadata
