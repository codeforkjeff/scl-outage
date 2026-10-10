import argparse
import asyncio
from hashlib import md5
import io
import json
import logging
import math
import os
import os.path
import sys
import time
from typing import Iterable, List
from pathlib import Path

import aiofiles
import aiofiles.os
import httpx
from PIL import Image, ImageDraw, ImageFont
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.collections import PatchCollection

matplotlib.use("Agg")

CACHE_DIR = "tile_cache"
DEFAULT_INPUT = Path("events.json")
DEFAULT_OUTPUT = Path("maps")
DEFAULT_PADDING = 0.5  # miles
DEFAULT_ZOOM = None  # auto-select
TILE_SIZE = 256
OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
USER_AGENT = "SclOutage/1.0"

FILL_RGBA = (220, 40, 40, 160)
OUTLINE_RGBA = (160, 10, 10, 255)
OUTLINE_W = 2

MILES_PER_DEG_LAT = 69.0

log = logging.getLogger(__name__)


def deg2num(lat: float, lon: float, zoom: int) -> tuple:
    """Lat/lon -> fractional OSM tile number."""
    lat_r = math.radians(lat)
    n = 2**zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return x, y


def pad_bbox(lat_min, lat_max, lon_min, lon_max, miles: float):
    """Expand a bounding box by at least `miles` on all sides."""
    ctr_lat = (lat_min + lat_max) / 2.0
    d_lat = miles / MILES_PER_DEG_LAT
    d_lon = miles / (MILES_PER_DEG_LAT * max(math.cos(math.radians(ctr_lat)), 1e-6))
    return (lat_min - d_lat, lat_max + d_lat, lon_min - d_lon, lon_max + d_lon)


def choose_zoom(lat_span: float, lon_span: float, max_px: int = 1024) -> int:
    """Highest zoom where the padded bbox fits in max_px x max_px."""
    for z in range(18, 8, -1):
        n = 2**z
        px_x = lon_span / (360.0 / n) * TILE_SIZE
        px_y = lat_span / (180.0 / n) * TILE_SIZE
        if px_x <= max_px and px_y <= max_px:
            return z
    return 10


def cache_filename(params: Iterable):
    key = "_".join([str(p) for p in params])
    return "tile_" + key


async def fetch_tile(
    z: int, x: int, y: int, client: httpx.AsyncClient | None = None
):
    """returns an Image object"""
    key = (z, x, y)

    data = None

    filename = cache_filename(key)
    path = os.path.join(CACHE_DIR, filename)
    if await aiofiles.os.path.exists(path):
        async with aiofiles.open(path, "rb") as f:
            log.debug("got cached tile")
            data = await f.read()
    else:
        url = OSM_URL.format(z=z, x=x, y=y)
        headers = {"User-Agent": USER_AGENT}
        should_close = False
        active_client = client
        if active_client is None:
            active_client = httpx.AsyncClient(headers=headers, timeout=8.0)
            should_close = True
        try:
            for attempt in range(2):
                try:
                    resp = await active_client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.content
                        await aiofiles.os.makedirs(CACHE_DIR, exist_ok=True)
                        async with aiofiles.open(path, "wb") as f:
                            await f.write(data)
                        break
                except Exception:
                    if attempt == 0:
                        await asyncio.sleep(0.5)
        finally:
            if should_close:
                await active_client.aclose()

    if data is None:
        return None
    return Image.open(io.BytesIO(data)).convert("RGBA")


async def check_network() -> bool:
    """Quick probe - returns True if OSM tiles are reachable."""
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=5.0
        ) as client:
            resp = await client.get("https://tile.openstreetmap.org/0/0/0.png")
            return resp.status_code == 200
    except Exception:
        return False


def map_filename(events: List):
    events_sorted = sorted(events, key=lambda e: int(e["identifier"]))
    event_ids = [int(e["identifier"]) for e in events_sorted]
    event_ids_str = "_".join([str(event_id) for event_id in event_ids])

    hash = md5(str(get_rings(events_sorted)).encode("utf-8")).hexdigest()

    return f"region_{event_ids_str}_{hash}.png"


