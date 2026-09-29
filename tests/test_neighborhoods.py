"""Tests for coordinate-to-neighborhood lookup."""

import unittest
from pathlib import Path

from scl_outage.neighborhoods import (
    NeighborhoodIndex,
    default_geojson_path,
    get_index,
    get_neighborhood,
    get_neighborhood_details,
)


class TestNeighborhoods(unittest.TestCase):
    def test_default_path_exists(self):
        path = default_geojson_path()
        self.assertTrue(path.exists(), f"Default GeoJSON path {path} does not exist")

    def test_known_neighborhood_locations(self):
        test_cases = [
            # (lat, lng, expected_s_hood, expected_l_hood)
            (47.63811, -122.37152, "West Queen Anne", "Queen Anne"),
            (47.62505, -122.31761, "Broadway", "Capitol Hill"),
            (47.66870, -122.38450, "Ballard", "Ballard"),
            (47.65340, -122.35000, "Fremont", "North Central"),
            (47.60150, -122.33230, "Pioneer Square", "Downtown"),
            (47.68150, -122.32550, "Green Lake", "North Central"),
        ]
        for lat, lng, expected_s_hood, expected_l_hood in test_cases:
            with self.subTest(lat=lat, lng=lng, s_hood=expected_s_hood):
                s_hood = get_neighborhood(lat, lng)
                self.assertEqual(s_hood, expected_s_hood)

                details = get_neighborhood_details(lat, lng)
                self.assertIsNotNone(details)
                self.assertEqual(details["s_hood"], expected_s_hood)
                self.assertEqual(details["l_hood"], expected_l_hood)
                self.assertIn("alt_names", details)
                self.assertIn("object_id", details)

    def test_outside_seattle_returns_none(self):
        outside_coords = [
            (47.49046, -122.24295),  # South of Seattle (Tukwila/Renton area)
            (47.61010, -122.20150),  # Bellevue (East of Lake Washington)
            (45.51520, -122.67840),  # Portland, OR
            (0.0, 0.0),              # Gulf of Guinea
        ]
        for lat, lng in outside_coords:
            with self.subTest(lat=lat, lng=lng):
                self.assertIsNone(get_neighborhood(lat, lng))
                self.assertIsNone(get_neighborhood_details(lat, lng))

    def test_none_input_returns_none(self):
        self.assertIsNone(get_neighborhood(None, None))  # type: ignore
        self.assertIsNone(get_neighborhood_details(None, None))  # type: ignore

    def test_custom_geojson_path(self):
        path = default_geojson_path()
        index = NeighborhoodIndex(path)
        res = index.find_neighborhood(47.63811, -122.37152)
        self.assertEqual(res, "West Queen Anne")

    def test_missing_geojson_file_raises_error(self):
        with self.assertRaises(FileNotFoundError):
            NeighborhoodIndex("nonexistent/file.geojson")

    def test_cache_reuse(self):
        index1 = get_index()
        index2 = get_index()
        self.assertIs(index1, index2)


if __name__ == "__main__":
    unittest.main()
