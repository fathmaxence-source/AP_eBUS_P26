from __future__ import annotations

import numpy as np
import pandas as pd

from bus_models import BusModel, LEGACY_BUS_MODEL
from configuration_simulation import ConfigurationAlertesBatterie


def calculer_soc_parcours(
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
    tabl["SoC"] = np.minimum(cumulative_soc_pct + initial_soc_pct, 100.0)  # Limiter à 100% max
    tabl["BatteryCapacity_kWh"] = battery_capacity_kwh

    return tabl, battery_capacity_kwh


def construire_message_alerte_batterie(
    tabl: pd.DataFrame,
    configuration_alertes: ConfigurationAlertesBatterie | None = None,
    critical_soc_pct: float | None = None,
) -> str | None:
    """
    Retourne un message si la batterie devient vide ou critique pendant le trajet.
    """

    if configuration_alertes is None:
        configuration_alertes = ConfigurationAlertesBatterie()
    if critical_soc_pct is not None:
        configuration_alertes = ConfigurationAlertesBatterie(
            seuil_alerte_soc_pct=critical_soc_pct,
            seuil_echec_soc_pct=configuration_alertes.seuil_echec_soc_pct,
            interrompre_si_batterie_vide=(
                configuration_alertes.interrompre_si_batterie_vide
            ),
        )

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

    if min_soc <= configuration_alertes.seuil_echec_soc_pct:
        return (
            "[ERREUR BATTERIE] La batterie se vide pendant le trajet"
            f"{time_label}{segment_label} (SoC min = {min_soc:.2f} %)."
        )

    if min_soc <= configuration_alertes.seuil_alerte_soc_pct:
        return (
            "[ALERTE BATTERIE] La batterie devient critique pendant le trajet"
            f"{time_label}{segment_label} (SoC min = {min_soc:.2f} %)."
        )

    return None


def route_soc(
    tabl: pd.DataFrame,
    bus_model: BusModel | None = None,
) -> tuple[pd.DataFrame, float]:
    """
    Alias de compatibilite vers la nouvelle fonction de calcul.
    """

    return calculer_soc_parcours(tabl=tabl, bus_model=bus_model)


def build_battery_alert_message(
    tabl: pd.DataFrame,
    critical_soc_pct: float = 10.0,
) -> str | None:
    """
    Alias de compatibilite vers la nouvelle fonction d'alerte.
    """

    return construire_message_alerte_batterie(
        tabl=tabl,
        critical_soc_pct=critical_soc_pct,
    )
