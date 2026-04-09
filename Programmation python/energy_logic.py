from math import asin, atan2, cos, degrees, radians, sin, sqrt
from statistics import mean
from typing import Any, Dict, List, Optional

from app_models import BusParameters, GeoPoint


TURN_ANGLE_THRESHOLD_DEG = 15.0
SHARP_TURN_THRESHOLD_DEG = 45.0
TURN_REFERENCE_ANGLE_DEG = 120.0
TURN_SLOWDOWN_MAX_FACTOR = 0.55
TURN_MIN_SPEED_M_S = 2.5
TURN_REFERENCE_LENGTH_M = 25.0
TURN_REGEN_RECOVERY = 0.35


def compute_speed(distance_m: float, time_s: float) -> float:
    if time_s <= 0:
        raise ValueError("Le temps doit etre > 0.")
    return distance_m / time_s


def compute_slope_angle(
    altitude_start_m: float,
    altitude_end_m: float,
    distance_m: float,
) -> float:
    if distance_m <= 0:
        raise ValueError("La distance doit etre > 0.")

    ratio = (altitude_end_m - altitude_start_m) / distance_m
    ratio = max(-1.0, min(1.0, ratio))
    return asin(ratio)


def compute_acceleration(
    current_speed_m_s: float,
    next_speed_m_s: float,
    time_s: float,
) -> float:
    if time_s <= 0:
        raise ValueError("Le temps doit etre > 0.")
    return (next_speed_m_s - current_speed_m_s) / time_s


def haversine_distance_m(
    lat1_deg: float,
    lon1_deg: float,
    lat2_deg: float,
    lon2_deg: float,
) -> float:
    earth_radius_m = 6_371_000.0
    lat1 = radians(lat1_deg)
    lon1 = radians(lon1_deg)
    lat2 = radians(lat2_deg)
    lon2 = radians(lon2_deg)

    d_lat = lat2 - lat1
    d_lon = lon2 - lon1

    value = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    c = 2 * asin(min(1.0, sqrt(value)))
    return earth_radius_m * c


def compute_heading_deg(
    lat1_deg: float,
    lon1_deg: float,
    lat2_deg: float,
    lon2_deg: float,
) -> float:
    mid_lat_rad = radians((lat1_deg + lat2_deg) / 2.0)
    delta_lon = radians(lon2_deg - lon1_deg) * cos(mid_lat_rad)
    delta_lat = radians(lat2_deg - lat1_deg)
    angle_deg = degrees(atan2(delta_lon, delta_lat))
    return (angle_deg + 360.0) % 360.0


def compute_turn_angle_deg(
    prev_point: GeoPoint,
    current_point: GeoPoint,
    next_point: GeoPoint,
) -> float:
    incoming_heading = compute_heading_deg(
        prev_point.lat,
        prev_point.lon,
        current_point.lat,
        current_point.lon,
    )
    outgoing_heading = compute_heading_deg(
        current_point.lat,
        current_point.lon,
        next_point.lat,
        next_point.lon,
    )
    delta = (outgoing_heading - incoming_heading + 180.0) % 360.0 - 180.0
    return abs(delta)


def interpolate_time_at_distance(
    target_distance_m: float,
    cumulative_distances_m: List[float],
    points: List[GeoPoint],
    fallback_time_s: float,
) -> float:
    known_points = [
        (cumulative_distances_m[idx], point.time_s)
        for idx, point in enumerate(points)
        if point.time_s is not None
    ]

    if len(known_points) >= 2:
        for idx in range(len(known_points) - 1):
            start_dist, start_time = known_points[idx]
            end_dist, end_time = known_points[idx + 1]
            if not (start_dist <= target_distance_m <= end_dist):
                continue

            if end_dist == start_dist:
                return float(start_time)

            ratio = (target_distance_m - start_dist) / (end_dist - start_dist)
            return float(start_time + ratio * (end_time - start_time))

    total_distance_m = cumulative_distances_m[-1] if cumulative_distances_m else 0.0
    if total_distance_m <= 0 or fallback_time_s <= 0:
        return 0.0

    return (target_distance_m / total_distance_m) * fallback_time_s


