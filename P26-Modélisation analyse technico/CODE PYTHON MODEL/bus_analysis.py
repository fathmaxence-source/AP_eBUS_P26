from __future__ import annotations
 
from pathlib import Path
 
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
 
from p_charge import p_charge
 
 
def _is_depot_trip_id(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.startswith("DEPOT_")
 
 
def _highlight_time_windows(
    ax: plt.Axes,
    rows: pd.DataFrame,
    start_col: str,
    end_col: str,
    color: tuple[float, float, float],
    alpha: float,
    label: str | None = None,
) -> None:
    first = True
    for _, row in rows.iterrows():
        ax.axvspan(
            pd.Timestamp(row[start_col]),
            pd.Timestamp(row[end_col]),
            color=color,
            alpha=alpha,
            label=label if first else None,
        )
        first = False
 
 
def build_realtime_profile(tabl: pd.DataFrame) -> pd.DataFrame:
    profile = tabl.copy()
    profile["StartTimeHour"] = profile["TimeHour"] - pd.to_timedelta(profile["deltaT"], unit="s")
    profile["Distance_km"] = profile["Distance"] / 1000.0
    profile["CumulativeDistance_km"] = profile["Total_Distance"] / 1000.0
    profile["Speed_km_h"] = profile["Velocity"] * 3.6
    profile["Power_kW"] = profile["Power"] / 1000.0
    profile["ChargePower_kW"] = profile["PowerC"] / 1000.0
    profile["NetPower_kW"] = (profile["Power"] - profile["PowerC"]) / 1000.0
    profile["EnergyUsed_kWh"] = (profile["Power"] * profile["deltaT"]) / 3.6e6
    profile["EnergyCharged_kWh"] = (profile["PowerC"] * profile["deltaT"]) / 3.6e6
    profile["CumulativeEnergyUsed_kWh"] = profile["EnergyUsed_kWh"].cumsum()
    profile["CumulativeEnergyCharged_kWh"] = profile["EnergyCharged_kWh"].cumsum()
    profile["NetBatteryEnergy_kWh"] = (
        profile["CumulativeEnergyUsed_kWh"] - profile["CumulativeEnergyCharged_kWh"]
    )
    if "TripID" in profile.columns:
        profile["IsDepotSegment"] = _is_depot_trip_id(profile["TripID"])
    else:
        profile["IsDepotSegment"] = False
    return profile
 
 
def compute_charge_window_hours(start_time: pd.Timestamp, end_time: pd.Timestamp) -> tuple[float, pd.Timestamp]:
    next_start_time = start_time + pd.Timedelta(days=1)
    while next_start_time <= end_time:
        next_start_time += pd.Timedelta(days=1)
    return (next_start_time - end_time).total_seconds() / 3600.0, next_start_time
 
 
def build_full_day_profile(
    realtime_profile: pd.DataFrame,
    battery_capacity_kwh: float,
    service_start_time: pd.Timestamp,
    terminal_power_kw: float,
) -> tuple[pd.DataFrame, dict[str, float | pd.Timestamp]]:
    service_profile = realtime_profile.copy()
    service_profile["Phase"] = "service"
 
    service_end_time = service_profile["TimeHour"].iloc[-1]
    soc_end_pct = float(service_profile["SoC"].iloc[-1])
    soc_end_fraction = soc_end_pct / 100.0
    charge_window_h, next_start_time = compute_charge_window_hours(service_start_time, service_end_time)
 
    # On charge a pleine puissance terminale
    pcharge_kw = terminal_power_kw
    time_to_full_h = (1 - soc_end_fraction) * battery_capacity_kwh / pcharge_kw
    actual_charge_end_time = service_end_time + pd.Timedelta(hours=time_to_full_h)
 
    charge_times = pd.date_range(start=service_end_time, end=actual_charge_end_time, freq="min")
    
    if len(charge_times) <= 1:
        metadata = {
            "charge_power_kw": pcharge_kw,
            "charge_window_h": charge_window_h,
            "service_end_time": service_end_time,
            "next_start_time": actual_charge_end_time,
        }
        return service_profile, metadata
 
    charged_energy_kwh = np.zeros(len(charge_times))
    soc_values = np.zeros(len(charge_times))
    soc_values[0] = soc_end_pct
 
    energy_per_minute_kwh = pcharge_kw / 60.0
    for index in range(1, len(charge_times)):
        remaining_kwh = max(0.0, (100.0 - soc_values[index - 1]) / 100.0 * battery_capacity_kwh)
        charged_energy_kwh[index] = min(energy_per_minute_kwh, remaining_kwh)
        soc_values[index] = soc_values[index - 1] + (charged_energy_kwh[index] / battery_capacity_kwh) * 100.0
    
    # Tronquer au moment où SoC atteint 100 %
    fully_charged_indices = np.where(soc_values >= 100.0)[0]
    soc_values[-1] = 100.0
    actual_charge_end_time = charge_times[-1]
 
    charge_profile = pd.DataFrame(
        {
            "TimeHour": charge_times,
            "StartTimeHour": charge_times - pd.to_timedelta(1, unit="min"),
            "Distance_km": 0.0,
            "CumulativeDistance_km": float(service_profile["CumulativeDistance_km"].iloc[-1]),
            "Speed_km_h": 0.0,
            "Power_kW": 0.0,
            "ChargePower_kW": charged_energy_kwh * 60.0,
            "NetPower_kW": -(charged_energy_kwh * 60.0),
            "EnergyUsed_kWh": 0.0,
            "EnergyCharged_kWh": charged_energy_kwh,
            "CumulativeEnergyUsed_kWh": float(service_profile["CumulativeEnergyUsed_kWh"].iloc[-1]),
            "CumulativeEnergyCharged_kWh": (
                float(service_profile["CumulativeEnergyCharged_kWh"].iloc[-1]) + np.cumsum(charged_energy_kwh)
            ),
            "SoC": soc_values,
            "Phase": "depot_charge",
            "IsDepotSegment": False,
        }
    )
    charge_profile["NetBatteryEnergy_kWh"] = (
        charge_profile["CumulativeEnergyUsed_kWh"] - charge_profile["CumulativeEnergyCharged_kWh"]
    )
 
    # Ajout d'un point à 0 kW après la fin de charge
    last_row = charge_profile.iloc[[-1]].copy()
    last_row["TimeHour"] = actual_charge_end_time + pd.Timedelta(minutes=1)
    last_row["ChargePower_kW"] = 0.0
    last_row["NetPower_kW"] = 0.0
    last_row["EnergyCharged_kWh"] = 0.0

    full_day_profile = pd.concat([service_profile, charge_profile.iloc[1:], last_row], ignore_index=True)
    metadata = {
        "charge_power_kw": pcharge_kw,
        "charge_window_h": charge_window_h,
        "service_end_time": service_end_time,
        "next_start_time": actual_charge_end_time,
    }
    return full_day_profile, metadata
 
 
def build_segment_summary(tabl: pd.DataFrame) -> pd.DataFrame:
    profile = build_realtime_profile(tabl)
    travel_rows = profile[profile["Distance"] > 0].copy()
    travel_rows["SegmentIndex"] = np.arange(1, len(travel_rows) + 1)
    travel_rows["TravelTime_min"] = travel_rows["deltaT"] / 60.0
    travel_rows["SoC_Start_pct"] = profile["SoC"].shift(fill_value=profile["SoC"].iloc[0]).loc[
        travel_rows.index
    ].values
    travel_rows["SoC_End_pct"] = travel_rows["SoC"].values
    travel_rows["SegmentType"] = np.where(
        travel_rows["IsDepotSegment"],
        "depot_deadhead",
        "line_service",
    )
 
    columns = [
        "SegmentIndex",
        "Cycle",
        "TripID",
        "SegmentType",
        "StartStopName",
        "EndStopName",
        "StartTimeHour",
        "TimeHour",
        "TravelTime_min",
        "Distance_km",
        "Speed_km_h",
        "Power_kW",
        "EnergyUsed_kWh",
        "SoC_Start_pct",
        "SoC_End_pct",
        "CumulativeDistance_km",
        "IsDepotSegment",
    ]
    optional_columns = [
        column_name
        for column_name in ("BusModelId", "BusModelName")
        if column_name in travel_rows.columns
    ]
    columns = optional_columns + columns
    summary = travel_rows[columns].reset_index(drop=True)
    return summary.rename(
        columns={
            "StartStopName": "StartStop",
            "EndStopName": "EndStop",
            "StartTimeHour": "StartTime",
            "TimeHour": "EndTime",
            "Power_kW": "AveragePower_kW",
        }
    )
 
 
def export_analysis_tables(
    realtime_profile: pd.DataFrame,
    segment_summary: pd.DataFrame,
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    realtime_path = output_dir / "bus_realtime_profile.csv"
    segments_path = output_dir / "bus_segment_summary.csv"
    realtime_profile.to_csv(realtime_path, index=False)
    segment_summary.to_csv(segments_path, index=False)
    return realtime_path, segments_path
 
 
def _style_time_axis(ax: plt.Axes) -> None:
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True, alpha=0.3)
 
 
def plot_power_over_time(
    full_day_profile: pd.DataFrame,
    route_name: str,
    output_path: Path | None = None,
) -> None:
    travel_rows = full_day_profile[full_day_profile["Distance"] > 0].copy()
    depot_rows = travel_rows[travel_rows["IsDepotSegment"]]
    depot_color = (0.95, 0.55, 0.1)
    depot_span_color = (1.0, 0.85, 0.45)
    charge_color = (0.92, 0.92, 0.92)
 
    plt.close("bus_power_over_time")
    fig, ax = plt.subplots(figsize=(15, 6), num="bus_power_over_time")
 
    _highlight_time_windows(
        ax,
        depot_rows,
        "StartTimeHour",
        "TimeHour",
        color=depot_span_color,
        alpha=0.25,
        label="Trajet depot",
    )
 
    charge_rows = full_day_profile[full_day_profile["Phase"] == "depot_charge"]
    if not charge_rows.empty:
        ax.axvspan(
            charge_rows["TimeHour"].iloc[0],
            charge_rows["TimeHour"].iloc[-1],
            color=charge_color,
            alpha=0.6,
            label="Recharge depot",
        )
 
    ax.plot(
        full_day_profile["TimeHour"],
        full_day_profile["NetPower_kW"],
        color=(0.8, 0.2, 0.1),
        linewidth=1.8,
        label="Puissance nette",
    )
    ax.scatter(
        depot_rows["TimeHour"],
        depot_rows["NetPower_kW"],
        s=46,
        color=depot_color,
        edgecolors=(0.25, 0.15, 0.0),
        linewidths=0.8,
        label="Fin de segment depot",
    )
    ax.set_xlabel("Heure")
    ax.set_ylabel("Puissance nette (kW)")
    ax.set_title(f"Puissance en fonction du temps - {route_name}")
    ax.legend(loc="best")
    _style_time_axis(ax)
 
    fig.tight_layout()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=160, bbox_inches="tight")
 
 
