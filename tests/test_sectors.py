import importlib.util
import os
import tempfile
import unittest

from recon import directory, sectors

ROWS = [
    # name, kind, category, postcode, can_email, emails
    ("Leeds Plumbing Ltd", "company", "43220 - Plumbing, heat and air-conditioning installation",
     "LS1 1AA", "can email", "a@b.co.uk"),
    ("Brighton Roofing", "company; roofers", "43910 - Roofing activities", "BN1 1AA", "post only", ""),
    ("Hove Hair", "hair salon", "", "BN3 2AB", "post only", ""),
    ("Seo Folk Ltd", "company", "73110 - Advertising agencies", "BN1 2BB", "can email", "x@y.co.uk"),
    ("Youth Shedz", "charity; company", "85590 - Other education n.e.c.", "LS2 9AA", "post only", ""),
]


@unittest.skipUnless(importlib.util.find_spec("duckdb"), "needs DuckDB")
class SectorTests(unittest.TestCase):
    def setUp(self):
        import duckdb
        self.root = tempfile.mkdtemp()
        self.master = os.path.join(self.root, "master")
        self.geo = os.path.join(self.root, "geo")
        self.cache = os.path.join(self.root, "sectors")
        os.makedirs(os.path.join(self.master, "uk"))
        os.makedirs(self.geo)
        db = duckdb.connect()
        values = ", ".join(
            "(" + ", ".join("'" + v.replace("'", "''") + "'" for v in row) + ")" for row in ROWS)
        blank = ", ".join(f"'' AS {c}" for c in directory.COLUMNS
                          if c not in ("name", "kind", "category", "postcode", "can_email", "emails"))
        db.execute(f"""COPY (SELECT name, kind, category, postcode, can_email, emails, {blank}
                             FROM (VALUES {values}) t(name, kind, category, postcode, can_email, emails))
                       TO '{os.path.join(self.master, "uk", "england.parquet")}' (FORMAT parquet)""")
        db.execute(f"""COPY (SELECT * FROM (VALUES ('LS11AA', 53.79, -1.54), ('LS29AA', 53.80, -1.55),
                                                   ('BN11AA', 50.82, -0.14), ('BN12BB', 50.83, -0.14),
                                                   ('BN32AB', 50.83, -0.17)) t(code, lat, lon))
                       TO '{os.path.join(self.geo, "uk-postcodes.parquet")}' (FORMAT parquet)""")
        sectors.build(self.master, self.cache, ("uk",), self.geo)
        self.sectors = sectors.Sectors(self.cache)

    def test_tree_counts_sectors_industries_and_niches(self):
        tree = self.sectors.tree("uk")
        by = {s["sector"]: s for s in tree["sectors"]}
        self.assertEqual(tree["total"], 5)
        self.assertEqual(by["trades"]["count"], 2)
        self.assertEqual(by["trades"]["may_email"], 1)
        self.assertEqual(by["trades"]["industries"][0]["name"], "Specialist trades")
        niches = {n["niche"]: n["name"] for n in by["trades"]["industries"][0]["niches"]}
        self.assertEqual(niches["43910"], "Roofing activities")
        self.assertEqual(by["marketing"]["count"], 1)
        beauty = by["beauty"]["industries"]
        self.assertEqual(beauty[0]["industry"], "other")  # Known only as "hair salon".
        self.assertEqual(beauty[0]["niches"][0]["niche"], "hair salon")
        self.assertEqual(by["community"]["count"], 1)  # The charity, by its word.

    def test_heat_map_places_each_district(self):
        heat = self.sectors.heat("uk", {"sector": ["trades"]})
        self.assertEqual({d["district"] for d in heat["districts"]}, {"LS1", "BN1"})
        by = {d["district"]: d for d in heat["districts"]}
        self.assertEqual((by["LS1"]["with_email"], by["BN1"]["with_email"]), (1, 0))
        heat = self.sectors.heat("uk", {"niche": ["43220"]})
        self.assertEqual([d["district"] for d in heat["districts"]], ["LS1"])
        heat = self.sectors.heat("uk", {"sector": ["trades"], "rule": ["can email"]})
        self.assertEqual([d["district"] for d in heat["districts"]], ["LS1"])

    def test_search_narrows_to_a_sector_and_niche(self):
        found = directory.Directory(self.master, geo=self.geo)
        names = lambda q: sorted(r["name"] for r in found.search({"group": ["uk"], **q})["rows"])
        self.assertEqual(names({"sector": ["trades"]}), ["Brighton Roofing", "Leeds Plumbing Ltd"])
        self.assertEqual(names({"sector": ["beauty"]}), ["Hove Hair"])
        self.assertEqual(names({"sector": ["trades"], "industry": ["43"], "niche": ["43910"]}),
                         ["Brighton Roofing"])
        self.assertEqual(names({"niche": ["hair salon"]}), ["Hove Hair"])

    def test_refuses_unknown_values(self):
        for query in ({"sector": ["nope"]}, {"industry": ["4x"]}, {"niche": ["'; drop"]}):
            with self.assertRaises(ValueError):
                sectors.clause(query)


if __name__ == "__main__":
    unittest.main()
