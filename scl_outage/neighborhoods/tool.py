"""
CLI for working with neighborhood data: namely, converting to geojson files
from various original data sources, and sanity checking coordinates
"""
import argparse
import asyncio
from itertools import chain
from pathlib import Path

import aiofiles
import aiofiles.os
import httpx
from shapely.geometry import mapping

from ..maps import (
    DEFAULT_PADDING,
    check_network,
    generate_map_from_rings,
    geojson_geometry_to_rings,
    get_geojson_rings,
)
from .all import create_neighborhood_index, get_data_sources, get_neighborhood_index


async def load():
    async with httpx.AsyncClient(timeout=30.0) as client:
        for data_source in get_data_sources():
            if data_source.datasource_path:
                if not await aiofiles.os.path.exists(data_source.datasource_path):
                    print(
                        f"Downloading from {data_source.url} to {data_source.datasource_path}"
                    )
                    resp = await client.get(data_source.url)
                    resp.raise_for_status()
                    async with aiofiles.open(data_source.datasource_path, "wb") as f:
                        await f.write(resp.content)

                geojson_exists = await aiofiles.os.path.exists(data_source.geojson_path)
                if not geojson_exists:
                    should_convert = True
                else:
                    ds_stat = await aiofiles.os.stat(data_source.datasource_path)
                    geo_stat = await aiofiles.os.stat(data_source.geojson_path)
                    should_convert = ds_stat.st_mtime >= geo_stat.st_mtime

                if should_convert:
                    print(f"Converting to {data_source.geojson_path}")
                    if data_source.convert_fn:
                        data_source.convert_fn()


async def coverage(
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

    await generate_map_from_rings(
        rings=rings,
        output_path=target_path,
        zoom_override=13,
        padding_miles=0.2,
        event={"title": "Neighborhood Coverage"},
    )
    print(f"Coverage map saved to {target_path}")
    return target_path


async def async_main() -> None:
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
        await load()

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
            print("no neighborhood found for that coordinate")

    elif args.command == "coverage":
        await coverage(
            output_path=args.output,
        )


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
