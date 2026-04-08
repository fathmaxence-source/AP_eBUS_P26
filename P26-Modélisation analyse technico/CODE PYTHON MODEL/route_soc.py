from __future__ import annotations

import numpy as np
import pandas as pd

from bus_models import BusModel, LEGACY_BUS_MODEL


def route_soc(
    tabl: pd.DataFrame,
    bus_model: BusModel | None = None,
) -> tuple[pd.DataFrame, float]:
    """
    Calcule l'evolution du SoC a partir du profil de puissance.
    """

    model = bus_model or LEGACY_BUS_MODEL
    initial_soc_pct = 100.0

    discharge_energy_kwh = (tabl["Power"] * tabl["deltaT"]) / 3.6e6
    charge_energy_kwh = (tabl["PowerC"] * tabl["deltaT"]) / 3.6e6

    battery_capacity_kwh = model.battery_capacity_kwh
    delta_soc = (-discharge_energy_kwh + charge_energy_kwh) / battery_capacity_kwh
    cumulative_soc_pct = np.cumsum(delta_soc) * 100.0

    tabl = tabl.copy()
    tabl["SoC"] = cumulative_soc_pct + initial_soc_pct
    tabl["BatteryCapacity_kWh"] = battery_capacity_kwh

    return tabl, battery_capacity_kwh


def build_battery_alert_message(
    tabl: pd.DataFrame,
    critical_soc_pct: float = 10.0,
) -> str | None:
    """
    Retourne un message si la batterie devient vide ou critique pendant le trajet.
    """

    if "SoC" not in tabl.columns or tabl.empty:
        return None

    min_index = tabl["SoC"].idxmin()
    min_row = tabl.loc[min_index]
    min_soc = float(min_row["SoC"])

    time_label = ""
    if "TimeHour" in tabl.columns:
        time_label = f" a {pd.Timestamp(min_row['TimeHour'])}"

    segment_label = ""
    if "StartStopName" in tabl.columns and "EndStopName" in tabl.columns:
        segment_label = f" sur le segment '{min_row['StartStopName']} -> {min_row['EndStopName']}'"

    if min_soc <= 0:
        return (
            "[ERREUR BATTERIE] La batterie se vide pendant le trajet"
            f"{time_label}{segment_label} (SoC min = {min_soc:.2f} %)."
        )

    if min_soc <= critical_soc_pct:
        return (
            "[ALERTE BATTERIE] La batterie devient critique pendant le trajet"
            f"{time_label}{segment_label} (SoC min = {min_soc:.2f} %)."
        )

    return None
