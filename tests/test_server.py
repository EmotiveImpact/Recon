"""Offline tests for the website's server (recon/server.py)."""

import csv
import importlib.util
import json
import os
import re
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from recon import dashboard, directory, places, server

HERE = os.path.dirname(__file__)


def sample_rows():
    return [
        places.blank(key="a", name="Glow Room", sector="Beauty and wellness", town="Bath",
                     contact_rule="can email", email="hello@glowroom.co.uk",
                     email_type="shared inbox", email_confidence="90", phone="01225 111111",
                     company_number="123", company_type="ltd"),
        places.blank(key="b", name="Jo's Nails", sector="Beauty and wellness", town="Bath",
                     contact_rule="post only", all_emails="jo@gmail.com (personal)",
                     mobile="07700 900000", mobile_only="yes"),
        places.blank(key="c", name="Fade Barbers", sector="Barbers and tattoo", town="Bristol",
                     contact_rule="post only", socials="https://instagram.com/fade"),
    ]


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "targets"))
        shutil.copy(os.path.join(HERE, "..", "targets", "saleane-uk.json"),
                    os.path.join(self.root, "targets", "saleane-uk.json"))
        self.workspace = server.Workspace(self.root)

    def tearDown(self):
        shutil.rmtree(self.root)

    def write_results(self, rows, name="saleane-uk-2026-10-13.csv"):
        places.write(os.path.join(self.root, "out", name), rows)

    def test_target_lists_join_their_project(self):
        self.workspace.save_project({"name": "SALEANE", "description": "Salon software"})
        projects = self.workspace.projects()
        self.assertEqual([p["name"] for p in projects], ["SALEANE"])
        self.assertEqual(projects[0]["targets"][0]["slug"], "saleane-uk")
        self.assertIsNone(projects[0]["targets"][0]["results"])

    def test_renaming_a_project_moves_its_lists(self):
        slug = self.workspace.save_project({"name": "SALEANE"})
        self.workspace.save_project({"name": "Saleane Studio"}, slug)
        self.assertEqual(self.workspace.target("saleane-uk")["project"], "Saleane Studio")

    def test_new_target_list_is_cleaned_and_readable(self):
        slug = self.workspace.save_target({
            "name": "SALEANE: UK dentists", "project": "SALEANE", "country": "gb",
            "sectors": {"Dentists": {"overture": ["dental_clinic", " ", "dental_clinic"],
                                     "osm": ["amenity=dentist", ["healthcare", "dentist"]],
                                     "sic": ["86230"]}}})
        self.assertEqual(slug, "saleane-uk-dentists")
        saved = self.workspace.target(slug)
        self.assertEqual(saved["country"], "GB")
        self.assertEqual(saved["sectors"]["Dentists"]["overture"], ["dental_clinic"])
        self.assertEqual(saved["sectors"]["Dentists"]["osm"],
                         [["amenity", "dentist"], ["healthcare", "dentist"]])

    def test_keys_the_site_doesnt_know_are_kept(self):
        slug = self.workspace.save_target({
            "name": "Kept", "country": "GB", "registers": ["fsa"],
            "sectors": {"A": {"overture": ["spa"], "trade_words": {"spa": ["spa"]}}}})
        saved = self.workspace.target(slug)
        self.assertEqual(saved["registers"], ["fsa"])
        self.assertEqual(saved["sectors"]["A"]["trade_words"], {"spa": ["spa"]})

    def test_bad_target_lists_are_refused(self):
        with self.assertRaises(ValueError):
            self.workspace.save_target({"name": "No sectors", "country": "GB", "sectors": {}})
        with self.assertRaises(ValueError):
            self.workspace.save_target({"name": "Mars", "country": "MA",
                                        "sectors": {"A": {"overture": ["x"]}}})
        with self.assertRaises(ValueError):  # Same name as an existing list.
            self.workspace.save_target({"name": "saleane uk", "country": "GB",
                                        "sectors": {"A": {"overture": ["x"]}}})

    def test_names_cannot_reach_outside_the_folder(self):
        for slug in ("../secrets", "a/b", "", "UPPER"):
            with self.assertRaises(ValueError):
                self.workspace.target(slug)

    def test_results_filter_and_summarise(self):
        self.write_results(sample_rows())
        found = self.workspace.search("saleane-uk", {"rule": ["post only"], "has": ["email"]})
        self.assertEqual([r["name"] for r in found["rows"]], ["Jo's Nails"])
        summary = found["summary"]
        self.assertEqual((summary["total"], summary["can_email"], summary["with_email"],
                          summary["ready"], summary["mobile_only"]), (3, 1, 2, 1, 1))
        self.assertEqual(self.workspace.search("saleane-uk", {"q": ["bristol"]})["total"], 1)
        ordered = self.workspace.search("saleane-uk", {"sort": ["-name"]})["rows"]
        self.assertEqual(ordered[0]["name"], "Jo's Nails")

    def test_newest_spreadsheet_wins_over_work_in_progress(self):
        places.write(os.path.join(self.root, "data", "saleane-uk", "places.csv"), sample_rows()[:1])
        self.assertEqual(self.workspace.summary("saleane-uk")["total"], 1)
        self.write_results(sample_rows())
        self.assertEqual(self.workspace.summary("saleane-uk")["total"], 3)

    def test_export_keeps_the_files_own_columns(self):
        path = os.path.join(self.root, "out", "saleane-uk-2026-10-13.csv")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("key,name,sector,contact_rule,new_column\nz,Studio,Beauty,can email,kept\n")
        exported = self.workspace.export("saleane-uk", {})
        self.assertTrue(exported.startswith("﻿key,name,sector,contact_rule,new_column,"))
        self.assertIn("kept", exported)

    def test_runs_check_what_they_are_given(self):
        with self.assertRaises(ValueError):
            self.workspace.runs.start("saleane-uk", "send")
        with self.assertRaises(LookupError):
            self.workspace.runs.start("nothing-here")
        with self.assertRaises(ValueError):
            self.workspace.runs.start("saleane-uk", "companies",
                                      {"companies_house": ["../../etc/passwd"]})


