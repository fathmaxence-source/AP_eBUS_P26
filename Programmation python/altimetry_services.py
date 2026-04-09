import json
from math import atanh, cos, exp, radians, sin
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

from app_models import AltimetryDataset, AltimetryTile, OnlineAltimetrySource
from network_utils import read_url_text


IGN_ELEVATION_API_URL = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"
_ALTIMETRY_DISCOVERY_CACHE: Dict[str, AltimetryDataset] = {}


def wgs84_to_lambert93(lat_deg: float, lon_deg: float) -> Dict[str, float]:
    lon_rad = radians(lon_deg)
    lat_rad = radians(lat_deg)

    eccentricity = 0.0818191910428158
    n = 0.7256077650532670
    c = 11754255.426096
    lon_meridian_rad = radians(3.0)
    x_s = 700000.0
    y_s = 12655612.049876

    sin_lat = sin(lat_rad)
    lat_iso = atanh(sin_lat) - eccentricity * atanh(eccentricity * sin_lat)
    radius = c * exp(-n * lat_iso)
    angle = n * (lon_rad - lon_meridian_rad)

    x = x_s + radius * sin(angle)
    y = y_s - radius * cos(angle)
    return {"x": x, "y": y}


def parse_altimetry_header(asc_path: Path) -> AltimetryTile:
    header: Dict[str, float] = {}
    with asc_path.open("r", encoding="utf-8", newline="") as asc_file:
        for _ in range(6):
            key, value = asc_file.readline().split()
            header[key.lower()] = float(value)

    return AltimetryTile(
        path=asc_path,
        ncols=int(header["ncols"]),
        nrows=int(header["nrows"]),
        xllcorner=header["xllcorner"],
        yllcorner=header["yllcorner"],
        cellsize=header["cellsize"],
        nodata_value=header["nodata_value"],
    )


def discover_altimetry_tiles(search_root: Path) -> AltimetryDataset:
    resolved_root = str(search_root.resolve())
    if resolved_root not in _ALTIMETRY_DISCOVERY_CACHE:
        tiles = [parse_altimetry_header(asc_path) for asc_path in search_root.rglob("*.asc")]
        _ALTIMETRY_DISCOVERY_CACHE[resolved_root] = AltimetryDataset(tiles=tiles)
    return _ALTIMETRY_DISCOVERY_CACHE[resolved_root]


def create_online_altimetry_source() -> OnlineAltimetrySource:
    return OnlineAltimetrySource()


def compute_geographic_bounds(
    coordinates: List[tuple[float, float]],
) -> Optional[Dict[str, float]]:
    valid_coordinates = [
        (lat_deg, lon_deg)
        for lat_deg, lon_deg in coordinates
        if lat_deg is not None and lon_deg is not None
    ]
    if not valid_coordinates:
        return None

    latitudes = [lat_deg for lat_deg, _ in valid_coordinates]
    longitudes = [lon_deg for _, lon_deg in valid_coordinates]
    return {
        "min_lat": min(latitudes),
        "max_lat": max(latitudes),
        "min_lon": min(longitudes),
        "max_lon": max(longitudes),
    }


def compute_projected_bounds_from_geographic_bounds(
    bounds: Dict[str, float],
    padding_m: float = 1000.0,
) -> Dict[str, float]:
    corner_coordinates = [
        (bounds["min_lat"], bounds["min_lon"]),
        (bounds["min_lat"], bounds["max_lon"]),
        (bounds["max_lat"], bounds["min_lon"]),
        (bounds["max_lat"], bounds["max_lon"]),
    ]
    projected_corners = [
        wgs84_to_lambert93(lat_deg, lon_deg)
        for lat_deg, lon_deg in corner_coordinates
    ]
    x_values = [coords["x"] for coords in projected_corners]
    y_values = [coords["y"] for coords in projected_corners]
    return {
        "min_x": min(x_values) - padding_m,
        "max_x": max(x_values) + padding_m,
        "min_y": min(y_values) - padding_m,
        "max_y": max(y_values) + padding_m,
    }


def tile_intersects_projected_bounds(
    tile: AltimetryTile,
    projected_bounds: Dict[str, float],
) -> bool:
    return not (
        tile.x_max < projected_bounds["min_x"]
        or tile.xllcorner > projected_bounds["max_x"]
        or tile.y_max < projected_bounds["min_y"]
        or tile.yllcorner > projected_bounds["max_y"]
    )


