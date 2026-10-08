from pathlib import Path
from typing import Any

from .base import (
    convert_gdb_to_geojson,
    DataSource,
    load_neighborhoods_from_geojson,
)

GDB_PATH = Path(__file__).resolve().parent / "renton.gdb.zip"
GEOJSON_PATH = Path(__file__).resolve().parent / "renton_district.geojson"


def convert() -> dict[str, Any]:
    return convert_gdb_to_geojson(
        gdb_path=GDB_PATH, output_path=GEOJSON_PATH, layer="DistrictBoundaries"
    )


def extract_name(props: dict):
    return f"{props.get('NAME')}"


def get_renton_districts():
    # this is an odd dataset that seems to include all the cities in the surrounding area.
    # we just want Renton.
    all_cities = load_neighborhoods_from_geojson(GEOJSON_PATH, extract_name, datasource)
    cities_to_keep = ["Renton"]
    return [c for c in all_cities if c.name in cities_to_keep]


datasource = DataSource(
    "renton_district",
    "https://gismaps.rentonwa.gov/GISIMAGES/TEMPDOWNLOAD/zipfiles/CommunityAndCultureGDB.zip",
    GDB_PATH,
    GEOJSON_PATH,
    convert,
    get_renton_districts,
    50,
)
