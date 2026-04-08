from __future__ import annotations

import numpy as np
import pandas as pd

from bus_models import BusModel, LEGACY_BUS_MODEL


def route_power(
    tabl: pd.DataFrame,
    scenario: int,
    bus_model: BusModel | None = None,
) -> pd.DataFrame:
    """
    Calcule la puissance de traction et la puissance auxiliaire a chaque pas.
    """

    model = bus_model or LEGACY_BUS_MODEL

    g = 9.81
    cr = model.rolling_resistance_coefficient
    cd = model.drag_coefficient
    mass_kg = model.reference_mass_kg
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

    if scenario in (2, 3):
        tabl.loc[tabl["deltaT"] == 3 * 60, "PowerC"] = 100e3

    if scenario == 3:
        mask = (
            (((tabl["PointID"] == 10) | (tabl["PointID"] == 22)))
            & (tabl["Stop"] == 0)
            & (tabl["deltaT"] == 30)
        )
        tabl.loc[mask, "PowerC"] = 50e3

    return tabl
