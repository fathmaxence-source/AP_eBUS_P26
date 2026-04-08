import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator


def unique_power(
    Power_Bus: np.ndarray,
    Start: pd.Timestamp,
    timeVector: pd.DatetimeIndex,
    StartDay: pd.Timestamp,
    NextStartDay: pd.Timestamp,
):
    """
    Interpole la puissance du bus sur une grille temporelle uniforme à la seconde,
    puis extrait le segment compris entre StartDay et NextStartDay.

    Parameters
    ----------
    Power_Bus    : tableau de puissance brute (kW)
    Start        : timestamp de début du service du bus
    timeVector   : timestamps associés à Power_Bus
    StartDay     : début de la fenêtre de sortie (timestamp)
    NextStartDay : fin   de la fenêtre de sortie (timestamp)

    Returns
    -------
    PowerBus : np.ndarray  puissance interpolée sur la fenêtre [StartDay, NextStartDay]
    timeinS  : pd.DatetimeIndex timestamps correspondants
    """
    # Grille uniforme d'une journée (86 400 secondes) à partir de Start
    timeinS = pd.date_range(start=Start, periods=1440 * 60, freq="s")

    # Dédoublonnage du vecteur temps source
    _, idx1 = np.unique(timeVector, return_index=True)
    timeVector_unique = timeVector[idx1]
    Power_unique      = np.asarray(Power_Bus)[idx1]

    # Conversion en secondes depuis une origine commune pour l'interpolateur
    origin = timeVector_unique[0]
    t_src  = (timeVector_unique - origin).total_seconds()
    t_dst  = (timeinS           - origin).total_seconds()

    # Interpolation PCHIP (équivalent à 'pchip' MATLAB), NaN hors domaine
    interp = PchipInterpolator(t_src, Power_unique, extrapolate=False)
    PowerBus1 = interp(t_dst)   # NaN en dehors de l'intervalle source

    # Triplication pour identifier le segment d'itinéraire commun
    delta_day = pd.Timedelta(days=1)
    PowerBus_triple = np.concatenate([PowerBus1, PowerBus1, PowerBus1])
    timeinS_triple  = pd.DatetimeIndex(
        np.concatenate([
            timeinS - delta_day,
            timeinS,
            timeinS + delta_day,
        ])
    )

    # Extraction du segment [StartDay, NextStartDay]
    idx_start = np.searchsorted(timeinS_triple, StartDay)
    idx_end   = np.searchsorted(timeinS_triple, NextStartDay)

    PowerBus = PowerBus_triple[idx_start : idx_end + 1]
    timeinS_out = timeinS_triple[idx_start : idx_end + 1]

    return PowerBus, timeinS_out
