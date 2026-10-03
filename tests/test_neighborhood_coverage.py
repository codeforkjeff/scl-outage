import csv
from pathlib import Path
import unittest

from scl_outage.neighborhoods.all import get_neighborhood_index


class TestNeighborhoods(unittest.TestCase):
    def test_known_neighborhood_locations(self):
        index = get_neighborhood_index()

        script_dir = Path(__file__).parent.resolve()

        with open(f"{script_dir}/neighborhoods.csv") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                lat = float(row["latitude"])
                lng = float(row["longitude"])
                match = index.find_neighborhood(lat, lng)
                self.assertIsNotNone(match)

                self.assertEqual(match.neighborhood.name, row["neighborhood"])
                self.assertEqual(match.match_type, "exact")

    def test_nearest_match(self):
        index = get_neighborhood_index()

        # this coordinate actually appeared in an SCL event.
        # it's on the waterfront just outside the boundary for Eastlake, so it
        # should match by "nearest"
        match = index.find_neighborhood(47.64536, -122.32791)

        self.assertIsNotNone(match)

        self.assertEqual(match.neighborhood.name, "Eastlake (Cascade)")
        self.assertEqual(match.match_type, "nearest")

        # middle of Lake Washington, this should be far enough away from
        # any neighborhood to return None
        match = index.find_neighborhood(47.662884, -122.236269)

        self.assertIsNone(match)


if __name__ == "__main__":
    unittest.main()
