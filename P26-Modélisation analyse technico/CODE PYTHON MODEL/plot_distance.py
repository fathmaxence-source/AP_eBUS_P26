import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


def plot_distance(tabl: pd.DataFrame, route: int, j: int) -> None:
    """
    Trace la distance parcourue (axe gauche) et la vitesse (axe droit)
    en fonction du temps, pour un trajet donné.

    Parameters
    ----------
    tabl  : DataFrame contenant les colonnes 'TimeHour', 'Total_Distance', 'Velocity'
    route : nombre de lignes correspondant à un trajet aller-retour
    j     : numéro de figure
    """
    H = tabl["TimeHour"].iloc[: route + 3].copy()
    D = tabl["Total_Distance"].iloc[: route + 3].copy()
    V = (tabl["Velocity"].iloc[: route + 3] * 3.6).copy()   # m/s → km/h

    # Supprimer les 3 premières lignes (en-tête / dépôt)
    H = H.iloc[3:].reset_index(drop=True)
    D = D.iloc[3:].reset_index(drop=True)
    V = V.iloc[3:].reset_index(drop=True)

    # Remplacer les vitesses nulles par la valeur précédente
    V_arr = V.values.copy()
    for i in range(2, len(V_arr)):
        if V_arr[i] == 0:
            V_arr[i] = V_arr[i - 1]

    fig, ax1 = plt.subplots(num=j, figsize=(12, 5))

    # Distance
    color_dist = (0, 0.45, 0.74)
    ax1.plot(H, D / 1000, "-", linewidth=1.5, color=color_dist, label="Distance")
    ax1.set_xlabel("Temps (Heures)", fontsize=12)
    ax1.set_ylabel("Distance (km)", fontsize=12, color=color_dist)
    ax1.tick_params(axis="y", labelcolor=color_dist)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    # Vitesse
    color_speed = (0.85, 0.33, 0.1)
    ax2 = ax1.twinx()
    ax2.plot(H, V_arr, "--", linewidth=1.5, color=color_speed, label="Vitesse")
    ax2.set_ylabel("Vitesse (km/h)", fontsize=12, color=color_speed)
    ax2.tick_params(axis="y", labelcolor=color_speed)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best", fontsize=10)

    plt.title(
        "Données quotidiennes : Distance parcourue et vitesse pendant un trajet",
        fontsize=14,
    )
    plt.grid(True)
    plt.tight_layout()
    plt.draw()
