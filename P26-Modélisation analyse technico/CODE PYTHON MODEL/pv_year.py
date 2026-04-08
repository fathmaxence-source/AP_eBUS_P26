import numpy as np
import pandas as pd
import scipy.io
import matplotlib.pyplot as plt


def pv_year(
    Npv: int,
    Switch: int,
    StartDay: pd.Timestamp,
    NextStartDay: pd.Timestamp,
):
    """
    Calcule la production PV sur une année et identifie le meilleur/pire jour.

    Parameters
    ----------
    Npv          : nombre de panneaux PV
    Switch       : 1 → meilleur jour, 2 → pire jour
    StartDay     : début de la fenêtre de simulation
    NextStartDay : fin de la fenêtre de simulation

    Returns
    -------
    Pmppt_PV    : np.ndarray  production PV sur la fenêtre (W)
    Energy_2j   : float       énergie totale sur la fenêtre (kWh)
    Cbat        : float       capacité batterie stationnaire recommandée (kWh)
    """
    # Chargement des données météo
    mat = scipy.io.loadmat("Meteo.mat", squeeze_me=True)
    Meteo = mat["Meteo"]
    g    = Meteo["g"].item()
    Tpv  = Meteo["Tpv"].item()
    Ta   = Meteo["Ta"].item()

    # Paramètres des panneaux
    Tstc  = 25        # Température STC (°C)
    gstc  = 1000      # Irradiation STC (W/m²)
    CoeffT = -0.37/100  # Coefficient de température (%/°C)
    Tnoct  = 20       # Température air NOCT (°C)
    gnoct  = 800      # Irradiation NOCT (W/m²)
    Pstc   = 345      # Puissance STC (Wc)

    # Puissance MPPT pour chaque pas de temps (shape : jours x minutes)
    Pmppt = Npv * Pstc * (g / gstc) * (1 + CoeffT * (Tpv - Tstc))

    # Énergie quotidienne (kWh)
    Energy_daily = np.sum(Pmppt, axis=1) * 60 / 3.6e6

    # Remplacement des NaN par la valeur précédente (forward fill)
    s = pd.Series(Energy_daily)
    Energy_daily = s.ffill().values

    # Tracé de la production annuelle
    plt.figure(30)
    plt.plot(Energy_daily, "o", linewidth=1.5, color=(0, 0.45, 0.74))
    plt.xlabel("Jour de l'année", fontsize=12)
    plt.ylabel("Energie (kWh)", fontsize=12)
    plt.title("Energie produite chaque jour de l'année", fontsize=14)
    plt.grid(True)
    plt.tight_layout()

    # Meilleur et pire jour
    idx1 = int(np.argmax(Energy_daily))
    idx2 = int(np.argmin(Energy_daily))
    Cbat = 0.5 * Energy_daily[idx1]
    id_  = [idx1, idx2]

    # Sélection du jour choisi et du jour suivant
    P_PV   = Pmppt[id_[Switch - 1], :]       # 0-based → Switch-1
    P_PV_N = Pmppt[id_[Switch - 1] + 1, :]

    # Grille temporelle minute par minute sur 24 h
    time_initial = pd.date_range("00:00", periods=1440, freq="min")

    # Indices correspondant à StartDay et NextStartDay dans la grille
    def time_of_day(ts):
        return ts.hour * 60 + ts.minute

    idx_start = time_of_day(StartDay)
    idx_next  = time_of_day(NextStartDay)

    Pmppt_PV = np.concatenate([P_PV[idx_start:], P_PV_N[:idx_next]])

    Energy_2j = float(np.sum(Pmppt_PV) * 60 / 3.6e6)

    return Pmppt_PV, Energy_2j, Cbat
