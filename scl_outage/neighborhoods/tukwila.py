from pathlib import Path
from typing import Any, List

from .base import (
    DataSource,
    load_neighborhoods_from_geojson,
    Neighborhood,
)


GEOJSON_PATH = Path(__file__).resolve().parent / "tukwila.geojson"


def extract_name(props: dict[str, Any]) -> str:
    return f"{props.get('Neighborho')} (Tukwila)"


def get_tukwila_neighborhoods() -> List[Neighborhood]:
    return load_neighborhoods_from_geojson(GEOJSON_PATH, extract_name, datasource)


# GeoJSON file dynamically generatwed from here:
# https://tukwila-open-data-tuk.hub.arcgis.com/maps/9d37eee223f940aabbb8bdc140fc691a

datasource = DataSource(
    "tukwila",
    None,
    None,
    GEOJSON_PATH,
    None,
    get_tukwila_neighborhoods,
    100,
)
