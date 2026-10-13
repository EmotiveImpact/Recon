"""Offline tests: no internet needed. Run with `python -m unittest`."""

import csv
import http.server
import io
import os
import tempfile
import threading
import unittest
import zipfile

from recon import (companies_house, contacts, dns, emails, finder, hunter, mailbox, merge, osm,
                   overture, patterns, people, places, rules, text, verify)
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
        "/contact": ('<p>Write to <a href="mailto:bookings@glowroom.co.uk">us</a> or ring '
                     '<a href="tel:+447700900123">us</a>. '
                     '<a href="https://www.instagram.com/glowroom/?hl=en">Instagram</a> '
                     '<a href="https://www.facebook.com/sharer.php?u=x">Share</a></p>'),
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

    def test_phones_and_socials_are_collected_on_the_way(self):
        extras = {}
        emails.crawl(self.url, extras)
        self.assertEqual(extras["phones"], ["+447700900123"])
        self.assertEqual(extras["socials"], ["https://www.instagram.com/glowroom/?hl=en"])
        place = places.blank(name="A", website=self.url, contact_rule=rules.POST_ONLY)
        with tempfile.TemporaryDirectory() as folder:
            emails.fill([place], os.path.join(folder, "cache.jsonl"), workers=1)
        self.assertEqual(place["mobile"], "07700 900123")
        self.assertEqual(place["socials"], "https://www.instagram.com/glowroom")
        self.assertIn("bookings@glowroom.co.uk (shared inbox)", place["all_emails"])

    def test_fill_only_visits_places_we_may_email_and_caches(self):
        allowed = places.blank(name="A", website=self.url, contact_rule=rules.CAN_EMAIL)
        post_only = places.blank(name="B", website="https://b-studio.co.uk",
                                 contact_rule=rules.POST_ONLY)
        with tempfile.TemporaryDirectory() as folder:
            cache = os.path.join(folder, "cache.jsonl")
            visited = emails.fill([allowed, post_only], cache, everyone=False, workers=1)
            self.assertEqual(visited, 1)
            self.assertEqual(post_only["email_found_on"], "")
            again = places.blank(name="A2", website=self.url, contact_rule=rules.CAN_EMAIL)
            self.assertEqual(emails.fill([again], cache, everyone=False, workers=1), 0)
            self.assertEqual(again["email_found_on"], allowed["email_found_on"])


# A real reply from a public resolver to "outlook.com MX", and one saying a
# domain does not exist.
OUTLOOK_MX = bytes.fromhex(
    "000081800001000100000000076f75746c6f6f6b03636f6d00000f0001c00c000f0001000000d1001f"
    "00050b6f75746c6f6f6b2d636f6d036f6c630a70726f74656374696f6ec00c")
NO_SUCH_DOMAIN = bytes.fromhex(
    "000081830001000000010000196e6f6e6578697374656e742d7265636f6e2d746573742d7a7a02636f"
    "02756b00000f0001c0260006000100000708003804646e7331036e6963c0290a686f73746d6173746572"
    "076e6f6d696e6574036f7267c0296acdd336000003840000012c0024ea0000002a30")


class DnsTests(unittest.TestCase):
    def test_question_matches_what_resolvers_expect(self):
        self.assertEqual(OUTLOOK_MX[12:29], dns.query("outlook.com", dns.MX, ident=0)[12:])

    def test_mail_servers_are_read_from_a_real_reply(self):
        code, truncated, answers = dns.parse(OUTLOOK_MX)
        self.assertEqual((code, truncated), (0, False))
        self.assertEqual(answers, [(dns.MX, (5, "outlook-com.olc.protection.outlook.com"))])

    def test_missing_domain(self):
        self.assertEqual(dns.parse(NO_SUCH_DOMAIN)[0], 3)

    def test_no_mx_falls_back_to_the_domain_itself(self):
        replies = {dns.MX: (0, []), dns.A: (0, [(dns.A, "192.0.2.1")])}
        original = dns.lookup
        dns.lookup = lambda name, qtype, servers=None: replies[qtype]
        try:
            self.assertEqual(dns.mx_hosts("glowroom.co.uk"), (dns.YES, ["glowroom.co.uk"]))
            replies[dns.A] = (0, [])
            self.assertEqual(dns.mx_hosts("glowroom.co.uk"), (dns.NO, []))
            replies[dns.MX] = (None, [])
            self.assertEqual(dns.mx_hosts("glowroom.co.uk"), (dns.UNKNOWN, []))
        finally:
            dns.lookup = original