async def osm_render(rings, lat_min, lat_max, lon_min, lon_max, zoom):
    """Build an image from OSM tiles with the rings drawn on top."""
    fx_min, fy_max = deg2num(lat_min, lon_min, zoom)
    fx_max, fy_min = deg2num(lat_max, lon_max, zoom)

    tx_min = int(math.floor(fx_min)) - 1
    ty_min = int(math.floor(fy_min)) - 1
    tx_max = int(math.floor(fx_max)) + 1
    ty_max = int(math.floor(fy_max)) + 1
    max_t = 2**zoom - 1

    cols = tx_max - tx_min + 1
    rows = ty_max - ty_min + 1
    mosaic = Image.new(
        "RGBA", (cols * TILE_SIZE, rows * TILE_SIZE), (200, 200, 200, 255)
    )

    tile_requests = []
    for row, ty in enumerate(range(ty_min, ty_max + 1)):
        for col, tx in enumerate(range(tx_min, tx_max + 1)):
            tile_x = max(0, min(tx, max_t))
            tile_y = max(0, min(ty, max_t))
            tile_requests.append((col, row, tile_x, tile_y))

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=10.0
    ) as client:
        tasks = [
            fetch_tile(zoom, tile_x, tile_y, client=client)
            for _, _, tile_x, tile_y in tile_requests
        ]
        tiles = await asyncio.gather(*tasks)

    fetched = 0
    for (col, row, _, _), tile in zip(tile_requests, tiles):
        if tile:
            mosaic.paste(tile, (col * TILE_SIZE, row * TILE_SIZE))
            fetched += 1

    if fetched == 0:
        raise RuntimeError("No tiles fetched")

    def ll2px(lat, lon):
        fx, fy = deg2num(lat, lon, zoom)
        return int((fx - tx_min) * TILE_SIZE), int((fy - ty_min) * TILE_SIZE)

    overlay = Image.new("RGBA", mosaic.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for ring in rings:
        pts = [ll2px(c[1], c[0]) for c in ring]
        if len(pts) >= 2:
            draw.polygon(pts, fill=FILL_RGBA)
            draw.line(pts + [pts[0]], fill=OUTLINE_RGBA, width=OUTLINE_W)

    comp = Image.alpha_composite(mosaic, overlay)

    # crop to padded bbox
    px0, py0 = ll2px(lat_max, lon_min)
    px1, py1 = ll2px(lat_min, lon_max)
    px0 = max(0, px0)
    py0 = max(0, py0)
    px1 = min(comp.width, px1)
    py1 = min(comp.height, py1)
    if px1 > px0 and py1 > py0:
        comp = comp.crop((px0, py0, px1, py1))

    return comp.convert("RGB")


def mpl_render(rings, lat_min, lat_max, lon_min, lon_max, event: dict | None = None):
    """Render a clean cartographic-style map with matplotlib (no tile download)."""

    lon_span = lon_max - lon_min
    lat_span = lat_max - lat_min
    aspect = lon_span / max(lat_span, 1e-9)

    fig_w = 8.0
    fig_h = max(fig_w / aspect, 2.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=150)
    ax.set_facecolor("#e8f4f8")
    fig.patch.set_facecolor("#e8f4f8")

    # grid lines
    n_lon = max(2, int(lon_span / 0.005))
    n_lat = max(2, int(lat_span / 0.005))
    lon_ticks = [lon_min + i * lon_span / n_lon for i in range(n_lon + 1)]
    lat_ticks = [lat_min + i * lat_span / n_lat for i in range(n_lat + 1)]
    for lt in lon_ticks:
        ax.axvline(lt, color="#c8dce8", linewidth=0.5, zorder=1)
    for lt in lat_ticks:
        ax.axhline(lt, color="#c8dce8", linewidth=0.5, zorder=1)

    # inner bbox highlight
    all_lats = [c[1] for ring in rings for c in ring]
    all_lons = [c[0] for ring in rings for c in ring]
    inner_lat_min, inner_lat_max = min(all_lats), max(all_lats)
    inner_lon_min, inner_lon_max = min(all_lons), max(all_lons)

    pad_rect = mpatches.Rectangle(
        (inner_lon_min, inner_lat_min),
        inner_lon_max - inner_lon_min,
        inner_lat_max - inner_lat_min,
        linewidth=0,
        facecolor="#fde8e8",
        alpha=0.35,
        zorder=2,
    )
    ax.add_patch(pad_rect)

    # polygon rings
    polys = []
    for ring in rings:
        arr = [(c[0], c[1]) for c in ring]
        if arr:
            polys.append(MplPolygon(arr, closed=True))

    if polys:
        pc = PatchCollection(
            polys,
            facecolor=(220 / 255, 40 / 255, 40 / 255, 0.45),
            edgecolor=(160 / 255, 10 / 255, 10 / 255, 1.0),
            linewidth=1.2,
            zorder=3,
        )
        ax.add_collection(pc)

    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_aspect("equal")
    ax.set_xlabel("Longitude", fontsize=7, color="#555")
    ax.set_ylabel("Latitude", fontsize=7, color="#555")
    ax.tick_params(axis="both", labelsize=6, colors="#555")

    event_dict = event or {}
    city = event_dict.get("city", "")
    state = event_dict.get("state", "")
    title_str = event_dict.get("title", "Region")
    eid = event_dict.get("identifier", event_dict.get("id", ""))
    people = event_dict.get("numPeople", "")
    status = event_dict.get("status", "")

    header = f"{title_str}  #{eid}" if eid else title_str
    if people:
        header += (
            f"  \u00b7  {people:,} affected"
            if isinstance(people, int)
            else f"  \u00b7  {people} affected"
        )
    if status:
        header += f"  \u00b7  {status}"
    sub = f"{city}{', ' if city and state else ''}{state}"

    if header:
        ax.set_title(header, fontsize=9, fontweight="bold", color="#222", pad=6)
    if sub:
        ax.text(
            0.5,
            1.005,
            sub,
            transform=ax.transAxes,
            ha="center",
            va="bottom",
            fontsize=7,
            color="#555",
        )

    ax.text(
        0.01,
        0.01,
        "\u00a9 OpenStreetMap contributors (offline render)",
        transform=ax.transAxes,
        fontsize=5,
        color="#aaa",
        va="bottom",
    )

    buf = io.BytesIO()
    plt.savefig(
        buf, format="png", bbox_inches="tight", dpi=150, facecolor=fig.get_facecolor()
    )
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def get_rings(events):
    rings = []
    for event in events:
        poly_obj = event.get("polygons", {})
        rings.extend(poly_obj.get("rings", []))
    return rings


def geojson_geometry_to_rings(geom: dict):
    """
    Transforms the "geometry" property of a feature in a geojson file
    into "rings" format found in SCL events
    """
    rings = []
    if not geom:
        return
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])
    if gtype == "Polygon":
        rings.extend(coords)
    elif gtype == "MultiPolygon":
        for poly in coords:
            rings.extend(poly)
    return rings


