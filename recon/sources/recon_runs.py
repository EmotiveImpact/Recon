"""Finished Recon lists (out/<target>-<date>.csv), folded into the master table.

A Recon run finds businesses on the open maps (Overture, OpenStreetMap),
matches them to Companies House and reads their own websites for emails and
phones. Those contacts are what the registers lack, so the newest list for
each target is loaded here and joins the register entries by company number,
name and postcode, email or website. The folder is `out/` unless RECON_RUNS
names another. The UK trade sweep's lists (/mnt/project-files/master-db/trades/,
or RECON_TRADES) are read too.
"""

import glob
import json
import os
import re
from datetime import date

from . import read_csv, record

SOURCE = {
    "name": "recon-runs",
    "title": "Recon's own searches (maps, Companies House and businesses' websites)",
    "country": "GB, US",
    "url": "https://github.com/EmotiveImpact/Recon",
    "licence": "Overture Maps (CDLA-Permissive-2.0, ODbL), OpenStreetMap (ODbL), "
               "Companies House (OGL v3.0); contacts published on the businesses' own websites",
    "updated": "each run",
    "fields": "name, address, website, emails, phones, socials, contact name, company number",
}

_DATED = re.compile(r"^(?P<slug>.+)-(?P<day>\d{4}-\d{2}-\d{2})\.csv$")


def newest_lists(folder):
    """The newest finished list for each target, as {slug: (day, path)}."""
    found = {}
    for path in glob.glob(os.path.join(folder, "*.csv")):
        match = _DATED.match(os.path.basename(path))
        if match and match["day"] > found.get(match["slug"], ("", ""))[0]:
            found[match["slug"]] = (match["day"], path)
    return found


def target_country(slug, folder="targets"):
    """The country in the run's target list; GB when the list is gone."""
    try:
        with open(os.path.join(folder, f"{slug}.json"), encoding="utf-8") as handle:
            return json.load(handle)["country"].upper()
    except (OSError, ValueError, KeyError):
        return "GB"


def trade_lists(folder):
    """Lists from the trade-by-trade sweep (<folder>/<trade>.csv, written in
    Recon's export shape), as {slug: (day, path)}, dated by when they were saved."""
    found = {}
    for path in glob.glob(os.path.join(folder, "*.csv")):
        day = date.fromtimestamp(os.path.getmtime(path)).isoformat()
        found["trades-" + os.path.splitext(os.path.basename(path))[0]] = (day, path)
    return found


def rows(cache):
    lists = newest_lists(os.environ.get("RECON_RUNS", "out"))
    lists.update(trade_lists(os.environ.get("RECON_TRADES", "/mnt/project-files/master-db/trades")))
    for slug, (day, path) in sorted(lists.items()):
        country = target_country(slug)
        for row in read_csv(path):
            can = row["contact_rule"] or "post only"
            yield record(
                SOURCE, f"{slug}:{row['key']}", row["name"], other_name=row["other_names"],
                kind=row["sector"].lower(), category=row["category"],
                legal_form=row["company_type"], address=row["address"], town=row["town"],
                postcode=row["postcode"], country=country, website=row["website"],
                emails=row["all_emails"] or row["email"], phones=row["all_phones"],
                socials=row["socials"], people=row["contact_name"],
                company_number=row["company_number"] if row["company_match"] else "",
                can_email=can,
                rule_reason=("company on Companies House" if can == "can email"
                             else "not shown to be a company: post only"),
                source_url=f"recon:{slug}", fetched=day)