class PatternTests(unittest.TestCase):
    def test_names_in_both_orders(self):
        self.assertEqual(patterns.split_name("JONES, Sarah Jane"), ("sarah", "jones"))
        self.assertEqual(patterns.split_name("Dr Sarah O'Brién"), ("sarah", "obrien"))
        self.assertIsNone(patterns.split_name("Sarah"))

    def test_making_addresses(self):
        self.assertEqual(patterns.make("f.last", "sarah", "jones"), "s.jones")
        self.assertEqual(patterns.make("firstl", "sarah", "jones"), "sarahj")

    def test_pattern_learned_from_a_published_address(self):
        people_ = [("sarah", "jones"), ("tom", "brown")]
        found = ["info@glowroom.co.uk", "tbrown@glowroom.co.uk"]
        self.assertEqual(patterns.learn(found, people_), ("flast", "matched"))

    def test_shape_is_a_weaker_hint(self):
        self.assertEqual(patterns.learn(["amy.wu@x.co.uk"], []), ("first.last", "shape"))
        self.assertEqual(patterns.learn(["info@x.co.uk", "hello@x.co.uk"], []), ("", ""))

    def test_patterns_seen_elsewhere_are_tried_first(self):
        import collections
        order = patterns.usual_order(collections.Counter({"f.last": 3}))
        self.assertEqual(order[:2], ["f.last", "first"])

    def test_hunter_pattern(self):
        self.assertEqual(patterns.from_hunter("{first}.{last}"), "first.last")
        self.assertEqual(patterns.from_hunter("{f}{last}"), "flast")
        self.assertEqual(patterns.from_hunter("{nonsense}"), "")


class HiddenEmailTests(unittest.TestCase):
    def test_cloudflare_and_spelt_out_addresses(self):
        scrambled = "42" + bytes(b ^ 0x42 for b in b"info@glowroom.co.uk").hex()
        page = (f'<a href="/cdn-cgi/l/email-protection#{scrambled}">email</a>'
                ' or write to sarah [at] glowroom [dot] co [dot] uk')
        self.assertEqual(emails.clean_candidates(page),
                         ["info@glowroom.co.uk", "sarah@glowroom.co.uk"])


class PeopleTests(unittest.TestCase):
    REPLY = {"items": [
        {"name": "JONES, Sarah Jane", "officer_role": "director"},
        {"name": "SMITH, Old", "officer_role": "director", "resigned_on": "2020-01-01"},
        {"name": "ACME SECRETARIES LTD", "officer_role": "corporate-secretary"},
        {"name": "BROWN, Tom", "officer_role": "secretary"},
    ]}

    def test_only_active_directors_who_are_people(self):
        self.assertEqual(people.directors(self.REPLY), [{"name": "Sarah Jones", "role": "director"}])

    def test_only_companies_we_may_email_with_a_website(self):
        company = places.blank(company_number="01234567", website="https://glowroom.co.uk",
                               contact_rule=rules.CAN_EMAIL)
        sole_trader = places.blank(website="https://other.co.uk", contact_rule=rules.POST_ONLY)
        asked = []
        with tempfile.TemporaryDirectory() as folder:
            cache = os.path.join(folder, "people.jsonl")
            self.assertIsNone(people.fill([company], cache, key=""))
            fetch = lambda number, key: asked.append(number) or self.REPLY
            people.PAUSE, pause = 0, people.PAUSE
            try:
                self.assertEqual(people.fill([company, sole_trader], cache, "k", fetch), 1)
            finally:
                people.PAUSE = pause
            self.assertEqual(people.load(cache)["01234567"][0]["name"], "Sarah Jones")
        self.assertEqual(asked, ["01234567"])
        self.assertEqual(company["contact_name"], "Sarah Jones")
        self.assertEqual(sole_trader["contact_name"], "")


