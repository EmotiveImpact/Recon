"""recon: find businesses to contact from open data, and how we may contact them.

    python -m recon run targets/saleane-uk.json --companies-house BasicCompanyData.zip

Each step reads and writes data/<target>/places.csv, so steps can be run one
at a time, repeated, or resumed. The finished list goes to out/.
"""

import argparse
import collections
import os
import re
import sys
from datetime import date

from . import (companies_house, contacts, dns, emails, finder, geo, hunter, mailbox, merge, osm,
               overture, people, places, registers, rules, text, verify)
from .target import Target

STEPS = ["places", "companies", "rules", "people", "emails", "verify", "export"]


def _paths(target_file):
    slug = os.path.splitext(os.path.basename(target_file))[0]
    folder = os.path.join("data", slug)
    return slug, folder, os.path.join(folder, "places.csv")


def step_places(target, store, args):
    contacts.fetch_lists()
    groups = []
    if not args.skip_overture:
        print("Reading Overture Maps…")
        found, release = overture.fetch(target, release=args.overture_release)
        print(f"  {len(found):,} places from Overture release {release}")
        groups.append(found)
    if not args.skip_osm:
        print("Reading OpenStreetMap…")
        found = osm.fetch(target, extract=args.osm_extract or None,
                          folder=os.path.join("data", "osm"), overpass=args.osm_overpass)
        print(f"  {len(found):,} places from OpenStreetMap")
        groups.append(found)
    if target.registers:
        print("Reading registers…")
        groups.append(registers.fetch(target, os.path.join("data", "registers"), args.postcodes))
    combined = merge.combine(*groups, target=target)
    print(f"  {len(combined):,} businesses once duplicates are joined")
    places.write(store, combined)


def step_companies(target, store, args):
    if target.country != "GB":
        print("Companies House only covers the UK; skipping")
        return
    if not args.companies_house:
        print("No Companies House file given (--companies-house); everyone stays 'post only'")
        return
    rows = places.read(store)
    print("Reading Companies House…")
    named = {text.name_key(r["legal_name"]) for r in rows if r["legal_name"]}
    index, total = companies_house.load(args.companies_house, target.sic_codes(), named)
    print(f"  {total:,} active companies in these trades")
    postcodes = None
    if not args.skip_postcodes:
        path = args.postcodes or geo.postcode_file(os.path.join("data", "geo"))
        if path:
            postcodes = geo.Postcodes(path, companies_house.wanted_postcodes(index))
    matched = companies_house.mark(rows, index, target, postcodes)
    print(f"  {matched:,} of {len(rows):,} businesses matched to a company")
    places.write(store, rows)


def step_rules(target, store, args):
    rows = places.read(store)
    rules.apply(rows, target.country)
    places.write(store, rows)
    counts = collections.Counter(r["contact_rule"] for r in rows)
    print("Contact rules: " + ", ".join(f"{k} {v:,}" for k, v in counts.items()))


def step_people(target, store, args):
    rows = places.read(store)
    print("Looking up who runs each company we may email (Companies House)…")
    looked_up = people.fill(rows, os.path.join(os.path.dirname(store), "people-cache.jsonl"))
    if looked_up is None:
        print("  No RECON_COMPANIES_HOUSE_KEY set, so no names this time. The key is free from "
              "https://developer.company-information.service.gov.uk/")
        return
    places.write(store, rows)
    print(f"  {looked_up:,} companies looked up; "
          f"{sum(1 for r in rows if r['contact_name']):,} businesses have a named director")


def step_emails(target, store, args):
    rows = places.read(store)
    folder = os.path.dirname(store)
    cache = os.path.join(folder, "email-cache.jsonl")
    contacts.fetch_lists()
    print("Looking for emails on businesses' own websites…")
    everyone = not args.can_email_only
    emails.fill(rows, cache, everyone=everyone, workers=args.workers, country=target.country)
    lookup = None
    if args.hunter:
        if hunter.key():
            print("  Hunter is switched on: each new domain uses one of your Hunter searches")
            lookup = hunter.Lookup(os.path.join(folder, "hunter-cache.jsonl"))
        else:
            print("  --hunter needs RECON_HUNTER_KEY; carrying on without Hunter")
    print("Working out address patterns and named contacts…")
    finder.fill(rows, emails.load(cache), people.load(os.path.join(folder, "people-cache.jsonl")),
                hunter=lookup, everyone=everyone)
    places.write(store, rows)
    print(f"  {sum(1 for r in rows if r['email']):,} businesses now have an email; "
          f"{sum(1 for r in rows if r['contact_email']):,} have a named person's address")
    if lookup:
        print(f"  {lookup.asked:,} Hunter searches used")


def step_verify(target, store, args):
    rows = places.read(store)
    print("Checking emails…")
    print(f"  {verify.fill(rows, smtp_from=args.smtp_from):,} checked")
    places.write(store, rows)


