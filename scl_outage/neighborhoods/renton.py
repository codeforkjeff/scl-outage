from pathlib import Path
from typing import Any

from .base import (
    convert_gdb_to_geojson,
    DataSource,
    load_neighborhoods_from_geojson,
)

GDB_PATH = Path(__file__).resolve().parent / "renton.gdb.zip"
GEOJSON_PATH = Path(__file__).resolve().parent / "renton.geojson"


def convert() -> dict[str, Any]:
    return convert_gdb_to_geojson(
        gdb_path=GDB_PATH, output_path=GEOJSON_PATH, layer="DesignatedNeighborhoods"
    )


def extract_name(props: dict):
    return f"{props.get('Neighborhood')} (Renton)"


def get_renton_neighborhoods():
    return load_neighborhoods_from_geojson(GEOJSON_PATH, extract_name, datasource)


datasource = DataSource(
    "renton",
    "https://gismaps.rentonwa.gov/GISIMAGES/TEMPDOWNLOAD/zipfiles/CommunityAndCultureGDB.zip",
    GDB_PATH,
    GEOJSON_PATH,
    convert,
    get_renton_neighborhoods,
    100,
)
