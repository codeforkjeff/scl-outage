"""
Seattle neighborhood lookup from coordinates using Shapely.

Neighborhood data downloaded from:
https://data-seattlecitygis.opendata.arcgis.com/datasets/SeattleCityGIS::neighborhood-map-atlas-neighborhoods
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from shapely.geometry import Point, shape
from shapely.strtree import STRtree


def default_geojson_path() -> Path:
    """Resolve the default path to nma_nhoods_sub.geojson.

    Checks in order:
    1. NEIGHBORHOODS_GEOJSON environment variable
    2. nma_nhoods_sub.geojson in same directory as this module
    """
    env_path = os.getenv("NEIGHBORHOODS_GEOJSON")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    repo_path = Path(__file__).resolve().parent / "nma_nhoods_sub.geojson"
    if repo_path.exists():
        return repo_path

    return repo_path


class NeighborhoodIndex:
    """Spatial index of Seattle neighborhoods using Shapely's STRtree."""

    def __init__(self, geojson_path: Path | str | None = None) -> None:
        self.geojson_path = Path(geojson_path) if geojson_path else default_geojson_path()
        if not self.geojson_path.exists():
            raise FileNotFoundError(
                f"Neighborhoods GeoJSON file not found at: {self.geojson_path}"
            )

        with open(self.geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features = data.get("features", [])
        self.geometries = []
        self.records: list[dict[str, Any]] = []

        for feature in features:
            geom = shape(feature["geometry"])
            props = feature.get("properties", {})
            self.geometries.append(geom)
            self.records.append(
                {
                    "s_hood": props.get("S_HOOD"),
                    "l_hood": props.get("L_HOOD"),
                    "alt_names": props.get("S_HOOD_ALT_NAMES"),
                    "object_id": props.get("OBJECTID"),
                }
            )

        self.tree = STRtree(self.geometries)

    def find_neighborhood(self, lat: float, lng: float) -> str | None:
        """Return the neighborhood name (S_HOOD) for the given coordinates, or None."""
        details = self.find_neighborhood_details(lat, lng)
        return details["s_hood"] if details else None

    def find_neighborhood_details(self, lat: float, lng: float) -> dict[str, Any] | None:
        """Return full details dictionary for the neighborhood at coordinates, or None."""
        if lat is None or lng is None:
            return None
        # GeoJSON uses [longitude, latitude] (x, y) coordinate order
        point = Point(lng, lat)
        matches = self.tree.query(point, predicate="intersects")
        if len(matches) == 0:
            return None
        return self.records[matches[0]]


# Global cached index for default path
_DEFAULT_INDEX: NeighborhoodIndex | None = None


def get_index(
    geojson_path: Path | str | None = None, force_reload: bool = False
) -> NeighborhoodIndex:
    """Return a cached or new NeighborhoodIndex."""
    global _DEFAULT_INDEX
    if geojson_path is not None:
        return NeighborhoodIndex(geojson_path)

    if _DEFAULT_INDEX is None or force_reload:
        _DEFAULT_INDEX = NeighborhoodIndex()
    return _DEFAULT_INDEX


def get_neighborhood(
    lat: float, lng: float, geojson_path: Path | str | None = None
) -> str | None:
    """Return the Seattle neighborhood name for the given lat and lng coordinate.

    Parameters:
        lat: Latitude (e.g. 47.63811)
        lng: Longitude (e.g. -122.37152)
        geojson_path: Optional custom path to nma_nhoods_sub.geojson.
                      Defaults to neighborhoods/nma_nhoods_sub.geojson.

    Returns:
        The neighborhood name (S_HOOD) as a string, or None if the coordinate
        does not fall within any mapped neighborhood.
    """
    index = get_index(geojson_path)
    return index.find_neighborhood(lat, lng)


def get_neighborhood_details(
    lat: float, lng: float, geojson_path: Path | str | None = None
) -> dict[str, Any] | None:
    """Return detailed neighborhood information for the given lat and lng coordinate.

    Returns:
        Dict with keys: 's_hood', 'l_hood', 'alt_names', 'object_id',
        or None if not found.
    """
    index = get_index(geojson_path)
    return index.find_neighborhood_details(lat, lng)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m scl_outage.neighborhoods <lat> <lng>")
        sys.exit(1)

    try:
        query_lat = float(sys.argv[1])
        query_lng = float(sys.argv[2])
    except ValueError:
        print(f"Error: Invalid coordinates '{sys.argv[1]}', '{sys.argv[2]}'. Lat and lng must be numbers.")
        sys.exit(1)

    details = get_neighborhood_details(query_lat, query_lng)
    if details:
        l_hood_str = f" ({details['l_hood']})" if details.get("l_hood") else ""
        print(f"{details['s_hood']}{l_hood_str}")
    else:
        print("None (coordinates not in a mapped neighborhood)")
