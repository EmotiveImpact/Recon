"""Offline tests for the master database: no internet needed."""

import csv
import gzip
import os
import tempfile
import types
import unittest
from unittest import mock

from recon import master, sources
from recon.sources import care_inspectorate_scotland, charity_commission

SOURCE = {"name": "test-register", "title": "Test", "country": "GB", "url": "https://example.org",
          "licence": "OGL", "updated": "daily", "fields": "name"}


def row(source_id, name, **values):
    return sources.record(SOURCE, source_id, name, **values)


class RecordTests(unittest.TestCase):
    def test_every_record_says_where_it_came_from(self):
        r = row(7, "  Glow   Room Ltd ", country="GB", postcode="sw1a1aa")
        self.assertEqual(r["record_id"], "test-register:7")
        self.assertEqual(r["name"], "Glow Room Ltd")
        self.assertEqual((r["source"], r["licence"], r["source_url"]),
                         ("test-register", "OGL", "https://example.org"))
        self.assertTrue(r["fetched"])
        self.assertEqual(r["postcode"], "SW1A 1AA")

    def test_unknown_columns_are_refused(self):
        with self.assertRaises(ValueError):
            row(1, "X", favourite_colour="blue")

    def test_emails_and_phones_are_tidied(self):
        r = row(1, "X", country="US", emails="Info@Example.com; mailto:info@example.com, bad@",
                phones="860-555-0101; 0000000")
        self.assertEqual(r["emails"], "info@example.com")
        self.assertEqual(r["phones"], "(860) 555-0101")

    def test_town_in_the_postcode_box_moves_to_the_address(self):
        r = row(1, "X", country="GB", address="1 High St", postcode="BRISTOL")
        self.assertEqual((r["address"], r["postcode"]), ("1 High St, BRISTOL", ""))

    def test_company_words(self):
        self.assertTrue(sources.corporate_name("Acme Widgets Inc."))
        self.assertTrue(sources.corporate_name("Glow Room Ltd"))
        self.assertTrue(sources.corporate_name("Leith Community Care SCIO"))
        self.assertFalse(sources.corporate_name("Jo's Hair"))

    def test_rules(self):
        self.assertEqual(sources.rule("GB", True, "")[0], "can email")
        self.assertEqual(sources.rule("GB", False, "")[0], "post only")
        self.assertEqual(sources.rule("US", None, "")[0], "can email")
        self.assertEqual(sources.rule("US", False, "")[0], "post only")
        self.assertEqual(sources.rule("FR", True, "")[0], "check local rules")


