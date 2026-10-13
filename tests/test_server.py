"""Offline tests for the website's server (recon/server.py)."""

import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from recon import places, server

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
