from pathlib import Path

from .base import DataSource, load_neighborhoods_from_geojson

GEOJSON_PATH = Path(__file__).resolve().parent / "seattle.geojson"


def extract_name(props: dict):
    s_hood = props.get("S_HOOD")
    l_hood = props.get("L_HOOD")
    if s_hood != l_hood:
        name = f"{s_hood} ({l_hood})"
    else:
        name = s_hood
    return name


def get_seattle_neighborhoods():
    return load_neighborhoods_from_geojson(GEOJSON_PATH, extract_name)


# Seattle data comes from a dynamically generated download link on this page,
# so we skip it here.
# https://data-seattlecitygis.opendata.arcgis.com/datasets/SeattleCityGIS::neighborhood-map-atlas-neighborhoods

datasource = DataSource(
    "seattle", None, None, GEOJSON_PATH, None, get_seattle_neighborhoods
)