class SourceRuleTests(unittest.TestCase):
    def test_charities(self):
        base = {"charity_type": "Other", "charity_is_cio": "False",
                "charity_company_registration_number": ""}
        self.assertFalse(charity_commission.corporate(base))
        self.assertTrue(charity_commission.corporate({**base, "charity_type": "CIO"}))
        self.assertTrue(charity_commission.corporate({**base, "charity_company_registration_number": "0123"}))
        self.assertEqual(charity_commission.kind_of("University of Leeds Union of Students"),
                         "students' union")
        self.assertEqual(charity_commission.kind_of("Bath Students' Union"), "students' union")
        self.assertEqual(charity_commission.kind_of("UNION OF UEA STUDENTS LIMITED"), "students' union")
        self.assertEqual(charity_commission.kind_of("TRINITY SAINT DAVID STUDENTS’ UNION"),
                         "students' union")
        self.assertEqual(charity_commission.kind_of("Liverpool Medical Students' Society"),
                         "student organisation")
        self.assertEqual(charity_commission.kind_of("Bath Rotary Trust"), "charity")

    def test_care_services(self):
        base = {"CareService": "Care Home Service", "ServiceType": "Private", "ServiceProvider": "Jo Smith"}
        self.assertFalse(care_inspectorate_scotland.corporate(base))
        self.assertTrue(care_inspectorate_scotland.corporate({**base, "ServiceProvider": "Care Ltd"}))
        self.assertTrue(care_inspectorate_scotland.corporate({**base, "ServiceType": "Local Authority"}))
        self.assertFalse(care_inspectorate_scotland.corporate({**base, "CareService": "Child Minding",
                                                               "ServiceProvider": "Care Ltd"}))

    def test_cqc(self):
        from recon.sources import cqc
        self.assertTrue(cqc.corporate("Square Mile Dental Centre Limited"))
        self.assertTrue(cqc.corporate("Leeds Teaching Hospitals NHS Trust"))
        self.assertFalse(cqc.corporate("Dr A Patel and Partners"))
        self.assertFalse(cqc.corporate("St Mary's Trust"))
        self.assertEqual(cqc.kind_of("Nursing homes|Residential homes"), "care home")

    def test_recon_runs_use_the_newest_list(self):
        from recon import places
        from recon.sources import recon_runs
        with tempfile.TemporaryDirectory() as folder:
            places.write(os.path.join(folder, "plumbers-uk-2026-10-01.csv"),
                         [places.blank(key="a", name="Old Ltd")])
            places.write(os.path.join(folder, "plumbers-uk-2026-10-13.csv"), [places.blank(
                key="a", name="Pipe Ltd", sector="Plumbers", postcode="BS1 4DJ",
                all_emails="info@pipe.co.uk", all_phones="0117 496 0000", company_number="123456",
                company_match="exact", contact_rule="can email")])
            with mock.patch.dict(os.environ, {"RECON_RUNS": folder}):
                found = list(recon_runs.rows(None))
        self.assertEqual(len(found), 1)
        r = found[0]
        self.assertEqual((r["name"], r["emails"], r["company_number"], r["can_email"], r["fetched"]),
                         ("Pipe Ltd", "info@pipe.co.uk", "00123456", "can email", "2026-10-13"))
        self.assertEqual(r["record_id"], "recon-runs:plumbers-uk:a")

    def test_overture_places(self):
        from recon.sources import overture_places as o
        gb = o.SOURCES[0].SOURCE
        r = o.to_record(gb, "GB", "abc", "Pipe Ltd", "plumbing", ["https://pipe.co.uk",
                        "https://facebook.com/pipeltd"], ["+44 117 496 0000"], ["Info@pipe.co.uk"],
                        None, "1 Quay St", "Bristol", "ENG", "bs14dj")
        self.assertEqual((r["emails"], r["website"], r["postcode"], r["can_email"], r["kind"]),
                         ("info@pipe.co.uk", "https://pipe.co.uk", "BS1 4DJ", "can email", "plumbing"))
        self.assertIn("facebook.com/pipeltd", r["socials"])
        r = o.to_record(gb, "GB", "def", "Dave the Plumber", "plumbing", None, None,
                        ["dave@gmail.com"], None, "", "Leeds", "", "LS1 1AA")
        self.assertEqual(r["can_email"], "post only")
        self.assertIn("personal webmail", r["rule_reason"])
        us = o.SOURCES[1].SOURCE
        self.assertEqual(o.to_record(us, "US", "x", "Joe's Plumbing", "plumbing", None, None, None,
                                     None, "", "Austin", "TX", "78701")["can_email"], "can email")

    def test_every_loader_describes_its_source(self):
        for name, loader in sources.registry().items():
            for key in ("name", "title", "country", "url", "licence"):
                self.assertTrue(loader.SOURCE.get(key), f"{name} has no {key}")