def select_local_altimetry_dataset(
    search_root: Path,
    geographic_bounds: Optional[Dict[str, float]],
    padding_m: float = 1000.0,
) -> AltimetryDataset:
    discovered_dataset = discover_altimetry_tiles(search_root)
    if not discovered_dataset.tiles:
        return AltimetryDataset(tiles=[])

    if geographic_bounds is None:
        return AltimetryDataset(tiles=list(discovered_dataset.tiles))

    projected_bounds = compute_projected_bounds_from_geographic_bounds(
        geographic_bounds,
        padding_m=padding_m,
    )
    matching_tiles = [
        tile
        for tile in discovered_dataset.tiles
        if tile_intersects_projected_bounds(tile, projected_bounds)
    ]
    return AltimetryDataset(tiles=matching_tiles)


def extract_altimetry_dataset_names(
    altimetry_dataset: AltimetryDataset,
    search_root: Optional[Path] = None,
) -> List[str]:
    dataset_names: List[str] = []
    seen_names = set()

    for tile in altimetry_dataset.tiles:
        tile_path = tile.path
        dataset_name = tile_path.parent.name
        if search_root is not None:
            try:
                relative_parts = tile_path.resolve().relative_to(search_root.resolve()).parts
                if relative_parts:
                    dataset_name = relative_parts[0]
            except ValueError:
                dataset_name = tile_path.parent.name

        if dataset_name not in seen_names:
            seen_names.add(dataset_name)
            dataset_names.append(dataset_name)

    return dataset_names


def describe_altimetry_source(
    altimetry_source: Optional[Union[AltimetryDataset, OnlineAltimetrySource]],
    selection_mode: str = "auto",
    geographic_bounds: Optional[Dict[str, float]] = None,
    search_root: Optional[Path] = None,
) -> Dict[str, Any]:
    if altimetry_source is None:
        return {
            "enabled": False,
            "mode": "disabled",
            "label": "Aucune source altimétrique active",
            "tile_count": 0,
            "dataset_names": [],
            "bounds": geographic_bounds,
        }

    if isinstance(altimetry_source, OnlineAltimetrySource):
        resource_name = altimetry_source.resource
        return {
            "enabled": True,
            "mode": "online",
            "label": f"API altimétrique IGN en ligne | ressource : {resource_name}",
            "tile_count": 0,
            "dataset_names": [],
            "resource_name": resource_name,
            "bounds": geographic_bounds,
        }

    tile_count = len(altimetry_source.tiles)
    dataset_names = extract_altimetry_dataset_names(
        altimetry_source,
        search_root=search_root,
    )
    if tile_count <= 0:
        return {
            "enabled": False,
            "mode": "local_missing",
            "label": "Aucune tuile locale ne couvre la zone GTFS sélectionnée",
            "tile_count": 0,
            "dataset_names": [],
            "bounds": geographic_bounds,
        }

    if selection_mode == "auto":
        label = f"Sélection locale automatique ({tile_count} tuile(s) retenue(s))"
    else:
        label = f"Jeu local global ({tile_count} tuile(s) disponible(s))"

    if dataset_names:
        joined_names = ", ".join(dataset_names[:2])
        if len(dataset_names) > 2:
            joined_names = f"{joined_names}, +{len(dataset_names) - 2} autre(s)"
        label = f"{label} | base(s) : {joined_names}"

    return {
        "enabled": True,
        "mode": "local",
        "label": label,
        "tile_count": tile_count,
        "dataset_names": dataset_names,
        "bounds": geographic_bounds,
    }


def has_altimetry_source(
    altimetry_source: Optional[Union[AltimetryDataset, OnlineAltimetrySource]],
) -> bool:
    if altimetry_source is None:
        return False
    if isinstance(altimetry_source, AltimetryDataset):
        return bool(altimetry_source.tiles)
    return True


def load_altimetry_grid(tile: AltimetryTile) -> None:
    if tile.grid is not None:
        return

    grid: List[List[float]] = []
    with tile.path.open("r", encoding="utf-8", newline="") as asc_file:
        for _ in range(6):
            asc_file.readline()
        for line in asc_file:
            grid.append([float(value) for value in line.split()])
    tile.grid = grid