class HunterTests(unittest.TestCase):
    def test_off_without_a_key_and_asks_once_per_domain(self):
        reply = {"data": {"pattern": "{first}", "emails": [
            {"value": "Hello@glowroom.co.uk", "type": "generic", "confidence": 90}]}}
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            cache = os.path.join(folder, "hunter.jsonl")
            self.assertIsNone(hunter.Lookup(cache, api_key="")("glowroom.co.uk"))
            lookup = hunter.Lookup(cache, "k", lambda d, k: calls.append(d) or reply)
            self.assertEqual(lookup("glowroom.co.uk")["emails"][0]["email"], "hello@glowroom.co.uk")
            lookup("glowroom.co.uk")
            self.assertEqual(hunter.Lookup(cache, api_key="")("glowroom.co.uk")["pattern"],
                             "{first}")
        self.assertEqual(calls, ["glowroom.co.uk"])


class _FakeMailServer:
    """Stands in for smtplib.SMTP: knows which mailboxes exist."""

    def __init__(self, mailboxes, catch_all=False):
        self.mailboxes, self.catch_all, self.asked = mailboxes, catch_all, []

    def __call__(self, host, port, timeout):
        return self

    def ehlo(self, name):
        return 250, b"hi"

    def mail(self, sender):
        return 250, b"ok"

    def rcpt(self, address):
        self.asked.append(address)
        if self.catch_all or address in self.mailboxes:
            return 250, b"ok"
        return 550, b"5.1.1 user unknown"

    def quit(self):
        pass


class MailboxTests(unittest.TestCase):
    def test_says_which_mailboxes_exist(self):
        server = _FakeMailServer({"sarah@glowroom.co.uk"})
        checker = mailbox.Checker("me@saleane.com", "saleane.com", connect=server, pause=0)
        found = checker.check("glowroom.co.uk", ["mx.glowroom.co.uk"],
                              ["sarah@glowroom.co.uk", "sjones@glowroom.co.uk"])
        self.assertEqual(found["sarah@glowroom.co.uk"][0], mailbox.SAFE)
        self.assertEqual(found["sjones@glowroom.co.uk"][0], mailbox.INVALID)
        self.assertTrue(server.asked[0].startswith("recon-check-"))

    def test_catch_all_is_not_taken_as_proof(self):
        checker = mailbox.Checker("me@saleane.com", "saleane.com",
                                  connect=_FakeMailServer(set(), catch_all=True), pause=0)
        found = checker.check("glowroom.co.uk", ["mx"], ["anyone@glowroom.co.uk"])
        self.assertEqual(found["anyone@glowroom.co.uk"][0], mailbox.RISKY)

    def test_stops_when_the_mail_port_is_blocked(self):
        def blocked(host, port, timeout):
            raise TimeoutError

        checker = mailbox.Checker("me@saleane.com", "saleane.com", connect=blocked, pause=0)
        for _ in range(2):
            checker.check("glowroom.co.uk", ["mx1", "mx2"], ["a@glowroom.co.uk"])
        self.assertTrue(checker.blocked)

    def test_big_providers(self):
        self.assertEqual(mailbox.provider("glowroom-co-uk.mail.protection.outlook.com"),
                         "outlook.com")


def _company(**values):
    defaults = dict(company_number="01234567", website="https://glowroom.co.uk",
                    contact_rule=rules.CAN_EMAIL)
    defaults.update(values)
    return places.blank(**defaults)


