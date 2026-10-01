#!/usr/bin/env python3
import argparse
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
import urllib.error
import urllib.request
from pathlib import Path

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


def fetch_tile(z: int, x: int, y: int):
    """returns an Image object"""
    key = (z, x, y)

    data = None

    filename = cache_filename(key)
    path = os.path.join(CACHE_DIR, filename)
    if os.path.exists(path):
        with open(path, "rb") as f:
            log.debug("got cached tile")
            data = f.read()
    else:
        url = OSM_URL.format(z=z, x=x, y=y)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = r.read()
                    with open(path, "wb") as f:
                        f.write(data)
                    break
            except Exception:
                if attempt == 0:
                    time.sleep(0.5)

    return Image.open(io.BytesIO(data)).convert("RGBA")


def check_network() -> bool:
    """Quick probe - returns True if OSM tiles are reachable."""
    try:
        req = urllib.request.Request(
            "https://tile.openstreetmap.org/0/0/0.png",
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
        return True
    except Exception:
        return False


def map_filename(events: List):
    events_sorted = sorted(events, key=lambda e: int(e["identifier"]))
    event_ids = [int(e["identifier"]) for e in events_sorted]
    event_ids_str = "_".join([str(event_id) for event_id in event_ids])

    hash = md5(str(get_rings(events_sorted)).encode("utf-8")).hexdigest()

    return f"region_{event_ids_str}_{hash}.png"


def osm_render(rings, lat_min, lat_max, lon_min, lon_max, zoom):
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

    fetched = 0
    for row, ty in enumerate(range(ty_min, ty_max + 1)):
        for col, tx in enumerate(range(tx_min, tx_max + 1)):
            tile = fetch_tile(zoom, max(0, min(tx, max_t)), max(0, min(ty, max_t)))
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


def get_geojson_rings(geojson_source: dict | Path | str) -> list:
    """Extract polygon coordinate rings from GeoJSON (dict, file path, or string path)."""
    if isinstance(geojson_source, (str, Path)):
        with open(geojson_source, "r", encoding="utf-8") as f:
            data = json.load(f)
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


def generate_map_from_rings(
    rings: List,
    output_path: Path,
    zoom_override=None,
    padding_miles: float = DEFAULT_PADDING,
    use_osm: bool = True,
    event: dict | None = None,
):
    e_lat_min, e_lat_max, e_lon_min, e_lon_max = get_min_max(rings)

    lat_min, lat_max, lon_min, lon_max = pad_bbox(
        e_lat_min, e_lat_max, e_lon_min, e_lon_max, padding_miles
    )

    zoom = zoom_override or choose_zoom(lat_max - lat_min, lon_max - lon_min)

    if use_osm:
        img = osm_render(rings, lat_min, lat_max, lon_min, lon_max, zoom)
    else:
        img = mpl_render(rings, lat_min, lat_max, lon_min, lon_max, event)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG", optimize=True)
    return output_path


def generate_map(
    events: List[dict],
    output_path: Path,
    zoom_override,
    padding_miles: float,
    use_osm: bool,
):
    rings = get_rings(events)
    return generate_map_from_rings(
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


def main():
    args = parse_args()

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"Input file not found: {src}")
    with open(src) as f:
        events = json.load(f)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.offline:
        use_osm = False
        log.debug("Offline mode: using matplotlib renderer.")
    else:
        log.debug("Checking OSM tile server connectivity...")
        use_osm = check_network()
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
            out = generate_map([ev], output_path, args.zoom, args.padding, use_osm)
            if out:
                log.debug(f"ok  {out.name}")
                ok += 1
            else:
                log.debug("skipped (no rings)")
        except Exception as e:
            log.error(f"ERROR  {e}")
        if use_osm:
            time.sleep(0.15)  # be polite to the tile server

    log.debug(f"Done - {ok}/{len(events)} maps saved to {out_dir}")


if __name__ == "__main__":
    main()
