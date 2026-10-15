"""Wikidata businesses and organisations in the UK and the US (CC0).

Every organisation on Wikidata in the country (property P17) that lists an
official website (P856), a Companies House number (P2622) or a LinkedIn
company page (P4264): mostly larger firms, public bodies, universities,
museums and clubs. Each gives its name, website, company number, LinkedIn
page, latest employee count, official email and phone when listed, and the
town of its head office.

The public query service stops any query after 60 seconds, so the work is
split up. First the item numbers are found: the organisation types are
listed (every subclass of "organisation", Q43229), then asked about a few
hundred types at a time, halving any batch that runs out of time. Then the
details are fetched for a hundred or so items at a time. Every answer is kept
in the cache folder, so a rerun asks nothing again; empty the folder to
refresh. Bands and other musical groups are left out, and so are
organisations Wikidata says have been dissolved.

In the UK an organisation with a company number or a company word in its
name (Ltd, plc and so on) may be emailed; anyone else is post only. US
organisations may be emailed under CAN-SPAM.
"""

import csv
import glob
import hashlib
import os
import re
import time
import types
import urllib.error
import urllib.parse

from .. import text
from . import corporate_name, download, joined, record, rule

ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "Recon/0.1 (in-house outreach research; https://github.com/EmotiveImpact/Recon)",
    "Accept": "text/csv",
}
COUNTRIES = {"GB": "Q145", "US": "Q30"}
ORGANISATION = "Q43229"
LEFT_OUT = ("Q215380", "Q2088357")  # musical group, musical ensemble
CLASS_BATCH = 300
ITEM_BATCH = 100
_PAUSE = 1.0  # seconds between live queries, to be gentle on the public service
# During an outage the service allows one query a minute, which would make a
# full copy take most of a day. After this much waiting in one run, give up
# and use the copy in the incoming folder instead, if there is one.
# In the same way, stop asking after this many seconds of live queries in one
# run; what was fetched stays cached, so each build gets further.
WAIT_BUDGET = 600
TIME_BUDGET = 1800
_waited = [0]
_started = []

# A copy fetched earlier by another session: items with a Companies House
# number or LinkedIn page only, without emails, phones or head offices.
# Set RECON_INCOMING to look somewhere else.
INCOMING = "/mnt/project-files/master-db/incoming"

DETAILS = """SELECT ?item (SAMPLE(?l) AS ?label) (SAMPLE(?lg) AS ?label_gb)
  (GROUP_CONCAT(DISTINCT STR(?w); separator=" ") AS ?websites)
  (GROUP_CONCAT(DISTINCT ?chn; separator=" ") AS ?company_numbers)
  (GROUP_CONCAT(DISTINCT ?li; separator=" ") AS ?linkedin)
  (GROUP_CONCAT(DISTINCT CONCAT(STR(?emp), "@", COALESCE(STR(?when), "")); separator=" ") AS ?employees)
  (GROUP_CONCAT(DISTINCT STR(?mail); separator=" ") AS ?emails)
  (GROUP_CONCAT(DISTINCT ?tel; separator="|") AS ?phones)
  (SAMPLE(?hqName) AS ?headquarters) (SAMPLE(?end) AS ?dissolved)
WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item rdfs:label ?l FILTER(LANG(?l) = "en") }
  OPTIONAL { ?item rdfs:label ?lg FILTER(LANG(?lg) = "en-gb") }
  OPTIONAL { ?item wdt:P856 ?w }
  OPTIONAL { ?item wdt:P2622 ?chn }
  OPTIONAL { ?item wdt:P4264 ?li }
  OPTIONAL { ?item p:P1128 ?st . ?st ps:P1128 ?emp . OPTIONAL { ?st pq:P585 ?when } }
  OPTIONAL { ?item wdt:P968 ?mail }
  OPTIONAL { ?item wdt:P1329 ?tel }
  OPTIONAL { ?item wdt:P159 ?hq . ?hq rdfs:label ?hqName FILTER(LANG(?hqName) = "en") }
  OPTIONAL { ?item wdt:P576 ?end }
} GROUP BY ?item"""


def _qid(uri):
    return (uri or "").rsplit("/", 1)[-1]


class Busy(RuntimeError):
    """The query service keeps refusing: too many requests."""