class FinderTests(unittest.TestCase):
    PEOPLE = {"01234567": [{"name": "Tom Brown", "role": "director"}],
              "07654321": [{"name": "Amy Wu", "role": "director"}]}

    def test_named_person_from_the_pattern_the_site_uses(self):
        place = _company()
        found = {"glowroom.co.uk": {"info@glowroom.co.uk": "https://glowroom.co.uk/contact",
                                    "sarah.jones@glowroom.co.uk": "https://glowroom.co.uk/team"}}
        finder.fill([place], found, self.PEOPLE)
        self.assertEqual(place["email"], "info@glowroom.co.uk")
        self.assertEqual(place["email_basis"], "published")
        self.assertEqual(place["email_confidence"], 90)
        self.assertEqual(place["email_pattern"], "first.last")
        self.assertEqual(place["contact_name"], "Tom Brown")
        self.assertEqual(place["contact_email"], "tom.brown@glowroom.co.uk")
        self.assertEqual(place["contact_email_basis"], "pattern-shape")

    def test_published_personal_address_is_used_as_it_is(self):
        place = _company()
        found = {"glowroom.co.uk": {"tom@glowroom.co.uk": "https://glowroom.co.uk/"}}
        finder.fill([place], found, self.PEOPLE)
        self.assertEqual(place["contact_email"], "tom@glowroom.co.uk")
        self.assertEqual(place["contact_email_basis"], "published")

    def test_post_only_rows_never_get_a_person(self):
        place = _company(contact_rule=rules.POST_ONLY, contact_name="Tom Brown")
        found = {"glowroom.co.uk": {"info@glowroom.co.uk": "https://glowroom.co.uk/"}}
        finder.fill([place], found, self.PEOPLE, everyone=True)
        self.assertEqual(place["email"], "info@glowroom.co.uk")
        self.assertEqual((place["contact_name"], place["contact_email"]), ("", ""))

    def test_borrowed_pattern_is_a_low_confidence_guess(self):
        learned = _company()
        unknown = _company(company_number="07654321", website="https://nailbar.co.uk")
        found = {"glowroom.co.uk": {"tbrown@glowroom.co.uk": "https://glowroom.co.uk/"},
                 "nailbar.co.uk": {}}
        finder.fill([learned, unknown], found, self.PEOPLE)
        self.assertEqual(learned["contact_email_basis"], "published")
        self.assertEqual(unknown["contact_email"], "awu@nailbar.co.uk")
        self.assertEqual(unknown["contact_email_basis"], "pattern-common")
        self.assertLess(unknown["contact_email_confidence"], finder.READY)

    def test_hunter_only_asked_when_the_site_gives_nothing(self):
        asked = []

        def lookup(site):
            asked.append(site)
            return {"pattern": "{first}.{last}", "emails": [
                {"email": "hello@nailbar.co.uk", "type": "generic", "confidence": 80,
                 "first": "", "last": ""}]}

        rich = _company()
        bare = _company(company_number="07654321", website="https://nailbar.co.uk")
        found = {"glowroom.co.uk": {"tbrown@glowroom.co.uk": "https://glowroom.co.uk/"}}
        finder.fill([rich, bare], found, self.PEOPLE, hunter=lookup)
        self.assertEqual(asked, ["nailbar.co.uk"])
        self.assertEqual(bare["email"], "hello@nailbar.co.uk")
        self.assertEqual(bare["email_basis"], "hunter")
        self.assertEqual(bare["contact_email"], "amy.wu@nailbar.co.uk")
        self.assertEqual(bare["contact_email_basis"], "pattern-hunter")

    def test_scores(self):
        self.assertEqual(finder.score("published")[0], 90)
        self.assertEqual(finder.score("published", "safe")[0], 98)
        self.assertEqual(finder.score("pattern-common", "safe")[0], 90)
        self.assertEqual(finder.score("pattern-matched", "", "no")[0], 0)
        confidence, reason = finder.score("pattern-matched", "risky", "yes", "Tom Brown", "flast")
        self.assertEqual(confidence, 60)
        self.assertIn("Tom Brown", reason)

    def test_one_off_lookup_ranks_the_learned_pattern_first(self):
        crawl = lambda site: ({"j.smith@glowroom.co.uk": "https://glowroom.co.uk/",
                               "info@glowroom.co.uk": "https://glowroom.co.uk/"}, "")
        mx = lambda domain: (dns.YES, ["mx"])
        ranked, shared = finder.lookup("https://www.glowroom.co.uk", "Sarah Jones", crawl, mx)
        self.assertEqual(ranked[0][0], "s.jones@glowroom.co.uk")
        self.assertEqual(shared, ["info@glowroom.co.uk"])


