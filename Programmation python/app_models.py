from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class BusParameters:
    mass_kg: float = 21950.0
    g: float = 9.81
    air_density: float = 1.2
    rolling_coeff: float = 0.010
    frontal_area_m2: float = 8.0
    drag_coeff: float = 0.65
    aux_power_kw: float = 2.5


@dataclass
class GeoPoint:
    lat: float
    lon: float
    altitude_m: float
    time_s: Optional[float] = None
    speed_m_s: Optional[float] = None


@dataclass
class AltimetryTile:
    path: Path
    ncols: int
    nrows: int
    xllcorner: float
    yllcorner: float
    cellsize: float
    nodata_value: float
    grid: Optional[List[List[float]]] = None

    @property
    def x_max(self) -> float:
        return self.xllcorner + self.ncols * self.cellsize

    @property
    def y_max(self) -> float:
        return self.yllcorner + self.nrows * self.cellsize


@dataclass
class AltimetryDataset:
    tiles: List[AltimetryTile]
    bucket_size_m: float = 1000.0
    tile_bucket_cache: Dict[tuple[int, int], Optional[AltimetryTile]] = field(default_factory=dict)
    altitude_cache: Dict[tuple[int, int], Optional[float]] = field(default_factory=dict)


@dataclass
class OnlineAltimetrySource:
    resource: str = "ign_rge_alti_wld"
    batch_size: int = 200
    altitude_cache: Dict[tuple[float, float], Optional[float]] = field(default_factory=dict)