def plot_soc_over_time(
    full_day_profile: pd.DataFrame,
    route_name: str,
    output_path: Path | None = None,
) -> None:
    plt.close("bus_soc_over_time")
    fig, ax = plt.subplots(figsize=(15, 6), num="bus_soc_over_time")
 
    soc_color = (0.15, 0.6, 0.25)
    depot_color = (0.95, 0.55, 0.1)
    depot_span_color = (1.0, 0.85, 0.45)
    charge_color = (0.92, 0.92, 0.92)
 
    depot_rows = full_day_profile[full_day_profile["IsDepotSegment"].fillna(False)]
    _highlight_time_windows(
        ax,
        depot_rows,
        "StartTimeHour",
        "TimeHour",
        color=depot_span_color,
        alpha=0.25,
        label="Trajet depot",
    )
 
    charge_rows = full_day_profile[full_day_profile["Phase"] == "depot_charge"]
    if not charge_rows.empty:
        ax.axvspan(
            charge_rows["TimeHour"].iloc[0],
            charge_rows["TimeHour"].iloc[-1],
            color=charge_color,
            alpha=0.6,
            label="Recharge depot",
        )
 
    ax.plot(
        full_day_profile["TimeHour"],
        full_day_profile["SoC"],
        color=soc_color,
        linewidth=1.8,
        label="SoC",
    )
    ax.scatter(
        depot_rows["TimeHour"],
        depot_rows["SoC"],
        s=44,
        color=depot_color,
        edgecolors=(0.25, 0.15, 0.0),
        linewidths=0.8,
    )
    ax.set_xlabel("Heure")
    ax.set_ylabel("SoC (%)", color=soc_color)
    ax.tick_params(axis="y", labelcolor=soc_color)
    ax.set_ylim(0, 105)
    ax.legend(loc="best")
    ax.set_title(f"Etat de charge en fonction du temps - {route_name}")
    _style_time_axis(ax)
 
    fig.tight_layout()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=160, bbox_inches="tight")
 
 