def ask(query, path, waits=3):
    """The answer to a query as a list of rows, kept at path. When the
    service says to slow down, wait as long as it asks (a few times at most)."""
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        _started[:] = _started or [time.time()]
        if time.time() - _started[0] > TIME_BUDGET:
            raise Busy("Wikidata copy not finished within this run's time limit")
        url = ENDPOINT + "?" + urllib.parse.urlencode({"query": " ".join(query.split())})
        for attempt in range(waits + 1):
            try:
                download(url, path, headers=HEADERS, attempts=1)
                break
            except urllib.error.HTTPError as error:
                if error.code != 429:
                    raise
                pause = min(int(error.headers.get("Retry-After") or 60), 300)
                if attempt == waits or _waited[0] + pause > WAIT_BUDGET:
                    raise Busy("Wikidata query service is rate-limiting") from error
                _waited[0] += pause
                time.sleep(pause)
        time.sleep(_PAUSE)
    with open(path, encoding="utf-8", errors="replace", newline="") as handle:
        return list(csv.DictReader(handle))


def subclasses(root, cache):
    query = f"SELECT DISTINCT ?c WHERE {{ ?c wdt:P279* wd:{root} }}"
    return {_qid(r["c"]) for r in ask(query, os.path.join(cache, f"subclasses-{root}.csv"))}


def organisation_types(cache):
    found = subclasses(ORGANISATION, cache)
    for root in LEFT_OUT:
        found -= subclasses(root, cache)
    return sorted(found, key=lambda q: int(q[1:]) if q[1:].isdigit() else 0)


def _with_website(country, classes, cache):
    """Items of these types in the country with a website; a batch that runs
    out of time is halved until it fits."""
    key = hashlib.sha1(" ".join(classes).encode()).hexdigest()[:16]
    values = " ".join(f"wd:{c}" for c in classes)
    query = (f"SELECT DISTINCT ?item WHERE {{ VALUES ?class {{ {values} }} "
             f"?item wdt:P31 ?class; wdt:P17 wd:{COUNTRIES[country]}; wdt:P856 [] . }}")
    try:
        return {_qid(r["item"]) for r in ask(query, os.path.join(cache, country, f"site-{key}.csv"))}
    except Busy:
        raise
    except OSError:  # Ran out of time: try each half.
        if len(classes) == 1:
            raise
        half = len(classes) // 2
        return (_with_website(country, classes[:half], cache)
                | _with_website(country, classes[half:], cache))


def item_ids(country, cache):
    """Every organisation in the country with a website, company number or
    LinkedIn company page."""
    types_ = organisation_types(cache)
    known = set(types_)
    found = set()
    for start in range(0, len(types_), CLASS_BATCH):
        found |= _with_website(country, types_[start:start + CLASS_BATCH], cache)
    # Companies House numbers and LinkedIn company pages are few enough to
    # ask for in one go; the types are checked here instead.
    for prop in ("P2622", "P4264"):
        query = (f"SELECT ?item ?class WHERE {{ ?item wdt:{prop} []; "
                 f"wdt:P17 wd:{COUNTRIES[country]}; wdt:P31 ?class . }}")
        for row in ask(query, os.path.join(cache, country, f"{prop}.csv")):
            if prop == "P2622" or _qid(row["class"]) in known:
                found.add(_qid(row["item"]))
    return sorted(found, key=lambda q: int(q[1:]) if q[1:].isdigit() else 0)


def details(country, ids, cache):
    for start in range(0, len(ids), ITEM_BATCH):
        batch = ids[start:start + ITEM_BATCH]
        query = DETAILS % " ".join(f"wd:{q}" for q in batch)
        name = f"details-{batch[0]}-{batch[-1]}-{len(batch)}.csv"
        yield from ask(query, os.path.join(cache, country, name))


def incoming_rows(country):
    """Rows in the details shape from the incoming copy, or None when there
    is no copy. Its columns: item, itemLabel, chn, website, linkedin,
    employees, country (one row per combination of values)."""
    folder = os.environ.get("RECON_INCOMING", INCOMING)
    paths = [p for p in sorted(glob.glob(os.path.join(folder, "wikidata", "*.csv")))
             if os.path.getsize(p) > 0]
    if not paths:
        return None
    found = []
    for path in paths:
        with open(path, encoding="utf-8", errors="replace", newline="") as handle:
            found.extend(csv.DictReader(handle))
    return merge_flat(found, country)


