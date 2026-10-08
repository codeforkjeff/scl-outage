"""
Generic (non-city specific) code for handling neighborhood data
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any, Callable, List
from urllib.request import url2pathname

import numpy as np
import pyogrio
import pyogrio.raw
from pyproj import Transformer
import shapely
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform
from shapely.strtree import STRtree

log = logging.getLogger(__name__)


@dataclass
class DataSource:
    name: str
    url: str | None
    datasource_path: Path | None
    geojson_path: Path | None
    convert_fn: Callable | None
    neighborhoods_fn: Callable
    priority: int


@dataclass
class Neighborhood:
    name: str
    geometry: object
    source: DataSource


@dataclass
class Match:
    neighborhood: Neighborhood
    match_type: str
    distance: float | int | None = None


class NeighborhoodIndex:
    """Spatial index of neighborhoods using Shapely's STRtree."""

    def __init__(self, neighborhoods: List[Neighborhood]):
        self.geometries = [n.geometry for n in neighborhoods]
        self.neighborhoods = neighborhoods
        self.tree = STRtree(self.geometries)

    def find_neighborhood(self, lat: float, lng: float) -> Match | None:
        """Return full details dictionary for the neighborhood at coordinates, or None."""
        if lat is None or lng is None:
            return None
        # GeoJSON uses [longitude, latitude] (x, y) coordinate order
        point = Point(lng, lat)
        matches = self.tree.query(point, predicate="intersects")
        if len(matches) == 0:
            log.debug(f"Trying nearest matches for {lat, lng}")
            # 0.0006 is about 200 ft, I think
            hood_indices, distances = self.tree.query_nearest(
                point, exclusive=False, max_distance=0.0006, return_distance=True
            )
            if len(hood_indices) > 0:
                _neighborhood_matches = [
                    Match(self.neighborhoods[hood_i], "nearest", distance=distances[i])
                    for (i, hood_i) in enumerate(hood_indices)
                ]
                neighborhood_matches = sorted(
                    _neighborhood_matches,
                    key=lambda m: m.neighborhood.source.priority,
                    reverse=True,
                )
                log.debug(f"Nearest matches for {lat, lng}: {neighborhood_matches}")
                return neighborhood_matches[0]
            return None
        if len(matches) > 1:
            # de-prioritize source=="wa"
            neighborhood_matches = sorted(
                [self.neighborhoods[i] for i in matches],
                key=lambda n: n.source.priority,
                reverse=True,
            )
            log.warning(
                f"More than more match found for {lat}, {lng}: {neighborhood_matches}"
            )
            return Match(neighborhood_matches[0], "exact")

        return Match(self.neighborhoods[matches[0]], "exact")


def create_neighborhood(
    feature: dict, extract_name: Callable, source: DataSource
) -> Neighborhood:
    """
    Create a Neighborhood object out of a feature record found in a geojson file
    """
    geom = shape(feature["geometry"])
    props = feature.get("properties", {})
    name = extract_name(props)
    return Neighborhood(name=name, geometry=geom, source=source)


def load_neighborhoods_from_geojson(
    geojson_path: Path | str, extract_name: Callable, source: DataSource
) -> List[Neighborhood]:
    """
    Read a geojson file and create Neighborhood objects out of it
    """
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    neighborhoods = [
        create_neighborhood(f, extract_name, source) for f in data.get("features", [])
    ]

    return neighborhoods


def _sanitize_property_value(val: Any) -> Any:
    """Convert numpy / non-standard types to JSON-serializable values."""
    if val is None:
        return None
    if isinstance(val, (float, np.floating)):
        return None if np.isnan(val) else float(val)
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, np.datetime64):
        return str(val)
    return str(val)


def convert_gdb_to_geojson(
    gdb_path: Path,
    output_path: Path,
    layer: str,
) -> dict[str, Any]:
    """Convert a GDB .zip file or uncompressed directory to WGS84 GeoJSON."""

    # path to a .zip file MUST have a .gdb.zip suffix or pyogrio will complain
    # about it being an invalid file format

    if not gdb_path.exists():
        raise FileNotFoundError(f"File not found: {gdb_path}")

    # Validate layer exists in geodatabase
    available_layers = pyogrio.list_layers(gdb_path)
    layer_names = [l[0] for l in available_layers]
    if layer not in layer_names:
        raise ValueError(
            f"Layer '{layer}' not found in {gdb_path}. Available layers: {layer_names}"
        )

    # Read raw features and CRS metadata
    meta, _fids, geometries, field_data = pyogrio.raw.read(gdb_path, layer=layer)
    source_crs = meta.get("crs")
    field_names = list(meta.get("fields", []))

    # Prepare coordinate transformer if needed
    transformer: Transformer | None = None
    if source_crs and source_crs.upper() != "EPSG:4326":
        transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)

    features: list[dict[str, Any]] = []
    num_features = len(geometries)

    for i in range(num_features):
        wkb_bytes = geometries[i]
        geom = shapely.from_wkb(wkb_bytes)

        # Reproject to WGS84 (longitude, latitude)
        if transformer is not None:
            geom = transform(transformer.transform, geom)

        # Build feature properties
        properties = {}
        for j, name in enumerate(field_names):
            raw_val = field_data[j][i]
            properties[name] = _sanitize_property_value(raw_val)

        feature = {
            "type": "Feature",
            "properties": properties,
            "geometry": mapping(geom),
        }
        features.append(feature)

    geojson_data: dict[str, Any] = {
        "type": "FeatureCollection",
        "name": layer,
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }

    if output_path is not None:
        target_file = Path(output_path)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, indent=2)

    return geojson_data