def step_export(target, store, args, slug):
    rows = places.read(store)
    rows.sort(key=lambda r: (r["contact_rule"] != "can email", r["sector"], r["town"], r["name"]))
    out = os.path.join("out", f"{slug}-{date.today().isoformat()}.csv")
    places.write(out, rows)
    print(f"\n{target.name}: {len(rows):,} businesses written to {out}\n")
    table = collections.Counter((r["sector"], r["contact_rule"]) for r in rows)
    def ready(row, field):
        confidence = row[f"{field}_confidence"]
        return (row[field] and row["contact_rule"] == "can email"
                and confidence != "" and int(confidence) >= finder.READY)

    with_email = collections.Counter(r["sector"] for r in rows if ready(r, "email"))
    with_person = collections.Counter(r["sector"] for r in rows if ready(r, "contact_email"))
    for sector in target.sectors:
        line = ", ".join(f"{rule} {n:,}" for (s, rule), n in sorted(table.items()) if s == sector)
        print(f"  {sector}: {line or 'none'}; emails ready {with_email[sector]:,}, "
              f"named people ready {with_person[sector]:,}")
    print(f"  (ready means a confidence of {finder.READY} or more)")


def find_one(args):
    """recon find glowroom.co.uk --name "Sarah Jones": one person's likely address."""
    ask = None
    if verify.reacher_running():
        ask = verify._reacher
    elif args.smtp_from:
        ask = mailbox.Checker(args.smtp_from).check
    ranked, shared = finder.lookup(args.target, args.name, emails.crawl, dns.Cache(), ask)
    print(f"Likely addresses for {args.name} at {text.domain(args.target)}, best first:")
    for address, confidence, reason in ranked[:args.top]:
        print(f"  {confidence:>3}  {address}\n       {reason}")
    if shared:
        print("Shared inboxes published on the site: " + ", ".join(shared))
    print("Before emailing: in the UK, only email a person at a limited company or LLP. "
          "Sole traders and partnerships need their consent first (docs/RULES.md).")
    return 0



def main(argv=None):
    parser = argparse.ArgumentParser(prog="recon", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["run", "categories", "find", *STEPS])
    parser.add_argument("target", help="target list, such as targets/saleane-uk.json "
                                       "(for 'find': the business's website or domain)")
    parser.add_argument("--name", help="for 'find': the person's first and last name")
    parser.add_argument("--top", type=int, default=5, help="for 'find': how many to show")
    parser.add_argument("--smtp-from", help="your own email address: switches on the direct "
                                            "mailbox check in 'verify' (needs port 25 open)")
    parser.add_argument("--hunter", action="store_true",
                        help="in 'emails', also ask Hunter (needs RECON_HUNTER_KEY; uses credits)")
    parser.add_argument("--companies-house", nargs="*", default=[],
                        help="Companies House free data zip or CSV files (UK only)")
    parser.add_argument("--postcodes", help="GeoNames' GB_full.csv.zip, for distances to "
                                            "registered offices (downloaded to data/geo/ if not given)")
    parser.add_argument("--skip-postcodes", action="store_true",
                        help="judge distances from the places found instead")
    parser.add_argument("--overture-release", help="defaults to the newest")
    parser.add_argument("--skip-overture", action="store_true")
    parser.add_argument("--skip-osm", action="store_true")
    parser.add_argument("--osm-extract", nargs="*", default=[],
                        help="read these .osm.pbf files instead of downloading the country's "
                             "OpenStreetMap extract (kept in data/osm/ for a week)")
    parser.add_argument("--osm-overpass", action="store_true",
                        help="ask the public Overpass API instead of reading an extract")
    parser.add_argument("--can-email-only", action="store_true",
                        help="only read the websites of businesses we may email "
                             "(by default every website is read, so you see every address)")
    parser.add_argument("--all-emails", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--words", nargs="*", default=[],
                        help="for 'categories': words to look for in category names "
                             "(by default, the words of the target's sector names)")
    args = parser.parse_args(argv)

    if args.command == "find":
        if not args.name:
            parser.error("find needs --name, such as --name \"Sarah Jones\"")
        return find_one(args)

    target = Target.load(args.target)
    slug, _, store = _paths(args.target)

    if args.command == "categories":
        found = args.words or sorted({w for name in target.sectors
                                      for w in re.findall(r"[a-z]{3,}", name.lower())
                                      if w not in ("and", "the", "for", "other")})
        for category, count in overture.categories(target, found, args.overture_release):
            print(f"{count:>8,}  {category}")
        return 0

    steps = STEPS if args.command == "run" else [args.command]
    if steps[0] != "places" and not os.path.exists(store):
        sys.exit(f"No {store} yet. Run the 'places' step first.")
    for step in steps:
        if step == "export":
            step_export(target, store, args, slug)
        else:
            globals()[f"step_{step}"](target, store, args)
    return 0
