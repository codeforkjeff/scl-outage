from pathlib import Path

from .base import DataSource, load_neighborhoods_from_geojson

GEOJSON_PATH = Path(__file__).resolve().parent / "wa_cdp.geojson"


def extract_name(props: dict):
    return props.get("NAME")


def get_wa_cdp():
    all_places = load_neighborhoods_from_geojson(GEOJSON_PATH, extract_name, datasource)
    # we don't need everything
    places_to_keep = [
        "Boulevard Park",
        "Bryn Mawr-Skyway",
        "White Center",
    ]
    return [place for place in all_places if place.name in places_to_keep]


# this is a list of census designated places in WA downloaded from:
# https://geo.wa.gov/datasets/wa-ofm::saep-census-designated-places/about

datasource = DataSource("wa_uninc", None, None, GEOJSON_PATH, None, get_wa_cdp, 100)
