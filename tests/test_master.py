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

    def test_companies_house_psc(self):
        import json
        from recon.sources import companies_house_psc as psc

        def line(number, **data):
            return json.dumps({"company_number": number, "data": data})
        lines = [
            line("123456", kind="individual-person-with-significant-control", name="Mrs Jane Smith",
                 name_elements={"title": "Mrs", "forename": "Jane", "surname": "Smith"},
                 natures_of_control=["ownership-of-shares-75-to-100-percent"]),
            line("00999999", kind="corporate-entity-person-with-significant-control",
                 name="Acme Holdings Ltd", natures_of_control=["voting-rights-25-to-50-percent"]),
            line("00123456", kind="corporate-entity-person-with-significant-control",
                 name="Acme Holdings Ltd", natures_of_control=["significant-influence-or-control"]),
            line("00123456", kind="individual-person-with-significant-control", name="Mr Old Owner",
                 ceased_on="2020-01-01", natures_of_control=["ownership-of-shares-25-to-50-percent"]),
            line("00555555", kind="persons-with-significant-control-statement",
                 statement="no-individual-or-entity-with-signficant-control"),
            json.dumps({"data": {"kind": "totals#persons-of-significant-control-snapshot"}}),
        ]
        found = list(psc.companies(psc.sorted_pairs(psc.owners(lines), tempfile.gettempdir())))
        self.assertEqual([r["company_number"] for r in found], ["00123456", "00999999"])
        self.assertEqual(found[0]["people"], "Acme Holdings Ltd (corporate owner, significant influence); "
                                             "Jane Smith (owner, 75%+ shares)")
        self.assertEqual(found[1]["people"], "Acme Holdings Ltd (corporate owner, 25-50% votes)")
        self.assertEqual((found[0]["can_email"], found[0]["kind"]), ("can email", "company"))
        with tempfile.TemporaryDirectory() as folder:  # Sorting on disk gives the same answer.
            pairs = list(psc.sorted_pairs(psc.owners(lines), folder, chunk=1))
            self.assertEqual(os.listdir(folder), [])
        self.assertEqual(pairs, sorted(psc.owners(lines)))

    def test_companies_house_accounts(self):
        from recon.sources import companies_house_accounts as accounts
        document = """<html><body>
        <ix:nonNumeric name="bus:EntityCurrentLegalOrRegisteredName" contextRef="c1">Glow Room
          <span>Ltd</span></ix:nonNumeric>
        <ix:nonFraction name="core:AverageNumberEmployeesDuringPeriod" contextRef="c1" decimals="0"
          unitRef="pure">12</ix:nonFraction>
        <ix:nonFraction name="core:AverageNumberEmployeesDuringPeriod" contextRef="c0" decimals="0"
          unitRef="pure">9</ix:nonFraction>
        <ix:nonFraction name="core:TurnoverRevenue" contextRef="c1" scale="3" unitRef="GBP">1,234</ix:nonFraction>
        <ix:nonNumeric name="bus:NameEntityOfficer" contextRef="d1">JANE SMITH</ix:nonNumeric>
        <ix:nonNumeric name="bus:NameEntityOfficer" contextRef="d2">Bob Jones</ix:nonNumeric>
        <ix:nonNumeric name="core:DirectorSigningFinancialStatements" contextRef="d1"/>
        <xbrli:context id="c1"><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate>
          <xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
        <xbrli:context id="c0"><xbrli:period><xbrli:endDate>2024-12-31</xbrli:endDate></xbrli:period>
          </xbrli:context>
        <xbrli:context id="d1"><xbrli:entity><xbrli:segment>Director1</xbrli:segment></xbrli:entity>
          <xbrli:period><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
        </body></html>"""
        name, staff, turnover, director = accounts.summary(document)
        self.assertEqual((name, staff, turnover, director), ("Glow Room Ltd", 12, 1_234_000, "Jane Smith"))
        r = accounts.to_record("123456", name, staff, turnover, director, "20251231")
        self.assertEqual((r["company_number"], r["category"], r["people"], r["can_email"]),
                         ("00123456", "about 12 staff; turnover £1.2m",
                          "Jane Smith (director who signed the accounts)", "can email"))

    def test_sec_form_d(self):
        from datetime import date
        from recon.sources import sec_form_d
        issuer = {"CIK": "0001234", "ENTITYNAME": "Acme Robotics Inc", "STREET1": "2 Main St",
                  "CITY": "Austin", "STATEORCOUNTRY": "TX", "ZIPCODE": "78701",
                  "ISSUERPHONENUMBER": "5125550101", "ENTITYTYPE": "Corporation"}
        person = sec_form_d.person({"FIRSTNAME": "JANE", "LASTNAME": "SMITH",
                                    "RELATIONSHIP_1": "Executive Officer", "RELATIONSHIP_2": "Director"})
        r = sec_form_d.to_record(issuer, date(2026, 6, 20), {"INDUSTRYGROUPTYPE": "Other Technology",
                                                             "REVENUERANGE": "Decline to Disclose"}, [person])
        self.assertEqual((r["source_id"], r["people"], r["category"], r["phones"], r["can_email"]),
                         ("1234", "Jane Smith (Executive Officer, Director)",
                          "Other Technology; revenue Decline to Disclose", "(512) 555-0101", "can email"))
        self.assertIsNone(sec_form_d.to_record({**issuer, "STATEORCOUNTRY": "X0"}))
        self.assertEqual(sec_form_d.recent_quarters(date(2026, 1, 5), 3), ["2025q4", "2025q3", "2025q2"])

    def test_sba_ppp(self):
        from recon.sources import sba_ppp
        base = {"LoanNumber": "9547507704", "BorrowerName": "SUMTER COATINGS, INC.",
                "BorrowerAddress": "2410 Highway 15 South", "BorrowerCity": "SUMTER", "BorrowerState": "SC",
                "BorrowerZip": "29150-9662", "LoanStatus": "Paid in Full", "JobsReported": "12",
                "NAICSCode": "325510", "BusinessType": "Corporation", "NonProfit": ""}
        r = sba_ppp.to_record(base)
        self.assertEqual((r["kind"], r["category"], r["postcode"], r["can_email"]),
                         ("business", "12 jobs reported (PPP 2020-21); NAICS 325510; Corporation",
                          "29150", "can email"))
        sole = sba_ppp.to_record({**base, "BusinessType": "Sole Proprietorship"})
        self.assertEqual((sole["kind"], sole["can_email"], sole["rule_reason"]),
                         ("sole trader", "post only", "individual: post only"))
        self.assertEqual(sba_ppp.borrower_key(base),
                         sba_ppp.borrower_key({**base, "BorrowerZip": "29150", "BorrowerName": "Sumter  Coatings, Inc."}))
        self.assertTrue(sba_ppp.WITHHELD.match("Exemption 6"))

    def test_gender_pay_gap(self):
        from recon.sources import gender_pay_gap as gpg
        base = {"EmployerId": "7", "EmployerName": "Acme Widgets", "CurrentName": "Acme Widgets",
                "Address": "1 High Street, Leeds, United Kingdom, LS1 4DL", "PostCode": "LS1 4DL",
                "CompanyNumber": "", "SicCodes": "47730,\n82990", "EmployerSize": "250 to 499",
                "CompanyLinkToGPGInfo": "https://careers.acme.co.uk/gender-pay.pdf",
                "ResponsiblePerson": "Jane Smith (Chief People Officer)"}
        made = gpg.to_record(base, 2025)
        self.assertEqual(made["can_email"], "post only")
        self.assertEqual(made["website"], "https://acme.co.uk")
        self.assertEqual(made["people"], "Jane Smith (Chief People Officer)")
        self.assertEqual(made["category"], "SIC 47730; SIC 82990; 250 to 499 staff")
        self.assertEqual(made["town"], "Leeds")
        made = gpg.to_record({**base, "CompanyNumber": "1234567"}, 2025)
        self.assertEqual((made["can_email"], made["company_number"]), ("can email", "01234567"))
        council = gpg.to_record({**base, "CurrentName": "Leeds City Council", "SicCodes": "1"}, 2025)
        self.assertEqual((council["can_email"], council["kind"]), ("can email", "public body"))
        self.assertEqual(gpg.site_from_link("https://assets.publishing.service.gov.uk/x.pdf"), "")
        self.assertEqual(gpg.site_from_link("https://drive.google.com/file/d/1"), "")
        self.assertEqual(gpg.site_from_link("https://www.leeds.gov.uk/pay"), "https://leeds.gov.uk")

    def test_modern_slavery(self):
        from recon.sources import modern_slavery as msr
        base = {"StatementYear": "2025", "OrganisationName": "Acme Widgets", "SectorType": "Private",
                "Address": "1 High Street\nLeeds\nUnited Kingdom\nLS1 4DL", "CompanyNumber": "",
                "StatementURL": "https://cdn.prod.website-files.com/a/statement.pdf",
                "EmailAddressNoURL": "info@acme.co.uk", "ApprovingPerson": "Jo Bloggs (Director)",
                "OrganisationSectors": "Retail\nWholesale", "Turnover": "£36 million to £60 million",
                "StatementSummaryURL": "https://example.org/s/1", "ParentName": "", "LastUpdated": "01/06/2025"}
        made = msr.to_record(base)
        self.assertEqual((made["town"], made["postcode"], made["country"]), ("Leeds", "LS1 4DL", "GB"))
        self.assertEqual(made["website"], "")  # a document host, not their site
        self.assertEqual((made["emails"], made["can_email"]), ("info@acme.co.uk", "post only"))
        self.assertEqual(made["category"], "Retail; Wholesale; turnover £36 million to £60 million")
        made = msr.to_record({**base, "CompanyNumber": "SC123456",
                              "StatementURL": "https://www.acme.co.uk/msa"})
        self.assertEqual((made["website"], made["can_email"]), ("https://acme.co.uk", "can email"))
        self.assertEqual(msr.parse_address("")[3], "GB")

    def test_wikidata(self):
        from recon.sources import wikidata
        source = wikidata.SOURCES[0].SOURCE
        flat = [{"item": "http://www.wikidata.org/entity/Q1", "itemLabel": "Acme", "chn": "",
                 "website": "https://acme.co.uk/", "linkedin": "acme",
                 "employees": "300", "country": "http://www.wikidata.org/entity/Q145"},
                {"item": "http://www.wikidata.org/entity/Q1", "itemLabel": "Acme", "chn": "",
                 "website": "https://acme.co.uk/shop", "linkedin": "acme", "employees": "",
                 "country": "http://www.wikidata.org/entity/Q145"}]
        made = wikidata.to_record(source, "GB", wikidata.merge_flat(flat, "GB")[0])
        self.assertEqual(made["website"], "https://acme.co.uk/")
        self.assertEqual(made["socials"], "https://www.linkedin.com/company/acme")
        self.assertEqual(made["can_email"], "post only")
        detail = {"item": "http://www.wikidata.org/entity/Q2", "label": "Acme Ltd", "label_gb": "",
                  "websites": "https://acme.co.uk/", "company_numbers": "01234567", "linkedin": "",
                  "employees": "250@2021-01-01T00:00:00Z 300@2023-01-01T00:00:00Z 9@",
                  "emails": "mailto:hello@acme.co.uk", "phones": "+44 20 7946 0000|+1-425-882-8080",
                  "headquarters": "London", "dissolved": ""}
        made = wikidata.to_record(source, "GB", detail)
        self.assertEqual((made["company_number"], made["can_email"]), ("01234567", "can email"))
        self.assertEqual(made["category"], "300 employees (2023)")
        self.assertEqual((made["emails"], made["phones"]), ("hello@acme.co.uk", "+442079460000"))
        self.assertIsNone(wikidata.to_record(source, "GB", {**detail, "dissolved": "2020-01-01"}))

    def test_web_data_commons(self):
        from recon.sources import web_data_commons as w
        base = {"page": "https://www.yell.com/biz/pipe", "domain": "yell.com", "name": "Pipe Ltd",
                "types": "Plumber", "telephone": "0117 496 0000", "website": "https://www.yell.com/x",
                "socials": "", "street": "1 Quay St", "locality": "Bristol", "region": "",
                "postcode": "BS1 4DJ", "country": "GB", "site_kind": "directory"}
        r = w.to_record(1, base)
        self.assertEqual((r["website"], r["can_email"], r["emails"]), ("", "can email", ""))
        self.assertIn("listing site", r["rule_reason"])
        r = w.to_record(2, {**base, "site_kind": "own site", "domain": "pipe.co.uk", "website": "",
                            "page": "https://pipe.co.uk/"})
        self.assertEqual((r["website"], r["kind"]), ("https://pipe.co.uk", "business"))

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

    def test_enrichment_joins_but_never_stands_alone(self):
        a = dict(SOURCE, name="register-a")
        owners = dict(SOURCE, name="owners", enrich_only=True)
        loaders = {
            "register-a": types.SimpleNamespace(SOURCE=a, rows=lambda cache: iter([
                sources.record(a, 1, "Pipe Ltd", country="GB", company_number="123",
                               can_email="can email")])),
            "owners": types.SimpleNamespace(SOURCE=owners, rows=lambda cache: iter([
                sources.record(owners, 1, "", country="GB", company_number="00000123",
                               people="Jo Pipe (owner)"),
                sources.record(owners, 2, "", country="GB", company_number="999",
                               people="Gone Ltd (corporate owner)")])),
        }
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.object(master, "registry", return_value=loaders):
            for name in loaders:
                master.load_source(name, out, os.path.join(out, "cache"))
            db = master.combine(out, list(loaders))
            rows = db.execute(f"SELECT name, people FROM '{out}/organisations.parquet'").fetchall()
        self.assertEqual(rows, [("Pipe Ltd", "Jo Pipe (owner)")])


if __name__ == "__main__":
    unittest.main()
