"""Tests for Shoreline boundary extraction and spatial lookup."""

import unittest

from scl_outage.neighborhoods.base import NeighborhoodIndex
from scl_outage.neighborhoods.shoreline import (
    get_shoreline_neighborhoods,
)


class TestShoreline(unittest.TestCase):
    def test_known_locations_in_shoreline(self):
        inside_coords = [
            (47.7562, -122.3458, "Meridian Park"),
            (47.7715, -122.3850, "Richmond Beach"),
            (47.7680, -122.3430, "Echo Lake"),
            (47.7510, -122.3660, "Highland Terrace"),
        ]
        neighborhood_index = NeighborhoodIndex(get_shoreline_neighborhoods())
        for lat, lng, name in inside_coords:
            with self.subTest(lat=lat, lng=lng, location=name):
                neighborhood = neighborhood_index.find_neighborhood(lat, lng)
                self.assertIsNotNone(neighborhood)
                self.assertEqual(neighborhood.name, f"{name} (Shoreline)")

    def test_known_locations_outside_shoreline(self):
        outside_coords = [
            (47.6205, -122.3493, "Space Needle, Seattle"),
            (47.6687, -122.3845, "Ballard, Seattle"),
            (47.6815, -122.3255, "Green Lake, Seattle"),
            (47.6101, -122.2015, "Downtown Bellevue"),
            (47.8107, -122.3774, "Edmonds, WA (North of Shoreline)"),
            (0.0, 0.0, "Gulf of Guinea"),
        ]
        neighborhood_index = NeighborhoodIndex(get_shoreline_neighborhoods())
        for lat, lng, name in outside_coords:
            with self.subTest(lat=lat, lng=lng, location=name):
                self.assertIsNone(neighborhood_index.find_neighborhood(lat, lng))


if __name__ == "__main__":
    unittest.main()