async def get_geojson_rings(geojson_source: dict | Path | str) -> list:
    """Extract polygon coordinate rings from GeoJSON (dict, file path, or string path)."""
    if isinstance(geojson_source, (str, Path)):
        async with aiofiles.open(geojson_source, "r", encoding="utf-8") as f:
            content = await f.read()
            data = json.loads(content)
    else:
        data = geojson_source

    rings = []
    for feature in data.get("features", []):
        geom = feature.get("geometry")
        if not geom:
            continue
        gtype = geom.get("type")
        coords = geom.get("coordinates", [])
        if gtype == "Polygon":
            rings.extend(coords)
        elif gtype == "MultiPolygon":
            for poly in coords:
                rings.extend(poly)
    return rings


def get_min_max(rings):
    """Returns min and max lat and lon values in a set of events"""
    if not rings:
        return (None, None, None, None)

    all_lats = [c[1] for ring in rings for c in ring]
    all_lons = [c[0] for ring in rings for c in ring]
    if not all_lats:
        return (None, None, None, None)

    lat_min, lat_max = min(all_lats), max(all_lats)
    lon_min, lon_max = min(all_lons), max(all_lons)

    return (lat_min, lat_max, lon_min, lon_max)


# ══════════════════════════════════════════════════════════════════════════════
# Per-event driver
# ══════════════════════════════════════════════════════════════════════════════