class OvertureTests(unittest.TestCase):
    def test_row_with_listed_email_and_socials(self):
        row = ("o1", "Glow Room", "nail_salon", ["beauty_salon"], ["https://glowroom.co.uk"],
               ["+44 20 7946 0000"], ["Glow@gmail.com", "info@glowroom.co.uk"],
               ["https://www.instagram.com/glowroom"], "1 High St", "London", "SW1A 1AA",
               51.5, -0.1)
        place = overture.to_place(TARGET, row)
        self.assertEqual(place["email"], "info@glowroom.co.uk")
        self.assertEqual(place["email_found_on"], "overture")
        self.assertEqual(place["socials"], "https://www.instagram.com/glowroom")

    def test_both_category_column_names(self):
        self.assertEqual(overture._category_columns({"taxonomy"}),
                         ("taxonomy.primary", "taxonomy.alternates"))
        self.assertEqual(overture._category_columns({"categories"}),
                         ("categories.primary", "categories.alternate"))


class ListedEmailTests(unittest.TestCase):
    def test_post_only_rows_show_every_email_labelled(self):
        place = _company(contact_rule=rules.POST_ONLY, email="jo@gmail.com",
                         email_found_on="overture")
        finder.fill([place], {})
        self.assertEqual(place["email"], "jo@gmail.com")
        self.assertEqual(place["email_type"], contacts.PERSONAL)
        self.assertIn("personal address at gmail.com", place["email_reason"])
        self.assertEqual(place["contact_email"], "")

    def test_can_email_only_drops_listed_email_for_post_only_rows(self):
        place = _company(contact_rule=rules.POST_ONLY, email="jo@gmail.com",
                         email_found_on="overture")
        finder.fill([place], {}, everyone=False)
        self.assertEqual(place["email"], "")

    def test_listed_email_scores_and_is_upgraded_when_also_on_the_site(self):
        listed = _company(email="info@glowroom.co.uk", email_found_on="overture")
        finder.fill([listed], {})
        self.assertEqual((listed["email_basis"], listed["email_confidence"]), ("overture", 75))
        found = {"glowroom.co.uk": {"info@glowroom.co.uk": "https://glowroom.co.uk/contact"}}
        finder.fill([listed], found)
        self.assertEqual((listed["email_basis"], listed["email_confidence"]), ("published", 90))

    def test_own_domain_on_the_site_beats_a_listed_free_mail_address(self):
        place = _company(email="glowroom@gmail.com", email_found_on="overture")
        found = {"glowroom.co.uk": {"hello@glowroom.co.uk": "https://glowroom.co.uk/"}}
        finder.fill([place], found)
        self.assertEqual(place["email"], "hello@glowroom.co.uk")


