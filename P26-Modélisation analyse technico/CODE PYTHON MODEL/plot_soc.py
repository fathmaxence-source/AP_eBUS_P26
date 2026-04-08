import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def plot_soc(
    tabl: pd.DataFrame,
    StartDay: pd.Timestamp,
    EndDay: pd.Timestamp,
    Pcharge: float,
    Eb: float,
    SoCi: float,
    j: int,
):
    """
    Trace le SoC (axe droit) et la puissance électrique (axe gauche)
    pendant la journée de service et la phase de recharge au dépôt.

    Parameters
    ----------
    tabl     : DataFrame avec colonnes 'SoC', 'TimeHour', 'Power', 'PowerC'
    StartDay : heure de début de service
    EndDay   : heure de fin de service
    Pcharge  : puissance de charge au dépôt (kW)
    Eb       : capacité batterie (kWh)
    SoCi     : SoC à la fin du service (fraction 0-1)
    j        : numéro de figure

    Returns
    -------
    Power      : np.ndarray  puissance concaténée (kW)
    timeVector : pd.DatetimeIndex timestamps correspondants
    """
    # Phase de service
    SoC1        = tabl["SoC"].values
    timeVector1 = tabl["TimeHour"]
    Pbus        = (-tabl["Power"] + tabl["PowerC"]).values / 1000  # W → kW

    # Phase de recharge (minute par minute, de EndDay à StartDay+1 jour)
    timeVector2 = pd.date_range(start=EndDay, end=StartDay + pd.Timedelta(days=1), freq="min")

    energy_factor = Pcharge * 60 / 3.6e3   # kWh par minute (Pcharge en kW)
    dSoC          = energy_factor / Eb * 100

    SoC2    = np.zeros(len(timeVector2))
    SoC2[0] = SoCi * 100
    for i in range(1, len(timeVector2)):
        SoC2[i] = SoC2[i - 1] + dSoC
    SoC2 = np.minimum(SoC2, 100.0)

    Pch = np.full(len(timeVector2), Pcharge)

    # Concaténation
    timeVector = timeVector1.tolist() + timeVector2.tolist()
    timeVector = pd.DatetimeIndex(timeVector)
    SoC        = np.concatenate([SoC1, SoC2])
    Power      = np.concatenate([Pbus, Pch])
    Power[SoC >= 100] = 0.0

    # Tracé
    fig, ax1 = plt.subplots(num=j + 6, figsize=(12, 5))

    color_pwr = (0, 0.45, 0.74)
    ax1.plot(timeVector, Power, linewidth=1.5, color=color_pwr, label="Puissance")
    ax1.set_xlabel("Temps (Heures)", fontsize=12)
    ax1.set_ylabel(
        "Demande et réponse en puissance électrique (kW)", fontsize=12, color=color_pwr
    )
    ax1.tick_params(axis="y", labelcolor=color_pwr)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    color_soc = (0.85, 0.33, 0.1)
    ax2 = ax1.twinx()
    ax2.plot(timeVector, SoC, "--", linewidth=1.5, color=color_soc, label="SoC")
    ax2.set_ylabel("SoC (%)", fontsize=12, color=color_soc)
    ax2.set_ylim(0, 110)
    ax2.tick_params(axis="y", labelcolor=color_soc)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize=10)

    plt.title(
        "Evolution de la puissance et du SoC du bus pendant une journée", fontsize=14
    )
    plt.grid(True)
    plt.tight_layout()
    plt.draw()

    return Power, timeVector
