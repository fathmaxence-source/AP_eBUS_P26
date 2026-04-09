import csv
import hashlib
import json
import shutil
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from zipfile import BadZipFile, ZipFile

from altimetry_services import compute_geographic_bounds, enrich_points_with_altitude, has_altimetry_source
from app_models import AltimetryDataset, OnlineAltimetrySource
from energy_logic import haversine_distance_m
from network_utils import read_url_bytes, read_url_text


GTFS_REQUIRED_FILES = ("stops.txt", "stop_times.txt", "trips.txt")
TRANSPORT_DATA_DATASETS_API_URL = "https://transport.data.gouv.fr/api/datasets"
ONLINE_GTFS_CACHE_DIR = Path(".cache") / "online_gtfs"


def parse_float(value: Optional[str], default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    return float(value)


def parse_int(value: Optional[str], default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(value)


def parse_gtfs_time_to_seconds(time_value: str) -> int:
    hours_str, minutes_str, seconds_str = time_value.split(":")
    return int(hours_str) * 3600 + int(minutes_str) * 60 + int(seconds_str)


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return without_accents.casefold()


def is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def fetch_json(url: str) -> Any:
    return json.loads(read_url_text(url, timeout=30))


def sanitize_cache_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in normalize_text(value))
    compact = "_".join(part for part in cleaned.split("_") if part)
    return compact or "feed"


def choose_gtfs_resource(dataset: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    scored_resources = []
    for resource in dataset.get("resources", []):
        if not resource.get("is_available", True):
            continue

        format_value = normalize_text(str(resource.get("format", "")))
        title_value = normalize_text(resource.get("title", ""))
        original_url = normalize_text(resource.get("original_url", ""))
        if "gtfs-rt" in format_value or "gtfsrt" in format_value:
            continue
        if "gtfs" not in format_value and "gtfs" not in title_value and "gtfs" not in original_url:
            continue

        score = 0
        if format_value == "gtfs":
            score += 4
        if normalize_text(resource.get("type", "")) == "main":
            score += 2
        if str(resource.get("url", "")).endswith("/download"):
            score += 1
        scored_resources.append((score, resource))

    if not scored_resources:
        return None

    scored_resources.sort(key=lambda item: item[0], reverse=True)
    return scored_resources[0][1]


def discover_online_gtfs_feeds() -> List[Dict[str, str]]:
    datasets = fetch_json(TRANSPORT_DATA_DATASETS_API_URL)
    feeds = []

    for dataset in datasets:
        resource = choose_gtfs_resource(dataset)
        if resource is None:
            continue

        covered_area = ", ".join(
            area.get("nom", "")
            for area in dataset.get("covered_area", [])
            if area.get("nom")
        )
        publisher_name = dataset.get("publisher", {}).get("name", "")
        feeds.append(
            {
                "name": dataset.get("slug", "") or str(dataset.get("id", "")),
                "agency_name": dataset.get("title", "") or publisher_name or "Reseau GTFS",
                "path": resource.get("url", ""),
                "page_url": dataset.get("page_url", ""),
                "covered_area": covered_area,
                "publisher_name": publisher_name,
                "resource_id": str(resource.get("id", "")),
                "resource_updated": resource.get("updated", ""),
                "source": "online",
            }
        )

    feeds.sort(key=lambda feed: normalize_text(feed["agency_name"]))
    return feeds


def find_gtfs_directories(search_root: Path) -> List[Path]:
    directories: List[Path] = []

    for candidate in search_root.rglob("*"):
        if candidate.is_dir() and all((candidate / filename).exists() for filename in GTFS_REQUIRED_FILES):
            directories.append(candidate)

    return sorted(set(directories))


def load_csv_rows(file_path: Path) -> List[Dict[str, str]]:
    with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def load_agency_name(gtfs_dir: Path) -> str:
    agency_path = gtfs_dir / "agency.txt"
    if not agency_path.exists():
        return gtfs_dir.name

    agencies = load_csv_rows(agency_path)
    if not agencies:
        return gtfs_dir.name

    return agencies[0].get("agency_name") or gtfs_dir.name


def discover_gtfs_feeds(search_root: Path, data_mode: str = "local") -> List[Dict[str, str]]:
    if data_mode == "online":
        return discover_online_gtfs_feeds()

    return [
        {
            "name": gtfs_dir.name,
            "agency_name": load_agency_name(gtfs_dir),
            "path": str(gtfs_dir),
            "source": "local",
        }
        for gtfs_dir in find_gtfs_directories(search_root)
    ]


def resolve_extracted_gtfs_directory(extract_root: Path) -> Path:
    if all((extract_root / filename).exists() for filename in GTFS_REQUIRED_FILES):
        return extract_root

    candidates = find_gtfs_directories(extract_root)
    if not candidates:
        raise FileNotFoundError(
            "Le fichier GTFS telecharge ne contient pas de dossier valide avec "
            "stops.txt, stop_times.txt et trips.txt."
        )

    candidates.sort(key=lambda candidate: (len(candidate.parts), len(str(candidate))))
    return candidates[0]


def download_online_gtfs_feed(
    download_url: str,
    search_root: Path,
    feed_name: str,
    version_key: str = "",
) -> Path:
    cache_root = search_root / ONLINE_GTFS_CACHE_DIR
    cache_root.mkdir(parents=True, exist_ok=True)

    url_hash = hashlib.sha1(download_url.encode("utf-8")).hexdigest()[:12]
    version_hash = hashlib.sha1(version_key.encode("utf-8")).hexdigest()[:8] if version_key else "noversion"
    feed_cache_dir = cache_root / f"{sanitize_cache_name(feed_name)}_{url_hash}_{version_hash}"
    zip_path = feed_cache_dir / "feed.zip"
    extract_root = feed_cache_dir / "extracted"
    metadata_path = feed_cache_dir / "metadata.json"

    metadata = {
        "download_url": download_url,
        "version_key": version_key,
    }

    if metadata_path.exists() and zip_path.exists() and extract_root.exists():
        try:
            cached_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if cached_metadata == metadata:
                return resolve_extracted_gtfs_directory(extract_root)
        except (json.JSONDecodeError, OSError, FileNotFoundError):
            pass

    feed_cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(read_url_bytes(download_url, timeout=60))

    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    try:
        with ZipFile(zip_path) as gtfs_zip:
            gtfs_zip.extractall(extract_root)
    except BadZipFile as exc:
        raise ValueError(
            "La ressource GTFS telechargee n'est pas une archive ZIP valide."
        ) from exc

    metadata_path.write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")
    return resolve_extracted_gtfs_directory(extract_root)


def select_gtfs_feed(
    search_root: Path,
    gtfs_path: Optional[str] = None,
    network_name: Optional[str] = None,
    data_mode: str = "local",
    version_key: Optional[str] = None,
) -> Path:
    if gtfs_path:
        if is_url(gtfs_path):
            return download_online_gtfs_feed(
                download_url=gtfs_path,
                search_root=search_root,
                feed_name=network_name or "gtfs_online",
                version_key=version_key or "",
            )
        candidate = Path(gtfs_path)
        if not candidate.is_absolute():
            candidate = search_root / candidate
        return candidate

    feeds = discover_gtfs_feeds(search_root, data_mode=data_mode)
    if not feeds:
        if data_mode == "online":
            raise FileNotFoundError("Aucun reseau GTFS en ligne n'a ete trouve via l'API.")
        raise FileNotFoundError(
            "Aucun dossier GTFS trouve dans le repertoire courant. "
            "Ajoutez un dossier contenant au minimum stops.txt, stop_times.txt et trips.txt."
        )

    if network_name:
        keyword = normalize_text(network_name)
        matches = [
            feed
            for feed in feeds
            if keyword in normalize_text(feed["name"])
            or keyword in normalize_text(feed["agency_name"])
            or keyword in normalize_text(feed.get("covered_area", ""))
            or keyword in normalize_text(feed.get("publisher_name", ""))
        ]
        if len(matches) == 1:
            selected_feed = matches[0]
            if data_mode == "online":
                return download_online_gtfs_feed(
                    download_url=selected_feed["path"],
                    search_root=search_root,
                    feed_name=selected_feed["agency_name"],
                    version_key=selected_feed.get("resource_updated", ""),
                )
            return Path(selected_feed["path"])
        if len(matches) > 1:
            available = ", ".join(feed["agency_name"] for feed in matches)
            raise ValueError(f"Plusieurs reseaux correspondent a '{network_name}' : {available}")
        raise ValueError(f"Aucun reseau GTFS ne correspond a '{network_name}'.")

    if len(feeds) == 1:
        selected_feed = feeds[0]
        if data_mode == "online":
            return download_online_gtfs_feed(
                download_url=selected_feed["path"],
                search_root=search_root,
                feed_name=selected_feed["agency_name"],
                version_key=selected_feed.get("resource_updated", ""),
            )
        return Path(selected_feed["path"])

    available = ", ".join(f"{feed['agency_name']} [{feed['name']}]" for feed in feeds)
    raise ValueError(
        "Plusieurs reseaux GTFS sont disponibles. "
        f"Utilisez --network pour choisir l'un des reseaux suivants : {available}"
    )


def load_gtfs_feed(gtfs_dir: Path) -> Dict[str, List[Dict[str, str]]]:
    missing_files = [filename for filename in GTFS_REQUIRED_FILES if not (gtfs_dir / filename).exists()]
    if missing_files:
        raise FileNotFoundError(
            f"Dossier GTFS invalide : fichiers manquants : {', '.join(missing_files)}"
        )

    feed = {
        "stops": load_csv_rows(gtfs_dir / "stops.txt"),
        "stop_times": load_csv_rows(gtfs_dir / "stop_times.txt"),
        "trips": load_csv_rows(gtfs_dir / "trips.txt"),
    }

    shapes_path = gtfs_dir / "shapes.txt"
    feed["shapes"] = load_csv_rows(shapes_path) if shapes_path.exists() else []

    routes_path = gtfs_dir / "routes.txt"
    feed["routes"] = load_csv_rows(routes_path) if routes_path.exists() else []
    return feed


def build_stop_index(stops: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    stop_index: Dict[str, Dict[str, Any]] = {}

    for stop in stops:
        stop_id = stop["stop_id"]
        altitude_m = parse_float(
            stop.get("stop_altitude_m"),
            parse_float(stop.get("elevation_m"), 0.0),
        )

        stop_index[stop_id] = {
            "stop_id": stop_id,
            "stop_name": stop.get("stop_name", stop_id),
            "lat": parse_float(stop.get("stop_lat")),
            "lon": parse_float(stop.get("stop_lon")),
            "altitude_m": altitude_m,
        }

    return stop_index


def build_trips_index(trips: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {trip["trip_id"]: trip for trip in trips}


def build_routes_index(routes: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {route["route_id"]: route for route in routes}


def build_shapes_index(shapes: List[Dict[str, str]]) -> Dict[str, List[Dict[str, Any]]]:
    shapes_index: Dict[str, List[Dict[str, Any]]] = {}

    for row in shapes:
        shape_id = row["shape_id"]
        altitude_m = parse_float(
            row.get("shape_pt_altitude_m"),
            parse_float(row.get("elevation_m"), 0.0),
        )
        shapes_index.setdefault(shape_id, []).append(
            {
                "lat": parse_float(row["shape_pt_lat"]),
                "lon": parse_float(row["shape_pt_lon"]),
                "sequence": parse_int(row["shape_pt_sequence"]),
                "shape_dist_traveled": parse_float(row.get("shape_dist_traveled"), 0.0),
                "altitude_m": altitude_m,
            }
        )

    for shape_points in shapes_index.values():
        shape_points.sort(key=lambda point: point["sequence"])

    return shapes_index


def build_stop_times_index(stop_times: List[Dict[str, str]]) -> Dict[str, List[Dict[str, Any]]]:
    stop_times_index: Dict[str, List[Dict[str, Any]]] = {}

    for row in stop_times:
        stop_times_index.setdefault(row["trip_id"], []).append(
            {
                **row,
                "stop_sequence": parse_int(row["stop_sequence"]),
                "arrival_seconds": parse_gtfs_time_to_seconds(row["arrival_time"]),
                "departure_seconds": parse_gtfs_time_to_seconds(row["departure_time"]),
                "shape_dist_traveled": parse_float(row.get("shape_dist_traveled"), -1.0),
            }
        )

    for trip_stop_times in stop_times_index.values():
        trip_stop_times.sort(key=lambda row: row["stop_sequence"])

    return stop_times_index


def select_trip(
    trips: List[Dict[str, str]],
    stop_times_index: Dict[str, List[Dict[str, Any]]],
    trip_id: Optional[str] = None,
    route_id: Optional[str] = None,
    direction_id: Optional[str] = None,
) -> Dict[str, str]:
    if trip_id is not None:
        for trip in trips:
            if trip["trip_id"] == trip_id:
                return trip
        raise ValueError(f"Trip introuvable : {trip_id}")

    candidates = []
    for trip in trips:
        if route_id is not None and trip.get("route_id") != route_id:
            continue
        if direction_id is not None and trip.get("direction_id") != direction_id:
            continue
        if trip["trip_id"] not in stop_times_index:
            continue
        candidates.append(trip)

    if not candidates:
        raise ValueError("Aucun trip GTFS ne correspond aux filtres demandes.")

    candidates.sort(key=lambda trip: len(stop_times_index[trip["trip_id"]]), reverse=True)
    return candidates[0]


def build_trip_group_key(trip: Dict[str, str]) -> str:
    direction_value = trip.get("direction_id", "").strip()
    if direction_value:
        return f"direction:{direction_value}"

    headsign_value = normalize_text(trip.get("trip_headsign", "").strip())
    if headsign_value:
        return f"headsign:{headsign_value}"

    return f"trip:{trip['trip_id']}"


def select_trips_for_analysis(
    trips: List[Dict[str, str]],
    stop_times_index: Dict[str, List[Dict[str, Any]]],
    trip_id: Optional[str] = None,
    route_id: Optional[str] = None,
    direction_id: Optional[str] = None,
) -> List[Dict[str, str]]:
    if trip_id is not None:
        return [
            select_trip(
                trips=trips,
                stop_times_index=stop_times_index,
                trip_id=trip_id,
                route_id=route_id,
                direction_id=direction_id,
            )
        ]

    if direction_id is not None or route_id is None:
        return [
            select_trip(
                trips=trips,
                stop_times_index=stop_times_index,
                route_id=route_id,
                direction_id=direction_id,
            )
        ]

    grouped_candidates: Dict[str, List[Dict[str, str]]] = {}
    for trip in trips:
        if trip.get("route_id") != route_id:
            continue
        if trip["trip_id"] not in stop_times_index:
            continue
        grouped_candidates.setdefault(build_trip_group_key(trip), []).append(trip)

    if not grouped_candidates:
        raise ValueError("Aucun trip GTFS ne correspond a la ligne selectionnee.")

    if len(grouped_candidates) == 1:
        return [
            select_trip(
                trips=trips,
                stop_times_index=stop_times_index,
                route_id=route_id,
                direction_id=None,
            )
        ]

    selected_trips: List[Dict[str, str]] = []
    for _, candidates in sorted(grouped_candidates.items(), key=lambda item: item[0]):
        candidates.sort(
            key=lambda trip: len(stop_times_index.get(trip["trip_id"], [])),
            reverse=True,
        )
        selected_trips.append(candidates[0])
    return selected_trips


def preview_trip_selection(
    feed: Dict[str, List[Dict[str, str]]],
    trip_id: Optional[str] = None,
    route_id: Optional[str] = None,
    line_selector: Optional[str] = None,
    direction_id: Optional[str] = None,
) -> Dict[str, Any]:
    stop_times_index = build_stop_times_index(feed["stop_times"])
    resolved_route_id = route_id or resolve_route_id_from_selector(feed["routes"], line_selector)
    selected_trips = select_trips_for_analysis(
        trips=feed["trips"],
        stop_times_index=stop_times_index,
        trip_id=trip_id,
        route_id=resolved_route_id,
        direction_id=direction_id,
    )

    trip_summaries = []
    total_segment_count = 0
    total_stop_count = 0
    for trip in selected_trips:
        trip_stop_times = stop_times_index[trip["trip_id"]]
        segment_count = 0
        for idx in range(len(trip_stop_times) - 1):
            segment_time_s = (
                trip_stop_times[idx + 1]["arrival_seconds"] - trip_stop_times[idx]["departure_seconds"]
            )
            if segment_time_s > 0:
                segment_count += 1

        total_segment_count += segment_count
        total_stop_count += len(trip_stop_times)
        trip_summaries.append(
            {
                "trip_id": trip["trip_id"],
                "route_id": trip.get("route_id", ""),
                "headsign": trip.get("trip_headsign", ""),
                "direction_id": trip.get("direction_id", ""),
                "stop_count": len(trip_stop_times),
                "segment_count": segment_count,
            }
        )

    headsigns = [summary["headsign"] or summary["direction_id"] for summary in trip_summaries]

    return {
        "trip_id": selected_trips[0]["trip_id"],
        "trip_ids": [trip["trip_id"] for trip in selected_trips],
        "trip_count": len(selected_trips),
        "route_id": selected_trips[0].get("route_id", ""),
        "headsign": " / ".join(headsign for headsign in headsigns if headsign),
        "direction_id": selected_trips[0].get("direction_id", ""),
        "stop_count": total_stop_count,
        "segment_count": total_segment_count,
        "trip_summaries": trip_summaries,
    }


def compute_selected_gtfs_bounds_from_feed(
    feed: Dict[str, List[Dict[str, str]]],
    trip_id: Optional[str] = None,
    route_id: Optional[str] = None,
    line_selector: Optional[str] = None,
    direction_id: Optional[str] = None,
) -> Optional[Dict[str, float]]:
    stops_index = build_stop_index(feed["stops"])
    stop_times_index = build_stop_times_index(feed["stop_times"])
    shapes_index = build_shapes_index(feed["shapes"])
    resolved_route_id = route_id or resolve_route_id_from_selector(feed["routes"], line_selector)

    selected_trips = select_trips_for_analysis(
        trips=feed["trips"],
        stop_times_index=stop_times_index,
        trip_id=trip_id,
        route_id=resolved_route_id,
        direction_id=direction_id,
    )

    coordinates: List[tuple[float, float]] = []
    for trip in selected_trips:
        for stop_time in stop_times_index.get(trip["trip_id"], []):
            stop = stops_index.get(stop_time["stop_id"])
            if not stop:
                continue
            coordinates.append((stop["lat"], stop["lon"]))

        for point in shapes_index.get(trip.get("shape_id", ""), []):
            coordinates.append((point["lat"], point["lon"]))

    if not coordinates:
        for stop in stops_index.values():
            coordinates.append((stop["lat"], stop["lon"]))

    return compute_geographic_bounds(coordinates)


def compute_selected_gtfs_bounds(
    gtfs_dir: Path,
    trip_id: Optional[str] = None,
    route_id: Optional[str] = None,
    line_selector: Optional[str] = None,
    direction_id: Optional[str] = None,
) -> Optional[Dict[str, float]]:
    feed = load_gtfs_feed(gtfs_dir)
    return compute_selected_gtfs_bounds_from_feed(
        feed=feed,
        trip_id=trip_id,
        route_id=route_id,
        line_selector=line_selector,
        direction_id=direction_id,
    )


def resolve_route_id_from_selector(
    routes: List[Dict[str, str]],
    line_selector: Optional[str],
) -> Optional[str]:
    if line_selector is None:
        return None

    keyword = normalize_text(line_selector)
    exact_matches = []
    partial_matches = []
    for route in routes:
        route_id = route.get("route_id", "")
        route_short_name = route.get("route_short_name", "")
        route_long_name = route.get("route_long_name", "")

        if any(keyword == normalize_text(value) for value in (route_id, route_short_name)):
            exact_matches.append(route)
            continue

        if any(keyword in normalize_text(value) for value in (route_id, route_short_name, route_long_name)):
            partial_matches.append(route)

    if len(exact_matches) == 1:
        return exact_matches[0]["route_id"]
    if len(exact_matches) > 1:
        available = ", ".join(
            f"{route.get('route_short_name', route['route_id'])} ({route['route_id']})"
            for route in exact_matches
        )
        raise ValueError(f"Plusieurs lignes correspondent exactement a '{line_selector}' : {available}")

    if len(partial_matches) == 1:
        return partial_matches[0]["route_id"]
    if len(partial_matches) > 1:
        available = ", ".join(
            f"{route.get('route_short_name', route['route_id'])} ({route['route_id']})"
            for route in partial_matches
        )
        raise ValueError(f"Plusieurs lignes correspondent a '{line_selector}' : {available}")

    raise ValueError(f"Aucune ligne GTFS ne correspond a '{line_selector}'.")


def build_segment_geo_points(
    start_stop_time: Dict[str, Any],
    end_stop_time: Dict[str, Any],
    start_stop: Dict[str, Any],
    end_stop: Dict[str, Any],
    shape_points: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, float]]:
    geo_points: List[Dict[str, float]] = [
        {
            "lat": start_stop["lat"],
            "lon": start_stop["lon"],
            "altitude_m": start_stop["altitude_m"],
            "time_s": float(start_stop_time["departure_seconds"]),
        }
    ]

    if shape_points and start_stop_time["shape_dist_traveled"] >= 0 and end_stop_time["shape_dist_traveled"] >= 0:
        start_dist = start_stop_time["shape_dist_traveled"]
        end_dist = end_stop_time["shape_dist_traveled"]
        if end_dist - start_dist > 0:
            for point in shape_points:
                point_dist = point["shape_dist_traveled"]
                if start_dist < point_dist < end_dist:
                    geo_points.append(
                        {
                            "lat": point["lat"],
                            "lon": point["lon"],
                            "altitude_m": point["altitude_m"],
                        }
                    )

    geo_points.append(
        {
            "lat": end_stop["lat"],
            "lon": end_stop["lon"],
            "altitude_m": end_stop["altitude_m"],
            "time_s": float(end_stop_time["arrival_seconds"]),
        }
    )
    return geo_points


def build_trip_segments(
    trip: Dict[str, str],
    stop_times_index: Dict[str, List[Dict[str, Any]]],
    stops_index: Dict[str, Dict[str, Any]],
    shapes_index: Dict[str, List[Dict[str, Any]]],
    altimetry_source: Optional[Union[AltimetryDataset, OnlineAltimetrySource]],
    max_segments: Optional[int] = None,
    current_count: int = 0,
) -> Dict[str, Any]:
    trip_stop_times = stop_times_index[trip["trip_id"]]
    shape_points = shapes_index.get(trip.get("shape_id", ""))
    raw_segments: List[Dict[str, Any]] = []

    for idx in range(len(trip_stop_times) - 1):
        if max_segments is not None and (current_count + len(raw_segments)) >= max_segments:
            break

        start_stop_time = trip_stop_times[idx]
        end_stop_time = trip_stop_times[idx + 1]
        start_stop = stops_index[start_stop_time["stop_id"]]
        end_stop = stops_index[end_stop_time["stop_id"]]
        segment_time_s = end_stop_time["arrival_seconds"] - start_stop_time["departure_seconds"]
        if segment_time_s <= 0:
            continue

        if start_stop_time["shape_dist_traveled"] >= 0 and end_stop_time["shape_dist_traveled"] >= 0:
            distance_m = end_stop_time["shape_dist_traveled"] - start_stop_time["shape_dist_traveled"]
        else:
            distance_m = haversine_distance_m(
                start_stop["lat"],
                start_stop["lon"],
                end_stop["lat"],
                end_stop["lon"],
            )

        geo_points = build_segment_geo_points(
            start_stop_time,
            end_stop_time,
            start_stop,
            end_stop,
            shape_points,
        )
        if has_altimetry_source(altimetry_source):
            geo_points = enrich_points_with_altitude(geo_points, altimetry_source)

        raw_segments.append(
            {
                "name": f"{start_stop['stop_name']} -> {end_stop['stop_name']}",
                "distance_m": max(distance_m, 0.0),
                "time_s": float(segment_time_s),
                "altitude_start_m": geo_points[0]["altitude_m"],
                "altitude_end_m": geo_points[-1]["altitude_m"],
                "geo_points": geo_points,
                "trip_id": trip["trip_id"],
                "route_id": trip.get("route_id"),
                "shape_id": trip.get("shape_id"),
                "trip_headsign": trip.get("trip_headsign", ""),
                "direction_id": trip.get("direction_id", ""),
            }
        )

    return {
        "raw_segments": raw_segments,
        "stop_names": [stops_index[row["stop_id"]]["stop_name"] for row in trip_stop_times],
        "segment_count": len(raw_segments),
    }


def build_raw_segments_from_gtfs(
    gtfs_dir: Path,
    altimetry_source: Optional[Union[AltimetryDataset, OnlineAltimetrySource]] = None,
    trip_id: Optional[str] = None,
    route_id: Optional[str] = None,
    line_selector: Optional[str] = None,
    direction_id: Optional[str] = None,
    max_segments: Optional[int] = None,
    data_mode: str = "local",
) -> Dict[str, Any]:
    feed = load_gtfs_feed(gtfs_dir)
    stops_index = build_stop_index(feed["stops"])
    trips_index = build_trips_index(feed["trips"])
    routes_index = build_routes_index(feed["routes"])
    stop_times_index = build_stop_times_index(feed["stop_times"])
    shapes_index = build_shapes_index(feed["shapes"])
    resolved_route_id = route_id or resolve_route_id_from_selector(feed["routes"], line_selector)

    selected_trips = select_trips_for_analysis(
        trips=feed["trips"],
        stop_times_index=stop_times_index,
        trip_id=trip_id,
        route_id=resolved_route_id,
        direction_id=direction_id,
    )

    raw_segments: List[Dict[str, Any]] = []
    trip_summaries = []
    for trip in selected_trips:
        if max_segments is not None and len(raw_segments) >= max_segments:
            break

        trip_result = build_trip_segments(
            trip=trip,
            stop_times_index=stop_times_index,
            stops_index=stops_index,
            shapes_index=shapes_index,
            altimetry_source=altimetry_source,
            max_segments=max_segments,
            current_count=len(raw_segments),
        )
        raw_segments.extend(trip_result["raw_segments"])
        trip_summaries.append(
            {
                "trip_id": trip["trip_id"],
                "headsign": trip.get("trip_headsign", ""),
                "direction_id": trip.get("direction_id", ""),
                "stop_names": trip_result["stop_names"],
                "segment_count": trip_result["segment_count"],
            }
        )

        if max_segments is not None and len(raw_segments) >= max_segments:
            break

    primary_trip = selected_trips[0]
    selected_route = primary_trip.get("route_id")
    selected_route_data = routes_index.get(selected_route, {})
    route_long_name = selected_route_data.get("route_long_name") or selected_route_data.get("route_short_name")

    return {
        "gtfs_dir": str(gtfs_dir),
        "trip": trips_index[primary_trip["trip_id"]],
        "trips": [trips_index[trip["trip_id"]] for trip in selected_trips],
        "trip_summaries": trip_summaries,
        "selection_mode": "round_trip" if len(selected_trips) > 1 else "single_trip",
        "route": selected_route_data,
        "route_name": route_long_name,
        "stop_names": trip_summaries[0]["stop_names"] if trip_summaries else [],
        "raw_segments": raw_segments,
        "altimetry_enabled": has_altimetry_source(altimetry_source),
        "data_mode": data_mode,
    }