class GroupingTests(unittest.TestCase):
    def test_same_organisation_is_joined_across_registers(self):
        rows = [
            row(1, "Glow Room Ltd", country="GB", postcode="SW1A 1AA"),
            row(2, "The Glow Room", country="GB", postcode="SW1A1AA", emails="info@glowroom.co.uk"),
            row(3, "Other Place", country="GB", emails="info@glowroom.co.uk"),
            row(4, "Unrelated", country="GB", postcode="SW1A 1AA"),
        ]
        groups = master.group(rows)
        self.assertEqual(groups["test-register:1"], groups["test-register:2"])
        self.assertEqual(groups["test-register:2"], groups["test-register:3"])
        self.assertNotEqual(groups["test-register:1"], groups["test-register:4"])

    def test_company_number_joins(self):
        rows = [row(1, "Glow Room CIC", country="GB", company_number="123456"),
                row(2, "GLOW ROOM COMMUNITY INTEREST COMPANY", country="GB", company_number="00123456")]
        groups = master.group(rows)
        self.assertEqual(groups["test-register:1"], groups["test-register:2"])

    def test_malformed_website_is_ignored(self):
        rows = [row(1, "A", country="US", website="http://[None]"), row(2, "B", country="US")]
        self.assertEqual(len(set(master.group(rows).values())), 2)

    def test_widely_shared_address_does_not_join(self):
        rows = [row(i, f"Firm {i}", country="US", emails="agent@filings.com") for i in range(10)]
        self.assertEqual(len(set(master.group(rows).values())), 10)

    def test_personal_email_joins_only_with_the_same_name(self):
        rows = [row(1, "Jo Hair", country="GB", emails="jo@gmail.com"),
                row(2, "Jo Hair Ltd", country="GB", emails="jo@gmail.com"),
                row(3, "Mia Nails", country="GB", emails="jo@gmail.com")]
        groups = master.group(rows)
        self.assertEqual(groups["test-register:1"], groups["test-register:2"])
        self.assertNotEqual(groups["test-register:1"], groups["test-register:3"])


@unittest.skipUnless(__import__("importlib").util.find_spec("duckdb"), "needs DuckDB")
class BuildTests(unittest.TestCase):
    def test_build_combine_and_summary(self):
        a = dict(SOURCE, name="register-a")
        b = dict(SOURCE, name="register-b", licence="Public Domain")
        loaders = {
            "register-a": types.SimpleNamespace(SOURCE=a, rows=lambda cache: iter([
                sources.record(a, 1, "Glow Room Ltd", country="GB", postcode="SW1A 1AA",
                               can_email="can email"),
                sources.record(a, 2, "Jo Nails", country="GB", postcode="E1 6AN", emails="jo@gmail.com",
                               can_email="post only")])),
            "register-b": types.SimpleNamespace(SOURCE=b, rows=lambda cache: iter([
                sources.record(b, 9, "The Glow Room", country="GB", postcode="SW1A1AA",
                               emails="info@glowroom.co.uk", phones="020 7946 0000",
                               can_email="post only")])),
        }
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.object(master, "registry", return_value=loaders), \
                mock.patch.object(master, "catalogue", return_value=[a, b]):
            for name in loaders:
                master.load_source(name, out, os.path.join(out, "cache"))
            with gzip.open(os.path.join(out, "sources", "register-a.csv.gz"), "rt") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 2)
            master.combine(out, list(loaders))
            per_source, total = master.summary(out)
            self.assertEqual(total[0], 2)  # Glow Room joined across both registers.
            self.assertEqual(total[2], 1)  # Its email may be sent: one register says company.
            self.assertEqual(total[5], 1)
            catalogue = master.write_catalogue(out, per_source)
            with open(catalogue) as handle:
                listed = {r["name"]: r for r in csv.DictReader(handle)}
            self.assertEqual(listed["register-b"]["licence"], "Public Domain")
            self.assertEqual(listed["register-a"]["records"], "2")
            master.segment(out)
            self.assertTrue(os.path.exists(os.path.join(out, "uk", "england.parquet")))
            with open(os.path.join(out, "uk", "counts.csv")) as handle:
                self.assertEqual(next(csv.DictReader(handle))["organisations"], "2")
            target = os.path.join(out, "glow.csv")
            self.assertEqual(master.export(out, "emails <> ''", target), 2)


if __name__ == "__main__":
    unittest.main()