class ContactTests(unittest.TestCase):
    def test_uk_phone_numbers(self):
        self.assertEqual(contacts.uk_phone("+44 (0)20 7946 0000"), ("020 7946 0000", "landline"))
        self.assertEqual(contacts.uk_phone("+447700900123"), ("07700 900123", "mobile"))
        self.assertEqual(contacts.uk_phone("0800 123 4567")[1], "non-geographic")
        self.assertEqual(contacts.uk_phone("07012 345678")[1], "other")
        self.assertEqual(contacts.uk_phone("+1 512 555 0100"), ("", ""))

    def test_mobile_only_is_flagged(self):
        place = places.blank(phone="07700900123")
        contacts.add_phones(place, ["+44 7700 900123", "07700 900456"], "GB")
        self.assertEqual(place["all_phones"], "07700 900123 (mobile); 07700 900456 (mobile)")
        self.assertEqual((place["phone_type"], place["mobile_only"]), ("mobile", "yes"))
        contacts.add_phones(place, ["01225 123456"], "GB")
        self.assertEqual((place["landline"], place["mobile_only"]), ("01225 123456", ""))

    def test_email_labels(self):
        self.assertEqual(contacts.email_label("jo@hotmail.co.uk", "glowroom.co.uk"), "personal")
        self.assertEqual(contacts.email_label("info@glowroom.co.uk", "glowroom.co.uk"),
                         "shared inbox")
        self.assertEqual(contacts.email_label("sarah@glowroom.co.uk", "glowroom.co.uk"),
                         "named person")
        self.assertEqual(contacts.email_label("sarah@salongroup.com", "glowroom.co.uk"),
                         "other business domain")

    def test_osm_handles_become_links_and_sources_are_joined(self):
        place = osm.to_place(TARGET, {"type": "node", "id": 7, "lat": 51.5, "lon": -0.1, "tags": {
            "shop": "beauty", "name": "Glow Room", "addr:postcode": "SW1A 1AA",
            "contact:instagram": "glowroom", "mobile": "07700 900123",
            "email": "hi@glowroom.co.uk;jo@gmail.com"}})
        self.assertEqual(place["socials"], "https://www.instagram.com/glowroom")
        self.assertEqual(place["mobile"], "07700 900123")
        other = places.blank(name="Glow Room", postcode="SW1A 1AA", source="overture",
                             source_id="o1", all_phones="020 7946 0000 (landline)")
        joined = merge.combine([other], [place])[0]
        self.assertEqual(joined["all_phones"], "020 7946 0000 (landline); 07700 900123 (mobile)")
        self.assertIn("jo@gmail.com (personal)", joined["all_emails"])


class NearMatchTests(unittest.TestCase):
    INDEX = {
        "glow room beauty": [{"number": "1", "name": "GLOW ROOM BEAUTY LTD", "postcode": "BA1 1AA",
                              "category": "Private Limited Company", "town": "bath",
                              "street": "1 high street", "sector": "x"}],
        "studio 8": [{"number": "2", "name": "STUDIO 8 LTD", "postcode": "BA1 2BB",
                      "category": "Private Limited Company", "town": "bath",
                      "street": "", "sector": "x"}],
    }

    def test_shorter_name_in_the_same_district_matches(self):
        place = places.blank(name="The Glow Room", postcode="BA1 5ZZ")
        self.assertEqual(companies_house.mark([place], self.INDEX), 1)
        self.assertEqual(place["company_number"], "1")
        self.assertIn("close name", place["company_match"])

    def test_different_numbers_never_match(self):
        place = places.blank(name="Studio 7", postcode="BA1 2BB")
        self.assertEqual(companies_house.mark([place], self.INDEX), 0)

    def test_two_equally_likely_companies_mean_no_match(self):
        index = dict(self.INDEX)
        index["glow room aesthetics"] = [dict(self.INDEX["glow room beauty"][0], number="3",
                                              name="GLOW ROOM AESTHETICS LTD")]
        place = places.blank(name="Glow Room", postcode="BA1 5ZZ")
        self.assertEqual(companies_house.mark([place], index), 0)

    def test_exact_matches_say_so(self):
        place = places.blank(name="Glow Room Beauty", postcode="BA1 1AA")
        companies_house.mark([place], self.INDEX)
        self.assertEqual(place["company_match"], "same name")


