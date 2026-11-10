import json
from pathlib import Path
from scl_outage.app import get_neighborhood_for_event


def test_get_neighborhood_for_event():
    events = json.loads(
        Path("sample_events/events-weird-regions.json").read_text(encoding="utf-8")
    )
    # midpoint algorithm places this event in SLU, but it's really
    # in Capitol Hill with a weird straggler region in Queen Area.
    event = [e for e in events if e["identifier"] == "225710"][0]
    hood = get_neighborhood_for_event(event)
    assert hood == "Stevens (Capitol Hill)"
