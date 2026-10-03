"""
CLI for working with neighborhood data: namely, converting to geojson files
from various original data sources, and sanity checking coordinates
"""
import argparse
from itertools import chain
import urllib.request
from pathlib import Path

from shapely.geometry import mapping

from ..maps import (
    DEFAULT_PADDING,
    check_network,
    generate_map_from_rings,
    geojson_geometry_to_rings,
    get_geojson_rings,
)
from .all import create_neighborhood_index, get_data_sources, get_neighborhood_index


def load():
    for data_source in get_data_sources():
        if data_source.datasource_path:
            if not data_source.datasource_path.exists():
                print(
                    f"Downloading from {data_source.url} to {data_source.datasource_path}"
                )
                urllib.request.urlretrieve(
                    data_source.url, str(data_source.datasource_path)
                )

            if (
                not data_source.geojson_path.exists()
                or data_source.datasource_path.stat().st_mtime
                >= data_source.geojson_path.stat().st_mtime
            ):
                print(f"Converting to {data_source.geojson_path}")
                if data_source.convert_fn:
                    data_source.convert_fn()


def coverage(
    output_path: Path | str = Path("coverage.png"),
) -> Path:
    target_path = Path(output_path)
    if target_path.is_dir():
        target_path = target_path / "coverage.png"

    def x(val):
        tmp = mapping(val)
        print(tmp)
        return tmp

    rings = []
    for data_source in get_data_sources():
        rings.extend(
            list(
                chain.from_iterable(
                    [
                        geojson_geometry_to_rings(mapping(n.geometry))
                        for n in data_source.neighborhoods_fn()
                    ]
                )
            )
        )

    # neighborhoods_dir = Path(__file__).resolve().parent
    # geojson_files = sorted(neighborhoods_dir.glob("*.geojson"))
    # if not geojson_files:
    #     raise FileNotFoundError(f"No .geojson files found in {neighborhoods_dir}")

    # rings = []
    # for geojson_file in geojson_files:
    #     rings.extend(get_geojson_rings(geojson_file))

    # print(rings)
    # if not rings:
    #     raise ValueError(f"No polygon rings found in {geojson_files}")

    generate_map_from_rings(
        rings=rings,
        output_path=target_path,
        zoom_override=13,
        padding_miles=0.2,
        event={"title": "Neighborhood Coverage"},
    )
    print(f"Coverage map saved to {target_path}")
    return target_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tool for working with neighborhood data"
    )
    parser.add_argument(
        "--coordinates",
        "-c",
        type=str,
        help="coordinates (lat,lng) to lookup neighborhood for",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("coverage.png"),
        help="output image path for coverage command (default: coverage.png)",
    )
    parser.add_argument(
        "--indexes",
        "-i",
        type=str,
        default=None,
        help="comma-separated neighborhood indexes to use for lookup (default: all)",
    )
    parser.add_argument(
        "command",
        type=str,
        help="command: load, lookup, coverage",
    )

    args = parser.parse_args()

    if args.command == "load":
        load()

    elif args.command == "lookup":
        if not args.coordinates:
            parser.error("Specify -c and provide lat,lng")

        (lat, lng) = [float(c) for c in args.coordinates.split(",")]

        if args.indexes:
            index = create_neighborhood_index(get_data_sources())
        else:
            index = get_neighborhood_index()

        match = index.find_neighborhood(lat, lng)
        if match:
            print(match.neighborhood.name)
        else:
            print(f"no neighborhood found for that coordinate")

    elif args.command == "coverage":
        coverage(
            output_path=args.output,
        )


if __name__ == "__main__":
    main()