def plot_energy_consumption_over_time(
    full_day_profile: pd.DataFrame,
    route_name: str,
    output_path: Path | None = None,
) -> None:
    plt.close("bus_energy_consumption")
    fig, ax = plt.subplots(figsize=(15, 6), num="bus_energy_consumption")
 
    depot_rows = full_day_profile[full_day_profile["IsDepotSegment"].fillna(False)]
    _highlight_time_windows(
        ax,
        depot_rows,
        "StartTimeHour",
        "TimeHour",
        color=(1.0, 0.85, 0.45),
        alpha=0.25,
        label="Trajet depot",
    )
 
    charge_rows = full_day_profile[full_day_profile["Phase"] == "depot_charge"]
    if not charge_rows.empty:
        ax.axvspan(
            charge_rows["TimeHour"].iloc[0],
            charge_rows["TimeHour"].iloc[-1],
            color=(0.92, 0.92, 0.92),
            alpha=0.6,
            label="Recharge depot",
        )
 
    ax.plot(
        full_day_profile["TimeHour"],
        full_day_profile["CumulativeEnergyUsed_kWh"],
        color=(0.8, 0.2, 0.1),
        linewidth=1.8,
        label="Energie consommee cumulee",
    )
 
    ax.set_xlabel("Heure")
    ax.set_ylabel("Energie (kWh)")
    ax.set_title(f"Consommation energetique en fonction du temps - {route_name}")
    _style_time_axis(ax)
    ax.legend(loc="best")
 
    fig.tight_layout()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=160, bbox_inches="tight")
 
 
