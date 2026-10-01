import copy
import datetime
import itertools
import json
import logging
import os
import re
from pathlib import Path
import time
import urllib.request
from zoneinfo import ZoneInfo

from cachetools import cached, TTLCache
from filelock import FileLock
from flask import abort, Flask, make_response, render_template, send_file

from .maps import generate_map, get_min_max, get_rings, map_filename
from .neighborhoods.all import get_neighborhood_index


URL = "https://utilisocial.io/datacapable/v2/p/scl/map/events"

TIMEZONE = ZoneInfo("America/Los_Angeles")

EVENTS_PATH = "events.json"
EVENTS_PATH_LOCK = "events.json.lock"
EVENTS_FILE_EXPIRATION = 2

app = Flask(__name__)

events_lock = FileLock(EVENTS_PATH_LOCK)

log = logging.getLogger(__name__)

if os.getenv("DEV"):
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("scl_outage").setLevel(logging.DEBUG)

    app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.context_processor
def utility_processor():
    def pretty_time(dt):
        s = dt.strftime("%I:%M") + dt.strftime("%p").lower()
        return re.sub(r"^0", "", s)

    def pretty_date(dt):
        """show just time portion if date is today's date"""
        now = get_now()
        if isinstance(dt, datetime.datetime):
            if now.strftime("%Y/%m/%d") == dt.strftime("%Y/%m/%d"):
                return pretty_time(dt)
            s = dt.strftime("%m/%d ") + pretty_time(dt)
            return re.sub(r"^0", "", s)
        else:
            return dt or "-"

    return dict(pretty_date=pretty_date)


@cached(cache=TTLCache(maxsize=1024, ttl=2))
def get_now():
    return datetime.datetime.now(tz=TIMEZONE)


def get_events():
    raw = None
    events_timestamp = 0

    from_environ = os.environ.get("EVENTS_PATH")
    if from_environ:
        with open(from_environ, encoding="utf-8") as f:
            raw = f.read()
    else:
        if os.path.exists(EVENTS_PATH):
            events_timestamp = os.path.getmtime(EVENTS_PATH)
        with events_lock:
            if time.time() - events_timestamp <= (EVENTS_FILE_EXPIRATION * 60):
                log.debug(f"Loading cached {EVENTS_PATH}")
                with open(EVENTS_PATH, encoding="utf-8") as f:
                    raw = f.read()
            else:
                log.debug(f"Making request to {URL}")
                with urllib.request.urlopen(URL) as f:
                    raw = f.read().decode("utf-8")
                    with open(EVENTS_PATH, "w", encoding="utf-8") as output_file:
                        output_file.write(raw)
                    events_timestamp = os.path.getmtime(EVENTS_PATH)
    events = json.loads(raw)
    return (events, events_timestamp)


def timestamp_to_datetime(ts, input_type="milliseconds"):
    _ts = ts
    if input_type == "milliseconds":
        _ts = int(ts) / 1000
    return datetime.datetime.fromtimestamp(_ts).astimezone(tz=TIMEZONE)


def prettify_datetime(dt):
    s = str(dt)
    return s[: s.index(".")]


def get_neighborhood_for_event(event):
    """
    find the midpoint in a geometry ring and use that to determine neighborhood,
    using the indexes available to us
    """
    rings = get_rings([event])
    lat_min, lat_max, lon_min, lon_max = get_min_max(rings)

    lat_mid = lat_min + ((lat_max - lat_min) / 2)
    lon_mid = lon_min + ((lon_max - lon_min) / 2)

    neighborhood = get_neighborhood_index().find_neighborhood(lat_mid, lon_mid)
    if neighborhood:
        return neighborhood.name

    log.warning(f"Could not find a neighborhood name for ({lat_mid}, {lon_mid})")

    return event["city"]


@app.route("/")
def index():
    events, events_timestamp = copy.deepcopy(get_events())

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

    response = make_response(render_template("index.jinja", **template_data))

    # expire immediately
    response.headers["Expires"] = "0"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"

    return response


@app.route("/events_map/<event_ids_str>")
def events_map(event_ids_str: str):
    events, _ = get_events()

    event_ids = sorted([int(e_id.strip()) for e_id in event_ids_str.split(",")])

    # note we use 'identifier' which is the publicly visible ID on the frontend,
    # and not the 'id' field
    filtered_events = [e for e in events if int(e["identifier"]) in event_ids]

    if len(filtered_events) != len(event_ids):
        non_existent = set(event_ids) - set([e["identifier"] for e in filtered_events])
        abort(404, description=f"Non existent event ids: {non_existent}")

    output_dir = Path(os.getcwd()) / Path("maps")
    image_path = Path(os.getcwd()) / output_dir / map_filename(filtered_events)

    if not image_path.exists():
        generate_map(filtered_events, image_path, None, 0.35, True)

    return send_file(image_path, mimetype="image/png")