def normalize_geo_points(raw_points: List[Dict[str, float]]) -> List[GeoPoint]:
    points: List[GeoPoint] = []

    for point in raw_points:
        missing_keys = [key for key in ("lat", "lon", "altitude_m") if key not in point]
        if missing_keys:
            raise ValueError(
                f"Point geographique incomplet. Champs manquants : {', '.join(missing_keys)}"
            )

        points.append(
            GeoPoint(
                lat=point["lat"],
                lon=point["lon"],
                altitude_m=point["altitude_m"],
                time_s=point.get("time_s"),
                speed_m_s=point.get("speed_m_s"),
            )
        )

    if len(points) < 2:
        raise ValueError("Au moins 2 points geographiques sont requis.")

    return points


def compute_profile_metrics_from_geo_points(
    raw_points: List[Dict[str, float]],
    fallback_time_s: float,
    fallback_distance_m: Optional[float] = None,
) -> Dict[str, Any]:
    points = normalize_geo_points(raw_points)

    distances_m: List[float] = []
    cumulative_distances_m: List[float] = [0.0]
    slope_angles_rad: List[float] = []
    speeds_m_s: List[float] = []
    speed_samples: List[Dict[str, float]] = []
    observed_speed_sample_count = 0
    accelerations_m_s2: List[float] = []
    turn_samples: List[Dict[str, float]] = []

    for idx in range(len(points) - 1):
        start = points[idx]
        end = points[idx + 1]
        distance_m = haversine_distance_m(start.lat, start.lon, end.lat, end.lon)

        if distance_m <= 0:
            cumulative_distances_m.append(cumulative_distances_m[-1])
            continue

        distances_m.append(distance_m)
        cumulative_distances_m.append(cumulative_distances_m[-1] + distance_m)
        slope_angles_rad.append(
            compute_slope_angle(start.altitude_m, end.altitude_m, distance_m)
        )

        if start.speed_m_s is not None:
            speeds_m_s.append(start.speed_m_s)
            if start.time_s is not None:
                speed_samples.append({"time_s": start.time_s, "speed_m_s": start.speed_m_s})
                observed_speed_sample_count += 1

        if start.time_s is not None and end.time_s is not None:
            delta_t = end.time_s - start.time_s
            if delta_t > 0:
                interval_speed = distance_m / delta_t
                speeds_m_s.append(interval_speed)
                speed_samples.append(
                    {
                        "time_s": start.time_s + (delta_t / 2.0),
                        "speed_m_s": interval_speed,
                    }
                )
                observed_speed_sample_count += 1

    if points[-1].speed_m_s is not None:
        speeds_m_s.append(points[-1].speed_m_s)
        if points[-1].time_s is not None:
            speed_samples.append(
                {"time_s": points[-1].time_s, "speed_m_s": points[-1].speed_m_s}
            )
            observed_speed_sample_count += 1

    distance_from_geo_m = sum(distances_m)
    distance_m = (
        distance_from_geo_m
        if distance_from_geo_m > 0
        else (fallback_distance_m if fallback_distance_m is not None else 0.0)
    )

    base_speed_m_s = compute_speed(distance_m, fallback_time_s) if fallback_time_s > 0 else 0.0

    weighted_turn_sum = 0.0
    turn_weight_sum = 0.0
    max_turn_angle_deg = 0.0
    sharp_turn_count = 0
    turn_points_count = 0
    turn_specific_energy_j_kg = 0.0

    for idx in range(1, len(points) - 1):
        previous_distance_m = distances_m[idx - 1] if idx - 1 < len(distances_m) else 0.0
        next_distance_m = distances_m[idx] if idx < len(distances_m) else 0.0
        local_length_m = min(previous_distance_m, next_distance_m)
        if local_length_m <= 0:
            continue

        turn_angle_deg = compute_turn_angle_deg(points[idx - 1], points[idx], points[idx + 1])
        if turn_angle_deg < TURN_ANGLE_THRESHOLD_DEG:
            continue

        turn_points_count += 1
        weight_factor = min(local_length_m / TURN_REFERENCE_LENGTH_M, 1.0)
        weighted_turn_sum += turn_angle_deg * local_length_m
        turn_weight_sum += local_length_m
        max_turn_angle_deg = max(max_turn_angle_deg, turn_angle_deg)

        if turn_angle_deg >= SHARP_TURN_THRESHOLD_DEG and weight_factor >= 0.5:
            sharp_turn_count += 1

        if base_speed_m_s <= 0:
            continue

        severity = min(turn_angle_deg, TURN_REFERENCE_ANGLE_DEG) / TURN_REFERENCE_ANGLE_DEG
        speed_factor = max(1.0 - TURN_SLOWDOWN_MAX_FACTOR, 1.0 - TURN_SLOWDOWN_MAX_FACTOR * severity)
        turn_speed_m_s = min(base_speed_m_s, max(TURN_MIN_SPEED_M_S, base_speed_m_s * speed_factor))
        turn_samples.append(
            {
                "time_s": interpolate_time_at_distance(
                    cumulative_distances_m[idx],
                    cumulative_distances_m,
                    points,
                    fallback_time_s,
                ),
                "speed_m_s": turn_speed_m_s,
            }
        )
        speeds_m_s.append(turn_speed_m_s)

        kinetic_gap_j_kg = max(0.0, 0.5 * ((base_speed_m_s ** 2) - (turn_speed_m_s ** 2)))
        turn_specific_energy_j_kg += kinetic_gap_j_kg * (1.0 - TURN_REGEN_RECOVERY) * weight_factor

    speed_samples.extend(turn_samples)
    speed_m_s = mean(speeds_m_s) if speeds_m_s else base_speed_m_s

    slope_rad = (
        sum(angle * dist for angle, dist in zip(slope_angles_rad, distances_m)) / distance_from_geo_m
        if distance_from_geo_m > 0
        else 0.0
    )

    abs_slope_rad = (
        sum(abs(angle) * dist for angle, dist in zip(slope_angles_rad, distances_m))
        / distance_from_geo_m
        if distance_from_geo_m > 0
        else 0.0
    )

    speed_samples.sort(key=lambda sample: sample["time_s"])
    if observed_speed_sample_count >= 2 and len(speed_samples) >= 2:
        for idx in range(len(speed_samples) - 1):
            delta_t = speed_samples[idx + 1]["time_s"] - speed_samples[idx]["time_s"]
            if delta_t > 0:
                accelerations_m_s2.append(
                    compute_acceleration(
                        speed_samples[idx]["speed_m_s"],
                        speed_samples[idx + 1]["speed_m_s"],
                        delta_t,
                    )
                )
    acceleration_m_s2 = mean(accelerations_m_s2) if accelerations_m_s2 else None

    return {
        "distance_m": distance_m,
        "speed_m_s": speed_m_s,
        "slope_rad": slope_rad,
        "abs_slope_rad": abs_slope_rad,
        "acceleration_m_s2": acceleration_m_s2,
        "gps_points_count": len(points),
        "distance_from_geo_m": distance_from_geo_m,
        "turn_points_count": turn_points_count,
        "sharp_turn_count": sharp_turn_count,
        "weighted_turn_angle_deg": (
            weighted_turn_sum / turn_weight_sum if turn_weight_sum > 0 else 0.0
        ),
        "max_turn_angle_deg": max_turn_angle_deg,
        "turn_specific_energy_j_kg": turn_specific_energy_j_kg,
    }