def plot_segment_dashboard(
    segment_summary: pd.DataFrame,
    route_name: str,
    output_path: Path | None = None,
) -> None:
    x_values = pd.to_datetime(segment_summary["EndTime"])
    depot_mask = segment_summary["IsDepotSegment"].astype(bool)
    depot_rows = segment_summary[depot_mask]
    depot_color = (0.95, 0.55, 0.1)
    depot_span_color = (1.0, 0.85, 0.45)
 
    fig, axes = plt.subplots(3, 1, figsize=(15, 11), sharex=True, num="bus_segment_dashboard")
 
    for axis in axes:
        _highlight_time_windows(
            axis,
            depot_rows,
            "StartTime",
            "EndTime",
            color=depot_span_color,
            alpha=0.25,
            label="Trajet depot" if axis is axes[0] else None,
        )
 
    axes[0].plot(
        x_values,
        segment_summary["AveragePower_kW"],
        color=(0.85, 0.33, 0.1),
        linewidth=1.5,
        marker="o",
        markersize=3,
        label="Segments",
    )
    axes[0].scatter(
        pd.to_datetime(depot_rows["EndTime"]),
        depot_rows["AveragePower_kW"],
        s=46,
        color=depot_color,
        edgecolors=(0.25, 0.15, 0.0),
        linewidths=0.8,
        label="Segments depot",
    )
    axes[0].set_ylabel("Puissance (kW)")
    axes[0].set_title(f"Puissance moyenne par segment en temps reel - {route_name}")
    axes[0].legend(loc="best")
    _style_time_axis(axes[0])
 
    axes[1].plot(
        x_values,
        segment_summary["Distance_km"],
        color=(0.0, 0.45, 0.74),
        linewidth=1.5,
        marker="o",
        markersize=3,
    )
    axes[1].scatter(
        pd.to_datetime(depot_rows["EndTime"]),
        depot_rows["Distance_km"],
        s=46,
        color=depot_color,
        edgecolors=(0.25, 0.15, 0.0),
        linewidths=0.8,
    )
    axes[1].set_ylabel("Distance (km)")
    axes[1].set_title("Distance entre deux arrets en temps reel")
    _style_time_axis(axes[1])
 
    axes[2].plot(
        x_values,
        segment_summary["SoC_End_pct"],
        color=(0.15, 0.6, 0.25),
        linewidth=1.6,
        marker="o",
        markersize=3,
    )
    axes[2].scatter(
        pd.to_datetime(depot_rows["EndTime"]),
        depot_rows["SoC_End_pct"],
        s=46,
        color=depot_color,
        edgecolors=(0.25, 0.15, 0.0),
        linewidths=0.8,
    )
    axes[2].set_ylabel("SoC arrivee (%)")
    axes[2].set_xlabel("Heure")
    axes[2].set_title("Evolution du SoC a chaque arrivee d'arret")
    axes[2].set_ylim(0, 105)
    _style_time_axis(axes[2])
 
    fig.tight_layout()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=160, bbox_inches="tight")
 
 
