"""recon: find businesses to contact from open data, and how we may contact them.

    python -m recon run targets/saleane-uk.json --companies-house BasicCompanyData.zip

Each step reads and writes data/<target>/places.csv, so steps can be run one
at a time, repeated, or resumed. The finished list goes to out/.
"""

import argparse
import collections
import os
import sys
from datetime import date

from . import companies_house, emails, merge, osm, overture, places, rules, verify
from .target import Target

STEPS = ["places", "companies", "rules", "emails", "verify", "export"]


def _paths(target_file):
    slug = os.path.splitext(os.path.basename(target_file))[0]
    folder = os.path.join("data", slug)
    return slug, folder, os.path.join(folder, "places.csv")


def step_places(target, store, args):
    groups = []
    if not args.skip_overture:
        print("Reading Overture Maps…")
        found, release = overture.fetch(target, release=args.overture_release)
        print(f"  {len(found):,} places from Overture release {release}")
        groups.append(found)
    if not args.skip_osm:
        print("Reading OpenStreetMap…")
        found = osm.fetch(target)
        print(f"  {len(found):,} places from OpenStreetMap")
        groups.append(found)
    combined = merge.combine(*groups)
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
    index, total = companies_house.load(args.companies_house, target.sic_codes())
    print(f"  {total:,} active companies in these trades")
    matched = companies_house.mark(rows, index)
    print(f"  {matched:,} of {len(rows):,} businesses matched to a company")
    places.write(store, rows)


def step_rules(target, store, args):
    rows = places.read(store)
    rules.apply(rows, target.country)
    places.write(store, rows)
    counts = collections.Counter(r["contact_rule"] for r in rows)
    print("Contact rules: " + ", ".join(f"{k} {v:,}" for k, v in counts.items()))


def step_emails(target, store, args):
    rows = places.read(store)
    print("Looking for emails on businesses' own websites…")
    emails.fill(rows, os.path.join(os.path.dirname(store), "email-cache.jsonl"),
                everyone=args.all_emails, workers=args.workers)
    places.write(store, rows)
    print(f"  {sum(1 for r in rows if r['email']):,} businesses now have an email")


def step_verify(target, store, args):
    rows = places.read(store)
    print("Checking emails…")
    print(f"  {verify.fill(rows):,} checked")
    places.write(store, rows)


def step_export(target, store, args, slug):
    rows = places.read(store)
    rows.sort(key=lambda r: (r["contact_rule"] != "can email", r["sector"], r["town"], r["name"]))
    out = os.path.join("out", f"{slug}-{date.today().isoformat()}.csv")
    places.write(out, rows)
    print(f"\n{target.name}: {len(rows):,} businesses written to {out}\n")
    table = collections.Counter((r["sector"], r["contact_rule"]) for r in rows)
    with_email = collections.Counter(r["sector"] for r in rows
                                     if r["email"] and r["contact_rule"] == "can email")
    for sector in target.sectors:
        line = ", ".join(f"{rule} {n:,}" for (s, rule), n in sorted(table.items()) if s == sector)
        print(f"  {sector}: {line or 'none'}; emails ready {with_email[sector]:,}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="recon", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["run", "categories", *STEPS])
    parser.add_argument("target", help="target list, such as targets/saleane-uk.json")
    parser.add_argument("--companies-house", nargs="*", default=[],
                        help="Companies House free data zip or CSV files (UK only)")
    parser.add_argument("--overture-release", help="defaults to the newest")
    parser.add_argument("--skip-overture", action="store_true")
    parser.add_argument("--skip-osm", action="store_true")
    parser.add_argument("--all-emails", action="store_true",
                        help="also look up emails for 'post only' businesses")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--words", nargs="*", default=["hair", "beauty", "spa", "salon"],
                        help="for 'categories': words to look for in category names")
    args = parser.parse_args(argv)

    target = Target.load(args.target)
    slug, _, store = _paths(args.target)

    if args.command == "categories":
        for category, count in overture.categories(target, args.words, args.overture_release):
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
