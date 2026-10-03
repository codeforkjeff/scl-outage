"""Tests for coordinate-to-neighborhood lookup."""

import unittest

from scl_outage.neighborhoods.base import NeighborhoodIndex


from scl_outage.neighborhoods.seattle import (
    get_seattle_neighborhoods,
)


class TestNeighborhoods(unittest.TestCase):
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
        neighborhood_index = NeighborhoodIndex(get_seattle_neighborhoods())

        for lat, lng, expected_s_hood, expected_l_hood in test_cases:
            with self.subTest(lat=lat, lng=lng, s_hood=expected_s_hood):
                match = neighborhood_index.find_neighborhood(lat, lng)
                expected = (
                    f"{expected_s_hood} ({expected_l_hood})"
                    if expected_s_hood != expected_l_hood
                    else expected_s_hood
                )
                self.assertEqual(match.neighborhood.name, expected)
                self.assertEqual(match.match_type, "exact")

    def test_outside_seattle_returns_none(self):
        outside_coords = [
            (47.49046, -122.24295),  # South of Seattle (Tukwila/Renton area)
            (47.61010, -122.20150),  # Bellevue (East of Lake Washington)
            (45.51520, -122.67840),  # Portland, OR
            (0.0, 0.0),  # Gulf of Guinea
        ]
        neighborhood_index = NeighborhoodIndex(get_seattle_neighborhoods())
        for lat, lng in outside_coords:
            with self.subTest(lat=lat, lng=lng):
                self.assertIsNone(neighborhood_index.find_neighborhood(lat, lng))
                self.assertIsNone(neighborhood_index.find_neighborhood(lat, lng))

    def test_none_input_returns_none(self):
        neighborhood_index = NeighborhoodIndex(get_seattle_neighborhoods())
        self.assertIsNone(neighborhood_index.find_neighborhood(None, None))  # type: ignore
        self.assertIsNone(neighborhood_index.find_neighborhood(None, None))  # type: ignore


if __name__ == "__main__":
    unittest.main()
