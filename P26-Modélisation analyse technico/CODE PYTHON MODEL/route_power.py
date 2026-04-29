from __future__ import annotations

import numpy as np
import pandas as pd

from bus_models import BusModel, LEGACY_BUS_MODEL
from configuration_simulation import ConfigurationRecharge


def _verifier_colonnes_puissance(
    tabl: pd.DataFrame,
    configuration_recharge: ConfigurationRecharge,
) -> None:
    colonnes_requises = {"Velocity", "Alpha"}
    if configuration_recharge.scenario in (2, 3):
        colonnes_requises.add("deltaT")
    if configuration_recharge.scenario == 3:
        colonnes_requises.update({"PointID", "Stop"})

    colonnes_manquantes = sorted(colonnes_requises.difference(tabl.columns))
    if colonnes_manquantes:
        raise ValueError(
            "Le tableau de parcours ne contient pas les colonnes requises "
            "pour le calcul de puissance : "
            + ", ".join(colonnes_manquantes)
        )

    if "deltaT" in tabl.columns and (tabl["deltaT"] < 0).any():
        raise ValueError("La colonne deltaT ne peut pas contenir de durees negatives.")
    if (tabl["Velocity"] < 0).any():
        raise ValueError("La colonne Velocity ne peut pas contenir de vitesses negatives.")


def _extraire_masse_kg(tabl: pd.DataFrame, model: BusModel) -> float | np.ndarray:
    """
    Utilise une masse dynamique si elle est deja presente dans le parcours.
    """

    for colonne in ("MasseTotaleBus_kg", "MassKg"):
        if colonne in tabl.columns:
            masses = tabl[colonne].astype(float).to_numpy()
            if (masses <= 0).any():
                raise ValueError(f"La colonne {colonne} doit contenir des masses > 0.")
            return masses
    return model.reference_mass_kg


def calculer_puissance_parcours(
    tabl: pd.DataFrame,
    configuration_recharge: ConfigurationRecharge,
    bus_model: BusModel | None = None,
) -> pd.DataFrame:
    """
    Calcule la puissance de traction et la puissance auxiliaire a chaque pas.
    """

    model = bus_model or LEGACY_BUS_MODEL
    _verifier_colonnes_puissance(tabl, configuration_recharge)

    g = 9.81
    cr = model.rolling_resistance_coefficient
    cd = model.drag_coefficient
    mass_kg = _extraire_masse_kg(tabl, model)
    air_density = model.air_density_kg_m3
    frontal_area = model.frontal_area_m2
    auxiliary_power_w = model.auxiliary_power_w
    acceleration = model.acceleration_m_s2

    velocity = tabl["Velocity"].values
    alpha = tabl["Alpha"].values

    pldm = velocity * (
        mass_kg * g * np.sin(alpha)
        + mass_kg * g * cr * np.cos(alpha)
        + 0.5 * air_density * velocity**2 * frontal_area * cd
        + mass_kg * acceleration
    )

    tabl = tabl.copy()
    tabl["Power"] = pldm + auxiliary_power_w
    tabl["PowerC"] = 0.0
    tabl["BusModelId"] = model.model_id
    tabl["BusModelName"] = model.display_name

    if configuration_recharge.scenario in (2, 3):
        tabl.loc[
            tabl["deltaT"] == configuration_recharge.duree_recharge_terminus_s,
            "PowerC",
        ] = configuration_recharge.puissance_borne_terminus_kw * 1000.0

    if configuration_recharge.scenario == 3:
        mask = (
            (tabl["PointID"].isin(configuration_recharge.points_recharge_intermediaire))
            & (tabl["Stop"] == 0)
            & (tabl["deltaT"] == configuration_recharge.duree_recharge_intermediaire_s)
        )
        tabl.loc[mask, "PowerC"] = (
            configuration_recharge.puissance_borne_intermediaire_kw * 1000.0
        )

    return tabl


def route_power(
    tabl: pd.DataFrame,
    scenario: int,
    bus_model: BusModel | None = None,
    configuration_recharge: ConfigurationRecharge | None = None,
) -> pd.DataFrame:
    """
    Alias de compatibilite vers la nouvelle fonction de calcul.
    """

    configuration = configuration_recharge or ConfigurationRecharge(scenario=scenario)
    return calculer_puissance_parcours(
        tabl=tabl,
        configuration_recharge=configuration,
        bus_model=bus_model,
    )
