from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class BusModel:
    """
    Parametres d'un modele de bus electrique.

    Les valeurs de masse, dimensions, batterie et puissance de traction
    proviennent de fiches techniques officielles. La masse retenue pour le
    calcul est une masse de reference chargee basee sur le poids total
    autorise en charge de la fiche technique.
    """

    model_id: str
    display_name: str
    manufacturer: str
    popularity_scope: str
    popularity_note: str
    length_m: float
    width_m: float
    height_m: float
    reference_mass_kg: float
    battery_capacity_kwh: float
    traction_power_kw: float
    rolling_resistance_coefficient: float = 1e-2
    drag_coefficient: float = 0.7
    air_density_kg_m3: float = 1.2
    auxiliary_power_w: float = 2.5e3
    acceleration_m_s2: float = 0.0
    source_urls: tuple[str, ...] = ()

    @property
    def frontal_area_m2(self) -> float:
        return self.width_m * self.height_m

    def to_record(self) -> dict[str, object]:
        record = asdict(self)
        record["frontal_area_m2"] = self.frontal_area_m2
        record["source_urls"] = " | ".join(self.source_urls)
        return record


BUS_MODELS: dict[str, BusModel] = {
    "heuliez_gx337_elec": BusModel(
        model_id="heuliez_gx337_elec",
        display_name="Heuliez GX 337 ELEC",
        manufacturer="Heuliez Bus / IVECO BUS",
        popularity_scope="France",
        popularity_note="Reference France : presente comme le modele urbain electrique le plus vendu en France depuis 2020.",
        length_m=12.050,
        width_m=2.550,
        height_m=3.350,
        reference_mass_kg=20_000.0,
        battery_capacity_kwh=350.0,
        traction_power_kw=160.0,
        source_urls=(
            "https://www.ivecogroup.com/media/brand_press_releases/2025/EMEA-%28English%29/Iveco-Bus/iveco_bus_signs_three_major_framework_agreements_with_le-de-france_mobilits_to_achieve_100_clean_buses_in_the_region_by_2030_20251030T085844T052_ckim1yvpckhnsc2gkbdewqa3",
            "https://www.heuliezbus.com/fr/vue/produits/bus/GX-ELEC/FT_GX337_ELEC.pdf",
        ),
    ),
    "mercedes_ecitaro": BusModel(
        model_id="mercedes_ecitaro",
        display_name="Mercedes-Benz eCitaro",
        manufacturer="Mercedes-Benz Buses / Daimler Buses",
        popularity_scope="Europe",
        popularity_note="Reference Europe : plus de 2 500 eCitaro etaient deja en service chez des operateurs europeens mi-2025.",
        length_m=12.135,
        width_m=2.550,
        height_m=3.400,
        reference_mass_kg=19_500.0,
        battery_capacity_kwh=555.0,
        traction_power_kw=280.0,
        source_urls=(
            "https://www.daimlertruck.com/en/newsroom/pressrelease/electric-buses-on-the-road-to-success-more-than-2500-mercedes-benz-ecitaro-buses-in-use-by-european-transport-companies-53114299",
            "https://www.daimlertruck.com/en/newsroom/pressrelease/vehicle-profile-the-mercedes-benz-ecitaro-exhibition-vehicle-technical-data-53100234",
        ),
    ),
    "solaris_urbino_12_electric": BusModel(
        model_id="solaris_urbino_12_electric",
        display_name="Solaris Urbino 12 electric",
        manufacturer="Solaris Bus & Coach",
        popularity_scope="Europe",
        popularity_note="Reference Europe : l'Urbino 12 electric est presente par Solaris comme son best-seller electrique.",
        length_m=12.000,
        width_m=2.550,
        height_m=3.300,
        reference_mass_kg=20_000.0,
        battery_capacity_kwh=420.0,
        traction_power_kw=220.0,
        source_urls=(
            "https://www.solarisbus.com/en/press/mobility-move-2024-new-version-of-the-solaris-urbino-12-electric-bus-debuts-2121",
            "https://www.solarisbus.com/public/assets/Biuro_prasowe/2023_05_11_UITP_zapro/Technical_details_Solaris_Urbino_12_electric.pdf",
        ),
    ),
    "volvo_7900_electric": BusModel(
        model_id="volvo_7900_electric",
        display_name="Volvo 7900 Electric",
        manufacturer="Volvo Buses",
        popularity_scope="Europe",
        popularity_note="Bus electrique 12m de Volvo avec batterie de 200 kWh, tres repandu en Scandinavie et Europe du Nord.",
        length_m=12.000,
        width_m=2.550,
        height_m=3.300,
        reference_mass_kg=19_000.0,
        battery_capacity_kwh=200.0,
        traction_power_kw=160.0,
        source_urls=(
            "https://www.volvobuses.com/en/our-offering/buses/volvo-7900-electric.html",
        ),
    ),
}


DEFAULT_BUS_MODEL_ID = "heuliez_gx337_elec"


LEGACY_BUS_MODEL = BusModel(
    model_id="legacy_default",
    display_name="Legacy Default Bus",
    manufacturer="Internal legacy model",
    popularity_scope="Legacy",
    popularity_note="Parametres historiques utilises avant l'introduction des modeles selectionnables.",
    length_m=12.0,
    width_m=2.550,
    height_m=3.302,
    reference_mass_kg=19_500.0 + 35.0 * 70.0,
    battery_capacity_kwh=150.0,
    traction_power_kw=0.0,
)


def get_bus_model(model_id: str) -> BusModel:
    if model_id not in BUS_MODELS:
        available_ids = ", ".join(sorted(BUS_MODELS))
        raise ValueError(f"Modele de bus inconnu '{model_id}'. Modeles disponibles : {available_ids}")
    return BUS_MODELS[model_id]


def list_bus_models() -> list[BusModel]:
    return [BUS_MODELS[key] for key in sorted(BUS_MODELS)]


def build_bus_models_reference_table() -> pd.DataFrame:
    records = [model.to_record() for model in list_bus_models()]
    return pd.DataFrame(records)