def merge_flat(flat, country):
    """One details-shaped row per item from rows with one value each."""
    items = {}
    for row in flat:
        if _qid(row.get("country")) != COUNTRIES[country]:
            continue
        item = items.setdefault(row["item"], {
            "item": row["item"], "label": row.get("itemLabel", ""), "websites": [],
            "company_numbers": [], "linkedin": [], "employees": [], "emails": "", "phones": "",
            "headquarters": "", "dissolved": ""})
        for key, column in (("websites", "website"), ("company_numbers", "chn"),
                            ("linkedin", "linkedin"), ("employees", "employees")):
            value = (row.get(column) or "").strip()
            if key == "employees" and value:
                value += "@"
            if value and value not in item[key]:
                item[key].append(value)
    for item in items.values():
        if item["label"] == _qid(item["item"]):  # No English label.
            item["label"] = ""
        for key in ("websites", "company_numbers", "linkedin", "employees"):
            item[key] = " ".join(item[key])
    return list(items.values())


def pick_website(websites):
    """The organisation's main site: its own sites, shortest address first."""
    own = [w for w in (websites or "").split() if text.own_website(w)]
    own.sort(key=lambda w: (urllib.parse.urlparse(w).path.strip("/") != "", len(w)))
    return own[0] if own else ""


def latest_employees(value):
    """'250@2021-01-01T00:00:00Z 300@2023-...' -> (300, '2023'); undated
    figures count as oldest."""
    best = None
    for part in (value or "").split():
        number, _, when = part.partition("@")
        try:
            count = int(float(number))
        except ValueError:
            continue
        key = (when[:10], count)
        if best is None or key > best:
            best = key
    return (best[1], best[0][:4]) if best else (None, "")


def local_phones(value, country):
    """Only the numbers in the country itself (+44 or +1)."""
    code = "+44" if country == "GB" else "+1"
    return [p for p in (value or "").split("|") if p.strip().replace(" ", "").startswith(code)]


def company_number(value):
    for number in (value or "").split():
        number = number.upper().replace(" ", "")
        if re.fullmatch(r"[A-Z]{0,2}\d{5,8}", number):
            return number
    return ""


def to_record(source, country, row):
    qid = _qid(row["item"])
    name = row.get("label_gb") if country == "GB" and row.get("label_gb") else row.get("label")
    if not name or row.get("dissolved"):
        return None
    number = company_number(row.get("company_numbers"))
    if country == "GB":
        corporate = bool(number) or corporate_name(name)
        can, why = rule("GB", corporate, "registered company (company number on Wikidata)" if number
                        else "trading as a company" if corporate
                        else "not shown to be a company: post only")
    else:
        can, why = rule("US", None, "US organisation: CAN-SPAM")
    staff, year = latest_employees(row.get("employees"))
    linkedin = [f"https://www.linkedin.com/company/{v}" for v in (row.get("linkedin") or "").split()]
    emails = [e[7:] if e.lower().startswith("mailto:") else e for e in (row.get("emails") or "").split()]
    return record(
        source, qid, name, kind="organisation",
        category=f"{staff:,} employees ({year})" if staff and year else
                 f"{staff:,} employees" if staff else "",
        town=row.get("headquarters") or "", country=country,
        website=pick_website(row.get("websites")), emails=emails,
        phones=local_phones(row.get("phones"), country), socials=linkedin,
        company_number=number if country == "GB" else "",
        registration_number=f"Wikidata {qid}",
        can_email=can, rule_reason=why, source_url=f"https://www.wikidata.org/wiki/{qid}")


def _loader(country):
    source = {
        "name": f"wikidata-{country.lower()}",
        "title": f"Wikidata organisations, {'United Kingdom' if country == 'GB' else 'United States'}",
        "country": country,
        "url": "https://query.wikidata.org/",
        "licence": "CC0 1.0 (Wikidata)",
        "updated": "live (copied when the cache is emptied)",
        "fields": "name, website, company number, LinkedIn page, employees, email, phone, head office town",
    }

    def rows(cache):
        os.makedirs(os.path.join(cache, country), exist_ok=True)
        try:
            found = list(details(country, item_ids(country, cache), cache))
        except Busy:
            found = incoming_rows(country)
            if found is None:
                raise
            print(f"{source['name']}: the query service is slow or rate-limiting; using the incoming "
                  "copy (company number and LinkedIn items only). Answers fetched so far stay cached.")
        for row in found:
            made = to_record(source, country, row)
            if made:
                yield made

    return types.SimpleNamespace(SOURCE=source, rows=rows)


SOURCES = [_loader("GB"), _loader("US")]