class WebsiteTests(unittest.TestCase):
    def test_ready_made_business_types_use_real_overture_categories(self):
        # A renamed category silently finds nothing, so every one the site offers
        # must be in the saved list of Overture's current names.
        web = os.path.join(HERE, "..", "web", "src")
        with open(os.path.join(web, "categories.json"), encoding="utf-8") as handle:
            counts = json.load(handle)["counts"]
        known = set(counts["GB"]) | set(counts["US"])
        with open(os.path.join(web, "library.ts"), encoding="utf-8") as handle:
            library = handle.read()
        offered = re.findall(r'preset\([^\[]*\[([^\]]*)\]', library)
        self.assertGreater(len(offered), 25)
        for names in offered:
            for name in re.findall(r'"([^"]+)"', names):
                self.assertIn(name, known)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "targets"))
        shutil.copy(os.path.join(HERE, "..", "targets", "saleane-uk.json"),
                    os.path.join(self.root, "targets", "saleane-uk.json"))
        workspace = server.Workspace(self.root)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.handler_for(workspace, None))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.root)

    def call(self, method, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers=headers or {})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_reading_needs_nothing_special(self):
        status, projects = self.call("GET", "/api/projects")
        self.assertEqual(status, 200)
        self.assertEqual(projects[0]["name"], "SALEANE")

    def test_changes_need_the_sites_header(self):
        body = {"name": "New thing"}
        self.assertEqual(self.call("POST", "/api/projects", body)[0], 403)
        status, made = self.call("POST", "/api/projects", body, {"X-Recon": "1"})
        self.assertEqual((status, made["slug"]), (201, "new-thing"))

    def test_errors_come_back_in_plain_words(self):
        status, body = self.call("GET", "/api/targets/missing")
        self.assertEqual(status, 404)
        self.assertIn("missing", body["error"])


if __name__ == "__main__":
    unittest.main()


