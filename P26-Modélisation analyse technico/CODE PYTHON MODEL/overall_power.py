import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def overall_power(
    PowerBus: np.ndarray,
    Pmppt_PV: np.ndarray,
    Cbat: float,
    timeinS: pd.DatetimeIndex,
    P_charge: np.ndarray,
    Scenario: int,
    StartDay: pd.Timestamp,
):
    """
    Évalue la répartition de la puissance au sein de la station de recharge.

    La batterie stationnaire joue un rôle tampon entre le PV, le réseau et
    les bus électriques.

    Parameters
    ----------
    PowerBus  : puissance agrégée des bus (kW)
    Pmppt_PV  : production PV brute minute par minute (W)
    Cbat      : capacité de la batterie stationnaire (kWh)
    timeinS   : axe temps seconde par seconde (DatetimeIndex)
    P_charge  : puissance de charge agrégée des bus (kW)
    Scenario  : entier (non utilisé ici, conservé pour compatibilité)
    StartDay  : timestamp de début de journée

    Returns
    -------
    Pbat   : puissance batterie stationnaire (kW), >0 = charge, <0 = décharge
    Pgrid  : puissance réseau (kW), >0 = soutirée, <0 = injectée
    Pmppt_PV_s : production PV interpolée à la seconde (kW)
    P_charge   : puissance de charge (kW, inchangée)
    dt     : pas de temps (s) = 1
    """
    len_pv = len(Pmppt_PV)

    timeinM = pd.date_range(start=StartDay, periods=len_pv, freq="min")
    timeinS_full = pd.date_range(start=StartDay, periods=len_pv * 60 + 1, freq="s")

    # Interpolation linéaire de Pmppt_PV (W→kW) à la seconde
    t_src = np.arange(len_pv)
    t_dst = np.linspace(0, len_pv - 1, len(timeinS_full))
    f_interp = interp1d(t_src, Pmppt_PV / 1000, kind="linear", fill_value="extrapolate")
    Pmppt_PV_s = f_interp(t_dst)

    # Harmonisation des longueurs (on prend le minimum commun)
    n = min(len(Pmppt_PV_s), len(P_charge))
    Pmppt_PV_s = Pmppt_PV_s[:n]
    P_charge_n = P_charge[:n]

    Cbat_floor = int(np.floor(Cbat))
    dt = 1          # seconde
    Loss_Factor = 0

    Pbat  = np.zeros(n)
    Pgrid = np.zeros(n)
    SoC   = np.zeros(n + 1)
    SoC[0] = 0.1   # SoC initial de la batterie stationnaire (10 %)

    for i in range(n):
        pv  = Pmppt_PV_s[i]
        pch = P_charge_n[i]

        if pv > pch:
            # Surplus PV
            excess = pv - pch
            if SoC[i] <= 0.9:
                Pbat[i]  = (1 - Loss_Factor) * excess
                dE       = Pbat[i] * dt / 3.6e3     # kWh
                SoC[i+1] = SoC[i] + dE / Cbat_floor
            else:
                Pgrid[i] = -(1 - Loss_Factor) * excess
                SoC[i+1] = SoC[i]
        else:
            # Déficit PV
            needed = pch - pv
            if SoC[i] > 0.1:
                Pbat[i]  = -(1 + Loss_Factor) * needed
                dE       = Pbat[i] * dt / 3.6e3     # kWh
                SoC[i+1] = SoC[i] + dE / Cbat_floor
            else:
                Pgrid[i] = (1 + Loss_Factor) * needed
                SoC[i+1] = SoC[i]

    # --- Tracé ---
    t_plot = timeinS_full[:n]

    fig, axes = plt.subplots(2, 1, num=29, figsize=(14, 8))

    axes[0].plot(t_plot, Pmppt_PV_s,   linewidth=1.5, label=r"$P_{PV}$")
    axes[0].plot(t_plot, Pbat,          linewidth=1.5, label=r"$P_{Batterie}$")
    axes[0].plot(t_plot, Pgrid,         linewidth=1.5, label=r"$P_{Réseau}$")
    axes[0].plot(t_plot, P_charge_n,    linewidth=1.5, label=r"$P_{Bus}$")
    axes[0].set_xlabel("Temps (Heures)", fontsize=12)
    axes[0].set_ylabel("Puissance (kW)", fontsize=12)
    axes[0].set_title(
        "Evolution de la puissance du bus, de la batterie, du réseau et du PV",
        fontsize=14,
    )
    axes[0].legend(loc="best", fontsize=10)
    axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axes[0].grid(True)

    axes[1].plot(t_plot, SoC[:n] * 100, linewidth=1.5)
    axes[1].set_xlabel("Temps (Heures)", fontsize=12)
    axes[1].set_ylabel("SoC (%)", fontsize=12)
    axes[1].set_title(
        "Evolution du SoC du stockage stationnaire pendant une journée", fontsize=14
    )
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axes[1].grid(True)

    plt.tight_layout()
    plt.draw()

    return Pbat, Pgrid, Pmppt_PV_s, P_charge_n, dt
