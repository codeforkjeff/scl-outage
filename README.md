
# Seattle City Light Outages

See it here: https://scl.codefork.com

This is an unofficial, very low bandwidth version of [this page](https://www.seattle.gov/city-light/outages).

I made this so I can view outage information quickly on my phone, which has
bad reception when my home internet is down. The Seattle City Light page makes
over 300 requests and fetches over 5 MB (compressed) of assets. This app renders
a simple text list of outages that's ~20 KB and static map images that average
~300 KB.

# How to Run

```sh
docker build . -t scl_outage
docker run -d --restart always -p 127.0.0.1:9000:8000 -v scl_outage_maps:/opt/scl_outage/maps -v scl_outage_tile_cache:/opt/scl_outage/tile_cache scl_outage
```

Load http://localhost:9000

# Local Development

```sh
DEV=1 uv run hypercorn --reload scl_outage:app

# use a sample events file
DEV=1 EVENTS_PATH=sample_events/events-multiple-areas.json uv run hypercorn --reload scl_outage:app

# run tests
uv run --dev pytest
```

# Neighborhood Data Sources

There are GeoJSON files committed into this repo containing neighborhood information for Seattle
and the surrounding cities that Seattle City Light services. Some of these have been created
from source data in a different format. To recreate the GeoJSON files:

```sh
uv run python3 -m scl_outage.neighborhoods.tool load
```

To generate a single map image showing which neighborhoods we have coverage for:

```sh
uv run python3 -m scl_outage.neighborhoods.tool coverage
```
