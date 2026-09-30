"""
CLI for working with neighborhood data: namely, converting to geojson files
from various original data sources, and sanity checking coordinates
"""
import argparse
import urllib.request
from pathlib import Path

from .all import get_data_sources, get_neighborhood_index


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
        "command",
        type=str,
        help="command: load, lookup",
    )

    args = parser.parse_args()

    if args.command == "load":
        load()

    elif args.command == "lookup":
        if not args.coordinates:
            parser.error("Specify -c and provide lat,lng")

        (lat, lng) = [float(c) for c in args.coordinates.split(",")]
        neighborhood = get_neighborhood_index().find_neighborhood(lat, lng)
        if neighborhood:
            print(neighborhood.name)
        else:
            print(f"no neighborhood found for that coordinate")


if __name__ == "__main__":
    main()
