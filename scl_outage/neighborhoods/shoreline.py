from pathlib import Path
from typing import Any

from .base import (
    convert_gdb_to_geojson,
    DataSource,
    load_neighborhoods_from_geojson,
)


GDB_PATH = Path(__file__).resolve().parent / "land.gdb.zip"
GEOJSON_PATH = Path(__file__).resolve().parent / "shoreline.geojson"
LAYER = "Neighborhood"


def convert() -> dict[str, Any]:
    return convert_gdb_to_geojson(
        gdb_path=GDB_PATH, output_path=GEOJSON_PATH, layer=LAYER
    )


def extract_name(props: dict):
    return f"{props.get('NAME')} (Shoreline)"


def get_shoreline_neighborhoods():
    return load_neighborhoods_from_geojson(GEOJSON_PATH, extract_name, datasource)


datasource = DataSource(
    "shoreline",
    "https://cosweb.shorelinewa.gov/uploads/attachments/gis/data/download_page/land.gdb.zip",
    GDB_PATH,
    GEOJSON_PATH,
    convert,
    get_shoreline_neighborhoods,
    100,
)