def compute_altimetry_bucket_key(
    x: float,
    y: float,
    bucket_size_m: float,
) -> tuple[int, int]:
    return (int(x // bucket_size_m), int(y // bucket_size_m))


def find_altimetry_tile(
    x: float,
    y: float,
    altimetry_dataset: AltimetryDataset,
) -> Optional[AltimetryTile]:
    if not altimetry_dataset.tiles:
        return None

    bucket_key = compute_altimetry_bucket_key(x, y, altimetry_dataset.bucket_size_m)
    if bucket_key in altimetry_dataset.tile_bucket_cache:
        return altimetry_dataset.tile_bucket_cache[bucket_key]

    for tile in altimetry_dataset.tiles:
        if tile.xllcorner <= x < tile.x_max and tile.yllcorner <= y < tile.y_max:
            altimetry_dataset.tile_bucket_cache[bucket_key] = tile
            return tile

    altimetry_dataset.tile_bucket_cache[bucket_key] = None
    return None


def sample_altitude_in_tile(
    x: float,
    y: float,
    tile: AltimetryTile,
) -> Optional[float]:
    load_altimetry_grid(tile)
    col = int((x - tile.xllcorner) / tile.cellsize)
    row_from_bottom = int((y - tile.yllcorner) / tile.cellsize)
    row = tile.nrows - 1 - row_from_bottom

    if row < 0 or row >= tile.nrows or col < 0 or col >= tile.ncols:
        return None

    altitude = tile.grid[row][col]
    if altitude == tile.nodata_value:
        return None
    return altitude


def sample_altitude_from_tiles(
    lat_deg: float,
    lon_deg: float,
    altimetry_dataset: AltimetryDataset,
) -> Optional[float]:
    if not altimetry_dataset.tiles:
        return None

    coords = wgs84_to_lambert93(lat_deg, lon_deg)
    x = coords["x"]
    y = coords["y"]
    altitude_key = (int(x), int(y))

    if altitude_key in altimetry_dataset.altitude_cache:
        return altimetry_dataset.altitude_cache[altitude_key]

    tile = find_altimetry_tile(x, y, altimetry_dataset)
    if tile is None:
        altimetry_dataset.altitude_cache[altitude_key] = None
        return None

    altitude = sample_altitude_in_tile(x, y, tile)
    altimetry_dataset.altitude_cache[altitude_key] = altitude
    return altitude


def fetch_online_altitudes(
    coordinates: List[tuple[float, float]],
    altimetry_source: OnlineAltimetrySource,
) -> Dict[tuple[float, float], Optional[float]]:
    uncached_coordinates = []
    for lat_deg, lon_deg in coordinates:
        cache_key = (round(lat_deg, 6), round(lon_deg, 6))
        if cache_key not in altimetry_source.altitude_cache:
            uncached_coordinates.append((lat_deg, lon_deg))

    for start_idx in range(0, len(uncached_coordinates), altimetry_source.batch_size):
        batch = uncached_coordinates[start_idx:start_idx + altimetry_source.batch_size]
        if not batch:
            continue

        params = urlencode(
            {
                "lon": "|".join(f"{lon_deg:.6f}" for _, lon_deg in batch),
                "lat": "|".join(f"{lat_deg:.6f}" for lat_deg, _ in batch),
                "resource": altimetry_source.resource,
                "delimiter": "|",
                "indent": "false",
                "measures": "false",
                "zonly": "false",
            }
        )
        request_url = f"{IGN_ELEVATION_API_URL}?{params}"

        payload = read_url_text(request_url, timeout=30)
        elevations = json.loads(payload).get("elevations", [])
        for elevation in elevations:
            cache_key = (round(float(elevation["lat"]), 6), round(float(elevation["lon"]), 6))
            altitude = float(elevation["z"])
            altimetry_source.altitude_cache[cache_key] = None if altitude == -99999 else altitude

    return {
        (round(lat_deg, 6), round(lon_deg, 6)): altimetry_source.altitude_cache.get(
            (round(lat_deg, 6), round(lon_deg, 6))
        )
        for lat_deg, lon_deg in coordinates
    }


def enrich_points_with_altitude(
    points: List[Dict[str, float]],
    altimetry_source: Union[AltimetryDataset, OnlineAltimetrySource],
) -> List[Dict[str, float]]:
    enriched_points: List[Dict[str, float]] = []

    online_altitudes: Dict[tuple[float, float], Optional[float]] = {}
    if isinstance(altimetry_source, OnlineAltimetrySource):
        online_altitudes = fetch_online_altitudes(
            [(point["lat"], point["lon"]) for point in points],
            altimetry_source,
        )

    for point in points:
        if isinstance(altimetry_source, AltimetryDataset):
            altitude = sample_altitude_from_tiles(point["lat"], point["lon"], altimetry_source)
        else:
            altitude = online_altitudes.get((round(point["lat"], 6), round(point["lon"], 6)))
        enriched_points.append(
            {
                **point,
                "altitude_m": altitude if altitude is not None else point.get("altitude_m", 0.0),
            }
        )

    return enriched_points