class StructuredDataTests(unittest.TestCase):
    PAGE = ('<script type="application/ld+json">{"@type": "BeautySalon", '
            '"telephone": "+44 1225 123456", "email": "mailto:hello@glowroom.co.uk", '
            '"sameAs": ["https://www.instagram.com/glowroom", "https://glowroom.co.uk"]}'
            '</script><span itemprop="telephone">07700 900123</span>'
            '<script type="application/ld+json">{broken</script>')

    def test_json_ld_and_microdata(self):
        found, phones, _ = emails.structured(self.PAGE)
        self.assertEqual(found, ["hello@glowroom.co.uk"])
        self.assertEqual(phones, ["+44 1225 123456", "07700 900123"])
        self.assertEqual(emails.phones_and_socials(self.PAGE)[1],
                         ["https://www.instagram.com/glowroom"])

    def test_site_map_finds_unlinked_contact_pages(self):
        class Robots:
            def site_maps(self):
                return ["https://glowroom.co.uk/sitemap.xml"]

            def can_fetch(self, agent, url):
                return True

        listing = ("<urlset><url><loc>https://glowroom.co.uk/prices</loc></url>"
                   "<url><loc>https://glowroom.co.uk/about-us</loc></url>"
                   "<url><loc>https://glowroom.co.uk/contact</loc></url>"
                   "<url><loc>https://other.co.uk/contact</loc></url></urlset>")
        original, sleep = emails._fetch, emails.time.sleep
        emails._fetch = lambda url, kind="html": (listing, url)
        emails.time.sleep = lambda seconds: None
        try:
            found = emails.sitemap_links(Robots(), "https://glowroom.co.uk/")
        finally:
            emails._fetch, emails.time.sleep = original, sleep
        self.assertEqual(found, ["https://glowroom.co.uk/contact",
                                 "https://glowroom.co.uk/about-us"])


class ValidEmailTests(unittest.TestCase):
    def test_real_looking_addresses_pass(self):
        for address in ("info@glowroom.co.uk", "sarah.o'brien@glowroom.co.uk",
                        "jo+bookings@gmail.com"):
            self.assertTrue(contacts.valid_email(address), address)

    def test_broken_placeholder_and_throwaway_addresses_fail(self):
        for address in ("a..b@glowroom.co.uk", ".a@glowroom.co.uk", "name@glowroom.co.uk",
                        "jo@mailinator.com", "jo@-glowroom.co.uk", "jo@glowroom.c",
                        "jo@@glowroom.co.uk"):
            self.assertFalse(contacts.valid_email(address), address)


class VerifyTests(unittest.TestCase):
    def test_a_confirmed_other_pattern_replaces_a_guess(self):
        place = _company(contact_name="Amy Wu", contact_email="amy@glowroom.co.uk",
                         contact_email_basis="pattern-common", email_pattern="first")
        real = {"amy.wu@glowroom.co.uk"}
        ask = lambda domain, hosts, addresses: {
            a: ("safe" if a in real else "invalid", "") for a in addresses}
        verify.fill([place], mx=lambda d: (dns.YES, ["mx"]), ask=ask)
        self.assertEqual(place["contact_email"], "amy.wu@glowroom.co.uk")
        self.assertEqual(place["email_pattern"], "first.last")
        self.assertEqual(place["contact_email_confidence"], 90)

    def test_domain_without_mail_scores_nothing(self):
        place = _company(email="info@glowroom.co.uk", email_basis="published",
                         email_found_on="https://glowroom.co.uk/")
        verify.fill([place], mx=lambda d: (dns.NO, []), ask=False)
        self.assertEqual(place["email_check"], "no mail server")
        self.assertEqual(place["email_confidence"], 0)
        self.assertEqual(place["mail_server"], dns.NO)


class PlacesFileTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "places.csv")
            places.write(path, [places.blank(name="Café Lumière", town="Bath")])
            self.assertEqual(places.read(path)[0]["name"], "Café Lumière")


if __name__ == "__main__":
    unittest.main()