async def generate_map_from_rings(
    rings: List,
    output_path: Path,
    zoom_override=None,
    padding_miles: float = DEFAULT_PADDING,
    use_osm: bool = True,
    event: dict | None = None,
):
    e_lat_min, e_lat_max, e_lon_min, e_lon_max = get_min_max(rings)
    if e_lat_min is None:
        return None

    lat_min, lat_max, lon_min, lon_max = pad_bbox(
        e_lat_min, e_lat_max, e_lon_min, e_lon_max, padding_miles
    )

    zoom = zoom_override or choose_zoom(lat_max - lat_min, lon_max - lon_min)

    if use_osm:
        img = await osm_render(rings, lat_min, lat_max, lon_min, lon_max, zoom)
    else:
        img = await asyncio.to_thread(
            mpl_render, rings, lat_min, lat_max, lon_min, lon_max, event
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(img.save, output_path, "PNG", optimize=True)
    return output_path


async def generate_map(
    events: List[dict],
    output_path: Path,
    zoom_override,
    padding_miles: float,
    use_osm: bool,
):
    rings = get_rings(events)
    return await generate_map_from_rings(
        rings,
        output_path,
        zoom_override=zoom_override,
        padding_miles=padding_miles,
        use_osm=use_osm,
        event=events[0] if events else None,
    )


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--input", default=str(DEFAULT_INPUT), help="Path to events.json")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output directory")
    p.add_argument("--zoom", type=int, default=None, help="Force OSM zoom level (1-18)")
    p.add_argument(
        "--padding",
        type=float,
        default=DEFAULT_PADDING,
        help="Minimum padding around each region in miles (default 0.5)",
    )
    p.add_argument(
        "--offline",
        action="store_true",
        help="Skip OSM tile check and use matplotlib fallback",
    )
    return p.parse_args()


async def async_main():
    args = parse_args()

    src = Path(args.input)
    if not await aiofiles.os.path.exists(src):
        sys.exit(f"Input file not found: {src}")
    async with aiofiles.open(src, "r", encoding="utf-8") as f:
        content = await f.read()
        events = json.loads(content)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.offline:
        use_osm = False
        log.debug("Offline mode: using matplotlib renderer.")
    else:
        log.debug("Checking OSM tile server connectivity...")
        use_osm = await check_network()
        log.debug(
            "OK - using OSM tiles."
            if use_osm
            else "OSM unreachable - falling back to matplotlib renderer."
        )

    log.debug(f"\nGenerating {len(events)} maps -> {out_dir}")

    ok = 0
    for i, ev in enumerate(events):
        label = ev.get("identifier") or ev.get("id") or i
        city = ev.get("city", "")
        log.debug(f"[{i+1:>3}/{len(events)}] #{label}  {city}")
        try:
            output_path = out_dir / map_filename([ev])
            out = await generate_map([ev], output_path, args.zoom, args.padding, use_osm)
            if out:
                log.debug(f"ok  {out.name}")
                ok += 1
            else:
                log.debug("skipped (no rings)")
        except Exception as e:
            log.error(f"ERROR  {e}")
        if use_osm:
            await asyncio.sleep(0.15)  # be polite to the tile server

    log.debug(f"Done - {ok}/{len(events)} maps saved to {out_dir}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
