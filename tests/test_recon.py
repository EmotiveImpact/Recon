"""Offline tests: no internet needed. Run with `python -m unittest`."""

import csv
import http.server
import io
import os
import tempfile
import threading
import unittest
import zipfile

from recon import companies_house, emails, merge, osm, places, rules, text
from recon.target import Target

HERE = os.path.dirname(__file__)
TARGET = Target.load(os.path.join(HERE, "..", "targets", "saleane-uk.json"))


class TextTests(unittest.TestCase):
    def test_uk_postcode_is_tidied(self):
        self.assertEqual(text.postcode("12 High St, sw1a1aa"), "SW1A 1AA")
        self.assertEqual(text.postcode("no postcode here"), "")

    def test_us_zip(self):
        self.assertEqual(text.postcode("Austin TX 78701-1234", "US"), "78701")

    def test_name_key_ignores_company_words(self):
        self.assertEqual(text.name_key("The Glow Room Ltd"), text.name_key("Glow Room"))
        self.assertEqual(text.name_key("Cut & Colour Limited"), text.name_key("Cut and Colour"))

    def test_booking_platforms_are_not_own_websites(self):
        self.assertFalse(text.own_website("https://www.fresha.com/a/glow-room"))
        self.assertFalse(text.own_website("instagram.com/glowroom"))
        self.assertTrue(text.own_website("https://www.glowroom.co.uk"))


class TargetTests(unittest.TestCase):
    def test_overture_primary_category_wins(self):
        self.assertEqual(TARGET.overture_sector("barber", ["hair_salon"]), "Barbers and tattoo")
        self.assertEqual(TARGET.overture_sector("cafe", ["nail_salon"]), "Beauty and wellness")
        self.assertIsNone(TARGET.overture_sector("cafe", ["bakery"]))

    def test_osm_barber_lands_with_barbers(self):
        self.assertEqual(TARGET.osm_sector({"shop": "hairdresser"}), "Beauty and wellness")
        self.assertEqual(TARGET.osm_sector({"shop": "hairdresser", "hairdresser": "barber"}),
                         "Barbers and tattoo")

    def test_sic_codes(self):
        self.assertEqual(TARGET.sic_codes()["86900"], "Body and health")


class OsmTests(unittest.TestCase):
    def test_element_becomes_place(self):
        place = osm.to_place(TARGET, {
            "type": "node", "id": 7, "lat": 51.5, "lon": -0.1,
            "tags": {"shop": "beauty", "name": "Glow Room", "addr:postcode": "sw1a1aa",
                     "website": "https://glowroom.co.uk", "email": "hi@glowroom.co.uk"},
        })
        self.assertEqual(place["sector"], "Beauty and wellness")
        self.assertEqual(place["postcode"], "SW1A 1AA")
        self.assertEqual(place["email_found_on"], "openstreetmap")

    def test_unnamed_place_is_skipped(self):
        self.assertIsNone(osm.to_place(TARGET, {"type": "node", "id": 1, "tags": {"shop": "beauty"}}))


class MergeTests(unittest.TestCase):
    def test_same_business_from_two_sources_appears_once(self):
        a = places.blank(name="Glow Room", postcode="SW1A 1AA", source="overture", source_id="o1")
        b = places.blank(name="The Glow Room", postcode="SW1A 1AA", source="osm",
                         source_id="n1", email="hi@glowroom.co.uk")
        combined = merge.combine([b], [a])
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined[0]["source"], "overture+osm")
        self.assertEqual(combined[0]["email"], "hi@glowroom.co.uk")


def _companies_zip(folder):
    path = os.path.join(folder, "BasicCompanyData.zip")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["CompanyName", " CompanyNumber", "RegAddress.PostTown",
                     "RegAddress.PostCode", "CompanyCategory", "CompanyStatus",
                     "SICCode.SicText_1", "SICCode.SicText_2"])
    writer.writerow(["GLOW ROOM LTD", "01234567", "LONDON", "SW1A 2BB",
                     "Private Limited Company", "Active",
                     "96020 - Hairdressing and other beauty treatment", ""])
    writer.writerow(["BAKERY LTD", "07654321", "LONDON", "SW1A 2BB",
                     "Private Limited Company", "Active", "10710 - Bread", ""])
    writer.writerow(["SHUT SALON LTD", "09999999", "LEEDS", "LS1 1AA",
                     "Private Limited Company", "Dissolved",
                     "96020 - Hairdressing and other beauty treatment", ""])
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("BasicCompanyData.csv", buffer.getvalue())
    return path


