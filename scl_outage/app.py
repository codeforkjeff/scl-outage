import copy
import datetime
import itertools
import json
import logging
import os
import re
from pathlib import Path
import time
from zoneinfo import ZoneInfo

import aiofiles
import aiofiles.os
from cachetools import cached, TTLCache
from filelock import AsyncFileLock
import httpx
from quart import abort, make_response, Quart, render_template, send_file

from .maps import generate_map, get_min_max, get_rings, map_filename
from .neighborhoods.all import get_neighborhood_index


URL = "https://utilisocial.io/datacapable/v2/p/scl/map/events"

TIMEZONE = ZoneInfo("America/Los_Angeles")

EVENTS_PATH = "events.json"
EVENTS_PATH_LOCK = "events.json.lock"
EVENTS_FILE_EXPIRATION = 2

app = Quart(__name__)

events_lock = AsyncFileLock(EVENTS_PATH_LOCK)

log = logging.getLogger(__name__)

if os.getenv("DEV"):
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("scl_outage").setLevel(logging.DEBUG)

    app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.before_serving
async def startup():
    get_neighborhood_index()


@app.context_processor
def utility_processor():
    def pretty_time(dt):
        s = dt.strftime("%I:%M") + dt.strftime("%p").lower()
        return re.sub(r"^0", "", s)

    def pretty_date(dt):
        return "/".join([re.sub(r"^0", "", dt.strftime(part)) for part in ["%m", "%d"]])

    def pretty_datetime(dt, hide_date_if_today=True):
        """show just time portion if date is today's date"""
        now = get_now()
        if isinstance(dt, datetime.datetime):
            if hide_date_if_today and now.strftime("%Y/%m/%d") == dt.strftime(
                "%Y/%m/%d"
            ):
                return pretty_time(dt)
            return pretty_time(dt) + " on " + pretty_date(dt)
        else:
            return dt or "-"

    return dict(
        pretty_datetime=pretty_datetime,
    )


@cached(cache=TTLCache(maxsize=1024, ttl=2))
def get_now():
    return datetime.datetime.now(tz=TIMEZONE)


async def get_events():
    raw = None
    events_timestamp = 0

    from_environ = os.environ.get("EVENTS_PATH")
    if from_environ:
        async with aiofiles.open(from_environ, encoding="utf-8") as f:
            raw = await f.read()
    else:
        if await aiofiles.os.path.exists(EVENTS_PATH):
            stat = await aiofiles.os.stat(EVENTS_PATH)
            events_timestamp = stat.st_mtime
        async with events_lock:
            if await aiofiles.os.path.exists(EVENTS_PATH):
                stat = await aiofiles.os.stat(EVENTS_PATH)
                events_timestamp = stat.st_mtime

            if (
                time.time() - events_timestamp <= (EVENTS_FILE_EXPIRATION * 60)
                and events_timestamp > 0
            ):
                log.debug(f"Loading cached {EVENTS_PATH}")
                async with aiofiles.open(EVENTS_PATH, encoding="utf-8") as f:
                    raw = await f.read()
            else:
                log.debug(f"Making request to {URL}")
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(URL)
                    resp.raise_for_status()
                    raw = resp.text
                async with aiofiles.open(
                    EVENTS_PATH, "w", encoding="utf-8"
                ) as output_file:
                    await output_file.write(raw)
                stat = await aiofiles.os.stat(EVENTS_PATH)
                events_timestamp = stat.st_mtime
    events = json.loads(raw)
    return (events, events_timestamp)


def timestamp_to_datetime(ts, input_type="milliseconds"):
    _ts = ts
    if input_type == "milliseconds":
        _ts = int(ts) / 1000
    return datetime.datetime.fromtimestamp(_ts).astimezone(tz=TIMEZONE)


def get_neighborhood_for_event(event) -> str:
    """
    find the midpoint in a geometry ring and use that to determine neighborhood,
    using the indexes available to us
    """
    rings = get_rings([event])
    lat_min, lat_max, lon_min, lon_max = get_min_max(rings)

    lat_mid = lat_min + ((lat_max - lat_min) / 2)
    lon_mid = lon_min + ((lon_max - lon_min) / 2)

    match = get_neighborhood_index().find_neighborhood(lat_mid, lon_mid)
    if match:
        return match.neighborhood.name

    log.warning(f"Could not find a neighborhood name for ({lat_mid}, {lon_mid})")

    return event["city"]


@app.route("/")
async def index():
    events_data, events_timestamp = await get_events()
    events = copy.deepcopy(events_data)

    total_outage_count = 0
    total_people_affected = 0

    for e in events:
        for time_field in ["startTime", "lastUpdatedTime", "etrTime"]:
            val = e.get(time_field)
            e[time_field] = timestamp_to_datetime(val) if val else "Unknown"
        e["status"] = e.get("status", "Unknown")

        e["neighborhood"] = get_neighborhood_for_event(e)

        total_outage_count += 1
        total_people_affected += e["numPeople"]

    by_neighborhood = list(
        itertools.groupby(events, lambda e: e.get("neighborhood", "Unknown"))
    )

    now = get_now()

    template_data = {
        "now": now,
        "ts": int(now.timestamp()),
        "events_file_expiration": EVENTS_FILE_EXPIRATION,
        "events": events,
        "by_district": by_neighborhood,
        "events_date": timestamp_to_datetime(events_timestamp, input_type="seconds"),
        "total_outage_count": total_outage_count,
        "total_people_affected": total_people_affected,
    }

    rendered = await render_template("index.jinja", **template_data)
    response = await make_response(rendered)

    # expire immediately
    response.headers["Expires"] = "0"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"

    return response


@app.route("/events_map/<event_ids_str>")
async def events_map(event_ids_str: str):
    events, _ = await get_events()

    event_ids = sorted([int(e_id.strip()) for e_id in event_ids_str.split(",")])

    # note we use 'identifier' which is the publicly visible ID on the frontend,
    # and not the 'id' field
    filtered_events = [e for e in events if int(e["identifier"]) in event_ids]

    if len(filtered_events) != len(event_ids):
        non_existent = set(event_ids) - set([e["identifier"] for e in filtered_events])
        abort(404, description=f"Non existent event ids: {non_existent}")

    output_dir = Path("maps")
    image_path = output_dir / map_filename(filtered_events)

    if not await aiofiles.os.path.exists(image_path):
        await generate_map(filtered_events, image_path, None, 0.35, True)

    return await send_file(image_path, mimetype="image/png")

