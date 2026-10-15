import importlib.util
import unittest

from recon import ask, sectors
from tests.test_sectors import SectorTests

PLACES = {"leeds": (53.79, -1.54, "Leeds, England"), "bn1": (50.82, -0.14, "BN1")}


def locate(place):
    if place.lower() not in PLACES:
        raise LookupError(place)
    return PLACES[place.lower()]


@unittest.skipUnless(importlib.util.find_spec("duckdb"), "needs DuckDB")
class AskTests(unittest.TestCase):
    def setUp(self):
        SectorTests.setUp(self)
        self.ask = ask.Ask(self.sectors, locate)

    def test_reads_a_kind_a_place_and_the_email_rule(self):
        query, place, miles, _ = self.ask.understand("plumbers in Leeds I can email within 10 miles")
        self.assertEqual(query["sector"], ["trades"])
        self.assertEqual(query["niche"], ["43220"])  # "Plumbing, heat and air-conditioning installation"
        self.assertEqual(query["rule"], ["can email"])
        self.assertEqual((place, miles), ("Leeds", 10))
        self.assertEqual(self.ask.understand("roofers near BN1 2BB")[1], "BN1 2BB")

    def test_counts_within_the_circle(self):
        found = self.ask.answer("plumbers in Leeds")
        self.assertEqual(found["figures"]["total"], 1)
        self.assertEqual(found["map"]["near"], ["Leeds"])
        self.assertEqual(self.ask.answer("roofers in Leeds")["figures"]["total"], 0)
        self.assertEqual(self.ask.answer("roofers near BN1")["figures"]["total"], 1)
        # A register word with no industry code still counts: Hove Hair is "hair salon".
        self.assertEqual(self.ask.answer("hair salons near BN1")["figures"]["total"], 1)

    def test_unknown_place_says_so(self):
        self.assertIn("couldn't find", self.ask.answer("plumbers in Atlantis")["answer"])

    def test_several_niches_mean_any_of_them(self):
        self.assertEqual(len(self.sectors.heat("uk", {"niche": ["43220", "43910"]})["districts"]), 2)
        self.assertIn(" OR ", sectors.clause({"niche": ["43220", "hair salon"]}))


if __name__ == "__main__":
    unittest.main()