class CompaniesHouseTests(unittest.TestCase):
    def test_only_active_companies_in_our_trades_are_loaded(self):
        with tempfile.TemporaryDirectory() as folder:
            index, total = companies_house.load([_companies_zip(folder)], TARGET.sic_codes())
        self.assertEqual(total, 1)
        self.assertIn("glow room", index)

    def test_match_by_postcode_district(self):
        with tempfile.TemporaryDirectory() as folder:
            index, _ = companies_house.load([_companies_zip(folder)], TARGET.sic_codes())
        place = places.blank(name="The Glow Room", postcode="SW1A 1AA")
        self.assertEqual(companies_house.mark([place], index), 1)
        self.assertEqual(place["company_number"], "01234567")

    def test_one_word_names_need_a_location_match(self):
        index = {"glow": [{"number": "1", "name": "GLOW LTD", "category": "Private Limited Company",
                           "postcode": "M1 1AA", "town": "manchester", "sector": "x"}]}
        place = places.blank(name="Glow", postcode="SW1A 1AA", town="London")
        self.assertEqual(companies_house.mark([place], index), 0)


class RuleTests(unittest.TestCase):
    def test_uk_companies_can_be_emailed_sole_traders_cannot(self):
        company = places.blank(company_type="Private Limited Company")
        llp = places.blank(company_type="Limited Liability Partnership")
        partnership = places.blank(company_type="Limited Partnership")
        sole_trader = places.blank()
        self.assertEqual(rules.contact_rule(company, "GB"), rules.CAN_EMAIL)
        self.assertEqual(rules.contact_rule(llp, "GB"), rules.CAN_EMAIL)
        self.assertEqual(rules.contact_rule(partnership, "GB"), rules.POST_ONLY)
        self.assertEqual(rules.contact_rule(sole_trader, "GB"), rules.POST_ONLY)

    def test_us_and_unknown_countries(self):
        self.assertEqual(rules.contact_rule(places.blank(), "US"), rules.CAN_EMAIL)
        self.assertEqual(rules.contact_rule(places.blank(), "FR"), rules.CHECK)


class EmailParsingTests(unittest.TestCase):
    def test_junk_is_dropped(self):
        page = ('<img src="logo@2x.png"> info&#64;glowroom.co.uk '
                'abc123@sentry.wixpress.com you@example.com Hello@GlowRoom.co.uk')
        self.assertEqual(emails.clean_candidates(page),
                         ["info@glowroom.co.uk", "hello@glowroom.co.uk"])

    def test_own_domain_and_shared_inbox_preferred(self):
        found = ["jane.smith@gmail.com", "jane@glowroom.co.uk", "info@glowroom.co.uk"]
        self.assertEqual(emails.best_email(found, "glowroom.co.uk"), "info@glowroom.co.uk")

    def test_contact_links_stay_on_site(self):
        page = ('<a href="/contact-us">Contact</a><a href="https://fresha.com/contact">x</a>'
                '<a href="/prices">Prices</a><a href="/about">Our story</a>')
        self.assertEqual(emails.contact_links(page, "https://glowroom.co.uk/"),
                         ["https://glowroom.co.uk/contact-us", "https://glowroom.co.uk/about"])


class _Site(http.server.BaseHTTPRequestHandler):
    pages = {
        "/robots.txt": "User-agent: *\nDisallow: /private\n",
        "/": '<html><a href="/contact">Contact us</a><a href="/private">x</a></html>',
        "/contact": '<p>Write to <a href="mailto:bookings@glowroom.co.uk">us</a></p>',
    }

    def do_GET(self):
        body = self.pages.get(self.path)
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/plain" if self.path.endswith(".txt") else "text/html")
        self.end_headers()
        self.wfile.write((body or "").encode())

    def log_message(self, *args):
        pass


class CrawlTests(unittest.TestCase):
    """A real fetch against a tiny website on this machine."""

    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), _Site)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_finds_email_on_contact_page(self):
        email, found_on = emails.find_email(self.url)
        self.assertEqual(email, "bookings@glowroom.co.uk")
        self.assertTrue(found_on.endswith("/contact"), found_on)

    def test_fill_only_visits_places_we_may_email_and_caches(self):
        allowed = places.blank(name="A", website=self.url, contact_rule=rules.CAN_EMAIL)
        post_only = places.blank(name="B", website="https://b-studio.co.uk",
                                 contact_rule=rules.POST_ONLY)
        with tempfile.TemporaryDirectory() as folder:
            cache = os.path.join(folder, "cache.jsonl")
            visited = emails.fill([allowed, post_only], cache, workers=1)
            self.assertEqual(visited, 1)
            self.assertEqual(post_only["email_found_on"], "")
            again = places.blank(name="A2", website=self.url, contact_rule=rules.CAN_EMAIL)
            self.assertEqual(emails.fill([again], cache, workers=1), 0)
            self.assertEqual(again["email_found_on"], allowed["email_found_on"])


class PlacesFileTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "places.csv")
            places.write(path, [places.blank(name="Café Lumière", town="Bath")])
            self.assertEqual(places.read(path)[0]["name"], "Café Lumière")


if __name__ == "__main__":
    unittest.main()