class DirectoryTests(unittest.TestCase):
    def test_trade_words_are_cut_to_their_stem(self):
        self.assertEqual(directory.terms("Plumbers, heating engineer"),
                         [["plumb"], ["heat", "engine"]])
        self.assertEqual(directory.stem("salons"), "salon")
        self.assertEqual(directory.stem("gym"), "gym")

    @unittest.skipUnless(importlib.util.find_spec("duckdb"), "needs DuckDB")
    def test_search_finds_whole_words_and_counts(self):
        import duckdb
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        os.makedirs(os.path.join(folder, "uk"))
        rows = [("PIPE PLUMBING LTD", "company", "43220 - Plumbing", "can email", "a@pipe.co.uk"),
                ("PLUMBLAND VILLAGE HALL", "charity", "Village hall", "post only", ""),
                ("JO PLUMBER", "company", "", "post only", "")]
        values = ", ".join(f"('{n}', '{k}', '{c}', '{r}', '{e}')" for n, k, c, r, e in rows)
        columns = ", ".join(f"NULL::VARCHAR AS {c}" for c in directory.COLUMNS
                            if c not in ("name", "kind", "category", "can_email", "emails"))
        duckdb.sql(f"""COPY (SELECT *, {columns} FROM (VALUES {values})
                             AS t(name, kind, category, can_email, emails))
                       TO '{folder}/uk/england.parquet' (FORMAT parquet)""")
        found = directory.Directory(folder).search({"q": ["plumbers"], "group": ["uk"]})
        self.assertEqual(sorted(r["name"] for r in found["rows"]), ["JO PLUMBER", "PIPE PLUMBING LTD"])
        self.assertEqual((found["total"], found["with_email"], found["may_email"]), (2, 1, 1))
        self.assertEqual(found["by_area"], [{"area": "england", "count": 2}])
        with self.assertRaises(ValueError):
            directory.Directory(folder).files("uk", "../secrets")


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.folder, "uk"))
        os.makedirs(os.path.join(self.folder, "trades"))
        with open(os.path.join(self.folder, "uk", "counts.csv"), "w", encoding="utf-8") as handle:
            handle.write("area,organisations,with_email,may_email,with_phone,with_website\n"
                         "england,100,40,10,60,50\nwales,20,5,1,9,8\n")
        with open(os.path.join(self.folder, "trades", "summary.csv"), "w", encoding="utf-8") as handle:
            handle.write("trade,businesses,with email,may email\nbuilders,3,2,1\ntotal,3,2,1\n")
        rows = [
            # name, postcode, town, lat, lon, email, rule, turnover band
            ("Brighton Build", "BN1 1AA", "Brighton", "50.8225", "-0.1372", "a@b.co.uk", "can email", "yes", "small"),
            ("Hove Homes", "BN3 2AB", "Hove", "50.8279", "-0.1680", "", "post only", "", "micro"),
            ("Worthing Works", "BN11 1AA", "Worthing", "50.8179", "-0.3729", "c@d.co.uk", "post only", "", ""),
        ]
        with open(os.path.join(self.folder, "trades", "builders.csv"), "w", newline="",
                  encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["name", "postcode", "town", "lat", "lon", "email", "contact_rule",
                             "publishes_turnover", "size_band"])
            writer.writerows(rows)
        self.dash = dashboard.Dashboard(self.folder)

    def test_overview_adds_up_the_counts(self):
        view = self.dash.overview()
        self.assertEqual(view["countries"]["uk"]["totals"]["organisations"], 120)
        self.assertEqual([t["trade"] for t in view["trades"]], ["builders"])

    @unittest.skipUnless(importlib.util.find_spec("duckdb"), "needs DuckDB")
    def test_postcode_district_does_not_catch_its_longer_neighbours(self):
        found = self.dash.places({"near": ["BN1"], "km": ["2"]})
        self.assertEqual(found["centre"]["matched"], "BN1")
        self.assertEqual(found["total"], 1)  # Hove is 2.2 km away; Worthing much further
        self.assertEqual(self.dash.places({"near": ["BN1"], "km": ["5"]})["total"], 2)

    @unittest.skipUnless(importlib.util.find_spec("duckdb"), "needs DuckDB")
    def test_towns_filters_and_money(self):
        found = self.dash.places({"near": ["Worthing"], "km": ["50"], "has": ["email"]})
        self.assertEqual(found["total"], 2)
        self.assertEqual(found["points"][0]["name"], "Worthing Works")
        money = self.dash.overview()["money"]
        self.assertEqual((money["total"], money["publishes_turnover"]), (3, 1))
        only = self.dash.places({"has": ["money"]})
        self.assertEqual([p["name"] for p in only["points"]], ["Brighton Build"])

    @unittest.skipUnless(importlib.util.find_spec("duckdb"), "needs DuckDB")
    def test_unknown_places_and_trades_are_refused(self):
        with self.assertRaises(LookupError):
            self.dash.places({"near": ["Nowhere-on-sea"]})
        with self.assertRaises(ValueError):
            self.dash.places({"trade": ["../etc"]})