def compute_motion_power_w(
    speed_m_s: float,
    slope_rad: float,
    acceleration_m_s2: float,
    bus: BusParameters,
) -> float:
    gravity_force = bus.mass_kg * bus.g * sin(slope_rad)
    rolling_force = bus.mass_kg * bus.g * bus.rolling_coeff * cos(slope_rad)
    aerodynamic_force = 0.5 * bus.air_density * (speed_m_s ** 2) * bus.frontal_area_m2 * bus.drag_coeff
    inertial_force = bus.mass_kg * acceleration_m_s2
    return speed_m_s * (gravity_force + rolling_force + aerodynamic_force + inertial_force)


def compute_total_power_w(
    speed_m_s: float,
    slope_rad: float,
    acceleration_m_s2: float,
    bus: BusParameters,
    turn_penalty_w: float = 0.0,
) -> float:
    return (
        compute_motion_power_w(speed_m_s, slope_rad, acceleration_m_s2, bus)
        + bus.aux_power_kw * 1000.0
        + turn_penalty_w
    )


def compute_segment_energy_kwh(total_power_w: float, time_s: float) -> float:
    return (total_power_w * time_s) / 3_600_000.0


def prepare_segments(raw_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []

    for seg in raw_segments:
        time_s = seg["time_s"]

        if "geo_points" in seg:
            profile = compute_profile_metrics_from_geo_points(
                raw_points=seg["geo_points"],
                fallback_time_s=time_s,
                fallback_distance_m=seg.get("distance_m"),
            )
            prepared.append(
                {
                    **seg,
                    "distance_m": profile["distance_m"],
                    "speed_m_s": profile["speed_m_s"],
                    "slope_rad": profile["slope_rad"],
                    "abs_slope_rad": profile["abs_slope_rad"],
                    "acceleration_m_s2": profile["acceleration_m_s2"],
                    "gps_points_count": profile["gps_points_count"],
                    "distance_from_geo_m": profile["distance_from_geo_m"],
                    "turn_points_count": profile["turn_points_count"],
                    "sharp_turn_count": profile["sharp_turn_count"],
                    "weighted_turn_angle_deg": profile["weighted_turn_angle_deg"],
                    "max_turn_angle_deg": profile["max_turn_angle_deg"],
                    "turn_specific_energy_j_kg": profile["turn_specific_energy_j_kg"],
                    "acceleration_source": "geo_profile",
                    "slope_source": "geo_profile",
                }
            )
            continue

        speed = compute_speed(seg["distance_m"], time_s)
        slope = compute_slope_angle(
            seg["altitude_start_m"],
            seg["altitude_end_m"],
            seg["distance_m"],
        )

        prepared.append(
            {
                **seg,
                "speed_m_s": speed,
                "slope_rad": slope,
                "abs_slope_rad": abs(slope),
                "acceleration_m_s2": None,
                "gps_points_count": 0,
                "distance_from_geo_m": None,
                "turn_points_count": 0,
                "sharp_turn_count": 0,
                "weighted_turn_angle_deg": 0.0,
                "max_turn_angle_deg": 0.0,
                "turn_specific_energy_j_kg": 0.0,
                "acceleration_source": "inter_segment",
                "slope_source": "segment_endpoints",
            }
        )

    for idx in range(len(prepared)):
        if prepared[idx]["acceleration_m_s2"] is not None:
            continue

        current_speed = prepared[idx]["speed_m_s"]
        current_time = prepared[idx]["time_s"]

        if idx < len(prepared) - 1:
            next_speed = prepared[idx + 1]["speed_m_s"]
            acceleration = compute_acceleration(current_speed, next_speed, current_time)
        else:
            acceleration = 0.0

        prepared[idx]["acceleration_m_s2"] = acceleration
        prepared[idx]["acceleration_source"] = "inter_segment"

    return prepared


def compute_trip_energy(
    raw_segments: List[Dict[str, Any]],
    bus: BusParameters,
    include_turn_penalty: bool = True,
) -> Dict[str, Any]:
    segments = prepare_segments(raw_segments)

    total_energy_kwh = 0.0
    total_distance_m = 0.0
    total_turn_energy_kwh = 0.0
    total_turn_points = 0
    total_sharp_turns = 0
    max_turn_angle_deg = 0.0
    detailed_results = []

    for seg in segments:
        turn_penalty_w = 0.0
        if include_turn_penalty and seg["time_s"] > 0:
            turn_penalty_w = bus.mass_kg * seg["turn_specific_energy_j_kg"] / seg["time_s"]

        total_power_w = compute_total_power_w(
            speed_m_s=seg["speed_m_s"],
            slope_rad=seg["slope_rad"],
            acceleration_m_s2=seg["acceleration_m_s2"],
            bus=bus,
            turn_penalty_w=turn_penalty_w,
        )
        energy_kwh = compute_segment_energy_kwh(total_power_w, seg["time_s"])
        turn_energy_kwh = compute_segment_energy_kwh(turn_penalty_w, seg["time_s"])

        total_energy_kwh += energy_kwh
        total_distance_m += seg["distance_m"]
        total_turn_energy_kwh += turn_energy_kwh
        total_turn_points += seg["turn_points_count"]
        total_sharp_turns += seg["sharp_turn_count"]
        max_turn_angle_deg = max(max_turn_angle_deg, seg["max_turn_angle_deg"])
        detailed_results.append(
            {
                "name": seg["name"],
                "distance_m": seg["distance_m"],
                "time_s": seg["time_s"],
                "speed_m_s": seg["speed_m_s"],
                "speed_km_h": seg["speed_m_s"] * 3.6,
                "slope_rad": seg["slope_rad"],
                "abs_slope_rad": seg["abs_slope_rad"],
                "acceleration_m_s2": seg["acceleration_m_s2"],
                "total_power_kw": total_power_w / 1000.0,
                "energy_kwh": energy_kwh,
                "turn_penalty_kw": turn_penalty_w / 1000.0,
                "turn_energy_kwh": turn_energy_kwh,
                "slope_source": seg["slope_source"],
                "acceleration_source": seg["acceleration_source"],
                "gps_points_count": seg["gps_points_count"],
                "distance_from_geo_m": seg["distance_from_geo_m"],
                "turn_points_count": seg["turn_points_count"],
                "sharp_turn_count": seg["sharp_turn_count"],
                "weighted_turn_angle_deg": seg["weighted_turn_angle_deg"],
                "max_turn_angle_deg": seg["max_turn_angle_deg"],
            }
        )

    total_distance_km = total_distance_m / 1000.0
    specific_consumption_kwh_km = (
        total_energy_kwh / total_distance_km if total_distance_km > 0 else 0.0
    )

    return {
        "segments": detailed_results,
        "total_energy_kwh": total_energy_kwh,
        "total_distance_km": total_distance_km,
        "specific_consumption_kwh_km": specific_consumption_kwh_km,
        "total_turn_energy_kwh": total_turn_energy_kwh,
        "total_turn_points": total_turn_points,
        "total_sharp_turns": total_sharp_turns,
        "max_turn_angle_deg": max_turn_angle_deg,
    }


def clone_segments_without_relief(raw_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cloned_segments: List[Dict[str, Any]] = []

    for seg in raw_segments:
        cloned_segment = {**seg}
        reference_altitude = seg.get("altitude_start_m", 0.0)

        if seg.get("geo_points"):
            cloned_geo_points = []
            reference_altitude = seg["geo_points"][0].get("altitude_m", reference_altitude)
            for point in seg["geo_points"]:
                cloned_geo_points.append(
                    {
                        **point,
                        "altitude_m": reference_altitude,
                    }
                )
            cloned_segment["geo_points"] = cloned_geo_points

        cloned_segment["altitude_start_m"] = reference_altitude
        cloned_segment["altitude_end_m"] = reference_altitude
        cloned_segments.append(cloned_segment)

    return cloned_segments


def build_scenario_comparisons(
    raw_segments: List[Dict[str, Any]],
    bus: BusParameters,
) -> List[Dict[str, Any]]:
    scenario_definitions = [
        {
            "name": "Complet",
            "description": "Relief IGN et penalites de virages actives.",
            "raw_segments": raw_segments,
            "include_turn_penalty": True,
        },
        {
            "name": "Sans relief",
            "description": "Altitudes neutralisees pour mesurer l'effet du relief.",
            "raw_segments": clone_segments_without_relief(raw_segments),
            "include_turn_penalty": True,
        },
        {
            "name": "Sans virages",
            "description": "Penalites energetiques de virages desactivees.",
            "raw_segments": raw_segments,
            "include_turn_penalty": False,
        },
    ]

    comparisons: List[Dict[str, Any]] = []
    reference_energy_kwh: Optional[float] = None

    for scenario in scenario_definitions:
        scenario_results = compute_trip_energy(
            scenario["raw_segments"],
            bus,
            include_turn_penalty=scenario["include_turn_penalty"],
        )
        if reference_energy_kwh is None:
            reference_energy_kwh = scenario_results["total_energy_kwh"]

        delta_kwh = scenario_results["total_energy_kwh"] - reference_energy_kwh
        delta_pct = (
            (delta_kwh / reference_energy_kwh) * 100.0
            if reference_energy_kwh not in (None, 0.0)
            else 0.0
        )
        comparisons.append(
            {
                "name": scenario["name"],
                "description": scenario["description"],
                "total_energy_kwh": scenario_results["total_energy_kwh"],
                "specific_consumption_kwh_km": scenario_results["specific_consumption_kwh_km"],
                "delta_energy_kwh": delta_kwh,
                "delta_energy_pct": delta_pct,
                "is_reference": reference_energy_kwh == scenario_results["total_energy_kwh"],
            }
        )

    return comparisons
