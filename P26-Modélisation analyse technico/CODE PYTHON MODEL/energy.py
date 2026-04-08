import numpy as np


def energy(Pbat: np.ndarray, Pgrid: np.ndarray, Pmppt_PV: np.ndarray,
           P_charge: np.ndarray, dt: float) -> dict:
    """
    Calcule les bilans énergétiques de la station de recharge.

    Parameters
    ----------
    Pbat     : puissance batterie stationnaire (kW), >0 charge, <0 décharge
    Pgrid    : puissance réseau (kW), >0 soutirée, <0 injectée
    Pmppt_PV : production PV (kW)
    P_charge : puissance de charge des bus (kW)
    dt       : pas de temps (s)

    Returns
    -------
    dict contenant toutes les énergies (kWh)
    """
    # Séparation charge / décharge batterie
    PCh_Bat   = np.maximum(Pbat, 0)
    P_DCh_Bat = np.minimum(Pbat, 0)

    # Séparation injection / soutirage réseau
    PSup_Grid = np.maximum(Pgrid, 0)
    PIn_Grid  = np.minimum(Pgrid, 0)

    factor = dt / 3.6e3   # conversion W·s → kWh  (ici dt en s, Puissances en kW → ×1000 / 3.6e6)
    # Note : Puissances en kW → kWh = kW * s / 3600
    factor_kW = dt / 3600

    Energy_Ch_Bus      = float(np.sum(P_charge)  * factor_kW)
    Energy_PV          = float(np.sum(Pmppt_PV)  * factor_kW)
    Energy_Ch_Bat      = float(np.sum(PCh_Bat)   * factor_kW)
    Energy_Disch_Bat   = float(-np.sum(P_DCh_Bat)* factor_kW)
    Energy_Supply_Grid = float(np.sum(PSup_Grid)  * factor_kW)
    Energy_Inject_Grid = float(-np.sum(PIn_Grid)  * factor_kW)

    Energy_Supply = Energy_PV + Energy_Disch_Bat + Energy_Supply_Grid
    Energy_Taken  = Energy_Ch_Bus + Energy_Ch_Bat + Energy_Inject_Grid

    results = dict(
        Energy_Ch_Bus      = Energy_Ch_Bus,
        Energy_PV          = Energy_PV,
        Energy_Ch_Bat      = Energy_Ch_Bat,
        Energy_Disch_Bat   = Energy_Disch_Bat,
        Energy_Supply_Grid = Energy_Supply_Grid,
        Energy_Inject_Grid = Energy_Inject_Grid,
        Energy_Supply      = Energy_Supply,
        Energy_Taken       = Energy_Taken,
    )

    # Affichage récapitulatif
    print("=== Bilan énergétique (kWh) ===")
    for k, v in results.items():
        print(f"  {k:25s} : {v:10.2f} kWh")
    print(f"  {'Vérification (Supply)':25s} : {Energy_Supply:10.2f} kWh")
    print(f"  {'Vérification (Taken)':25s}  : {Energy_Taken:10.2f} kWh")

    return results
