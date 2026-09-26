
# Seattle City Light Outage

See it here: https://scl.codefork.com

This is an unofficial, very low bandwidth version of [this page](https://www.seattle.gov/city-light/outages).

I made this so I can view outage information quickly on my phone, which has
bad reception when my home internet is down. The Seattle City Light page makes
over 300 requests and fetches over 5 MB of assets. This app renders a simple text
list of outages that's ~20 KB and static map images that average ~300 KB.

# How to Run

```sh
docker build . -t scl_outage
docker run -d --restart always -p 127.0.0.1:9000:8000 -v maps:/opt/scl_outage/maps -v tile_cache:/opt/scl_outage/tile_cache scl_outage
```

Load http://localhost:9000
