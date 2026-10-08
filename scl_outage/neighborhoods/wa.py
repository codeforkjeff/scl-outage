from pathlib import Path

from .base import DataSource, load_neighborhoods_from_geojson

GEOJSON_PATH = Path(__file__).resolve().parent / "wa.geojson"


def extract_name(props: dict):
    return props.get("CITY_DISSOLVE")


def get_wa_cities():
    all_cities = load_neighborhoods_from_geojson(GEOJSON_PATH, extract_name, datasource)
    # we don't need everything
    cities_to_keep = ["Burien", "Lake Forest Park", "SeaTac", "Tukwila"]
    return [c for c in all_cities if c.name in cities_to_keep]


# this is a list of all cities in WA, downloaded from:
# https://geo.wa.gov/datasets/WADOR::city-boundaries/about

datasource = DataSource("wa", None, None, GEOJSON_PATH, None, get_wa_cities, 50)