def plot_realtime_dashboard(
    realtime_profile: pd.DataFrame,
    route_name: str,
    output_path: Path | None = None,
) -> None:
    """
    Wrapper de compatibilite avec l'ancienne architecture.
 
    L'ancienne version du main importait `plot_realtime_dashboard`.
    On redirige maintenant cet appel vers le graphe puissance/temps
    pour eviter tout ImportError si un ancien script est encore lance.
    """
 
    plot_power_over_time(
        full_day_profile=realtime_profile,
        route_name=route_name,
        output_path=output_path,
    )
 
 
def plot_distance_soc_over_time(
    full_day_profile: pd.DataFrame,
    route_name: str,
    output_path: Path | None = None,
) -> None:
    """
    Wrapper de compatibilite avec l'ancienne architecture.
 
    L'ancien nom `plot_distance_soc_over_time` est conserve pour permettre
    le lancement d'un ancien `main_code.py` sans modifier manuellement
    toutes les instructions d'import.
    """
 
    plot_soc_over_time(
        full_day_profile=full_day_profile,
        route_name=route_name,
        output_path=output_path,
    )
 
 
def print_segment_preview(segment_summary: pd.DataFrame, max_rows: int = 20) -> None:
    preview = segment_summary.head(max_rows).copy()
    with pd.option_context(
        "display.max_columns",
        None,
        "display.width",
        220,
        "display.max_colwidth",
        30,
    ):
        print()
        print(f"Resume segment par segment (premieres {min(len(preview), max_rows)} lignes) :")
        print(preview.to_string(index=False))
