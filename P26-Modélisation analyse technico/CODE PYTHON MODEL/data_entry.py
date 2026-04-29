import pandas as pd
import numpy as np


def apply_scenario_modifications(tabl: pd.DataFrame, scenario: int) -> pd.DataFrame:
    """
    Applique les modifications spécifiques au scénario sur le tableau de données.
    
    Scénario 2 & 3 : Allonge le temps d'arrêt aux terminus (30s → 3min) pour
    permettre la recharge pendant les arrêts.
    
    Terminus = premier et dernier arrêt de chaque trajet (identifiés par changement de TripID).
    
    Parameters
    ----------
    tabl     : pd.DataFrame  données du trajet (colonnes : Stop, deltaT, TripID)
    scenario : int           numéro du scénario (1, 2 ou 3)
    
    Returns
    -------
    pd.DataFrame  données modifiées (avec colonne 'IsTerminusRecharge' pour les scénarios 2-3)
    """
    if "IsTerminusRecharge" not in tabl.columns:
        tabl = tabl.copy()
        tabl["IsTerminusRecharge"] = False
    else:
        tabl = tabl.copy()
    
    if scenario in (2, 3):
        # Identifier les terminus: dernier arrêt de chaque trajet
        # Un arrêt est un terminus si:
        # 1. Stop == 0 (c'est un arrêt)
        # 2. deltaT ≈ 30s (durée standard d'arrêt)
        # 3. C'est le dernier arrêt avant changement de TripID (terminus)
        
        if "TripID" in tabl.columns:
            trip_changes = tabl["TripID"] != tabl["TripID"].shift()
            terminus_indices = trip_changes[trip_changes].index - 1
            
            # Vérifier que ce sont bien des arrêts avec deltaT ≈ 30s
            terminus_mask = (
                tabl.index.isin(terminus_indices) &
                (tabl["Stop"] == 0) &
                (abs(tabl["deltaT"] - 30) < 0.1)
            )
            tabl.loc[terminus_mask, "deltaT"] = 3 * 60  # 30s → 3min (180s)
            tabl.loc[terminus_mask, "IsTerminusRecharge"] = True
    
    return tabl


def data_entry(path: str, scenario: int, N: int):
    """
    Charge et prépare les données de trajet à partir d'un fichier Excel.
 
    Parameters
    ----------
    path     : chemin vers le fichier .xlsx
    scenario : entier (1, 2 ou 3)
    N        : nombre de trajets à répéter
 
    Returns
    -------
    tabl  : pd.DataFrame  données complètes du service journalier
    route : int           nombre de lignes d'un trajet aller-retour
    """
    cols = ["PointID", "T", "Stop", "Latitude", "Longitude",
            "Alpha", "Total_Distance", "Distance"]
 
    raw = pd.read_excel(path, header=None)
    raw.columns = cols
 
    # Supprimer les lignes où la distance parcourue est nulle (sauf la 1ère)
    mask = np.concatenate([[False], raw["Distance"].values[1:] == 0])
    tabl = raw[~mask].copy().reset_index(drop=True)
 
    # Convertir le temps en secondes
    # Excel peut stocker l'heure comme un nombre décimal (fraction de jour)
    # ou comme un objet datetime.time selon le format de la cellule
    import datetime
    def to_seconds(val):
        if isinstance(val, datetime.time):
            return val.hour * 3600 + val.minute * 60 + val.second
        else:
            return float(val) * 24 * 60 * 60
 
    tabl["TimeinS"] = tabl["T"].apply(to_seconds)
    tabl.drop(columns=["T", "Latitude", "Longitude"], inplace=True)
 
    # Indices des arrêts (Stop == 0)
    indices_zero = tabl.index[tabl["Stop"] == 0].tolist()
    num_stops = len(indices_zero)
 
    v_avg = np.zeros(len(tabl))
    id_   = np.zeros(len(tabl))
 
    # Calcul de la vitesse moyenne entre deux arrêts successifs
    for i in range(num_stops - 1):
        start_idx = indices_zero[i]
        stop_idx  = indices_zero[i + 1]
 
        time_diff = tabl.at[stop_idx, "TimeinS"] - tabl.at[start_idx, "TimeinS"]
        dist_diff = tabl.at[stop_idx, "Total_Distance"] - tabl.at[start_idx, "Total_Distance"]
 
        if time_diff == 0:
            v_avg[start_idx + 1 : stop_idx + 1] = v_avg[start_idx]
        else:
            v_avr = dist_diff / time_diff
            v_avg[start_idx + 1 : stop_idx + 1] = v_avr
 
        id_[start_idx : stop_idx] = i + 1   # indexation 1-based comme MATLAB
 
    id_[-1] = num_stops
 
    tabl["Velocity"] = v_avg
    tabl["PointID"]  = id_.astype(int)
    tabl.loc[0, "PointID"] = 0
    tabl.drop(columns=["TimeinS"], inplace=True)
 
    # Calcul du deltaT
    delta_t = tabl["Distance"].values / np.maximum(v_avg, np.finfo(float).eps)
    delta_t[0] = 0.0
    tabl["deltaT"] = delta_t
    tabl.drop(columns=["Total_Distance"], inplace=True)
 
    # Insertion d'un temps d'arrêt de 30 s à chaque arrêt
    offset = 0
    for i, idx in enumerate(indices_zero):
        row_idx = idx + offset
        new_row = pd.DataFrame(
            [[i + 1, 0, 0, 0, 0, 30]],
            columns=tabl.columns
        )
        tabl = pd.concat(
            [tabl.iloc[: row_idx + 1], new_row, tabl.iloc[row_idx + 1:]],
            ignore_index=True
        )
        offset += 1
 
    # Conserver l'en-tête (1ère ligne) séparément
    header = tabl.iloc[[0]].copy()
    tabl   = tabl.iloc[1:].reset_index(drop=True)
 
    # Retournement : aller + retour
    flipped = tabl.iloc[1:-1].iloc[::-1].reset_index(drop=True)
    tabl    = pd.concat([tabl, flipped], ignore_index=True)
 
    route = len(tabl)          # taille d'un trajet aller-retour
    tabl  = pd.concat([tabl] * N, ignore_index=True)
    tabl  = pd.concat([header, tabl], ignore_index=True)
 
    # Passage à 3 min au terminus (scénarios 2 et 3)
    # On commence à l'index 3 (pas de charge nécessaire au départ, batterie pleine)
    if scenario in (2, 3):
        for i in range(2, len(tabl)):   # index 2 = 3ème ligne (0-based)
            pid = tabl.at[i, "PointID"]
            stp = tabl.at[i, "Stop"]
            dt  = tabl.at[i, "deltaT"]
            if (pid == 1 and stp == 0 and dt == 30) or \
               (pid == 26 and stp == 0 and dt == 30):
                tabl.at[i, "deltaT"] = 3 * 60
 
    # Ajout d'un trajet dépôt-terminus de 4 km à 12 m/s en début et fin
    depot_row = pd.DataFrame(
        [[0, 1, 0, 4000, 12, 4000 / 12]],
        columns=tabl.columns
    )
    tabl = pd.concat(
        [tabl.iloc[[0]], depot_row, tabl.iloc[1:], depot_row],
        ignore_index=True
    )
 
    # Temps cumulé et distance totale
    tabl["Time"]           = tabl["deltaT"].cumsum()
    tabl["Total_Distance"] = tabl["Distance"].cumsum()
 
    return tabl, route
 
