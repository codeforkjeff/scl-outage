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
                neighborhood = index.find_neighborhood(lat, lng)

                self.assertEqual(neighborhood.name, row["neighborhood"])


if __name__ == "__main__":
    unittest.main()
