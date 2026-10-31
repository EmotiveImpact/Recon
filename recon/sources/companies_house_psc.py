"""Companies House "People with significant control" snapshot.

Every UK company must tell Companies House who owns or controls it: the people
and companies holding more than a quarter of the shares or votes, or who can
appoint the board. This file lists them for every company, one line of JSON per
person, in no particular order. It names owners only, with no company name,
address or contact details, so each record carries just the company number and
joins the company's other entries in the master table on that number.

Only current owners are kept (anyone who has ceased is dropped), and the
statements a company files when it has no owner to name are skipped. Updated
every morning; the one-file snapshot is about 2.2 GB zipped (13 GB of text)
and is read straight out of the zip, never unpacked. Because the lines are not
grouped by company, the owners are first written to small sorted files in the
cache folder (a few hundred MB in all), which are merged and then deleted.

Companies House publishes the snapshot free of charge for anyone to reuse as
public register data. The owners are named people, so their names count as
personal data under UK GDPR: use them to address a letter or email to the right
person at a company, not to market to them as individuals.
"""

import glob
import heapq
import io
import itertools
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile

from . import USER_AGENT, download, record, rule

SOURCE = {
    "name": "companies-house-psc",
    "title": "Companies House people with significant control",
    "country": "GB",
    "url": "https://download.companieshouse.gov.uk/en_pscdata.html",
    "licence": "Companies House public register data, free to reuse (owners' names are personal data)",
    "updated": "daily",
    "fields": "company number, owners and how much of the company each controls",
    "enrich_only": True,  # Added to companies found elsewhere, never on its own.
}

_LINK = re.compile(r'href="(persons-with-significant-control-snapshot-[\d-]+\.zip)"')

# The PSC kinds, in plain words. Statements and exemptions are not owners.
ROLES = {
    "individual-person-with-significant-control": "owner",
    "corporate-entity-person-with-significant-control": "corporate owner",
    "legal-person-person-with-significant-control": "legal owner",
    "individual-beneficial-owner": "beneficial owner",
    "corporate-entity-beneficial-owner": "corporate beneficial owner",
    "legal-person-beneficial-owner": "legal beneficial owner",
}

_SHARE = re.compile(r"(ownership-of-shares|voting-rights)-(\d+)-to-(\d+)-percent")


# A folder where a copy may already have been fetched, one subfolder per
# source; set RECON_INCOMING to look somewhere else.
INCOMING = "/mnt/project-files/master-db/incoming"


def fetched_copy(source, pattern, key=None):
    """The newest complete zip matching pattern in the incoming folder for
    this source, or None. Half-downloaded files are passed over."""
    folder = os.path.join(os.environ.get("RECON_INCOMING", INCOMING), source)
    found = sorted(glob.glob(os.path.join(folder, pattern)), key=key)
    for path in reversed(found):
        try:
            with zipfile.ZipFile(path):  # Fails if the file is incomplete.
                return path
        except (OSError, zipfile.BadZipFile):
            continue
    return None


def latest_zip(cache):
    pattern = "persons-with-significant-control-snapshot-*.zip"
    found = fetched_copy(SOURCE["name"], pattern)
    if found:
        return found
    found = sorted(glob.glob(os.path.join(cache, pattern)))
    if found:
        return found[-1]
    request = urllib.request.Request(SOURCE["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        names = _LINK.findall(response.read().decode("utf-8", "replace"))
    if not names:
        raise RuntimeError("No PSC snapshot listed on the Companies House download page")
    name = sorted(names)[-1]
    return download("https://download.companieshouse.gov.uk/" + name, os.path.join(cache, name))


def control(natures):
    """How much of the company someone controls, in a few words, from
    Companies House's "natures of control" codes."""
    natures = [n for n in natures or [] if isinstance(n, str)]
    shares = votes = ""
    for nature in natures:
        found = _SHARE.search(nature)
        if not found:
            continue
        low, high = found.group(2), found.group(3)
        words = f"{low}%+" if high == "100" else f"{low}-{high}%"
        if found.group(1) == "ownership-of-shares":
            shares = shares or f"{words} shares"
        else:
            votes = votes or f"{words} votes"
    if shares:
        return shares
    if votes:
        return votes
    natures = " ".join(natures)
    if "appoint-and-remove-directors" in natures:
        return "appoints the directors"
    if "significant-influence-or-control" in natures:
        return "significant influence"
    return ""


def person(data):
    """'Jane Smith (owner, 75%+ shares)', or '' for a line that is not a
    current, named owner."""
    role = ROLES.get(data.get("kind", ""))
    if not role or data.get("ceased_on") or data.get("ceased"):
        return ""
    parts = data.get("name_elements") or {}
    name = " ".join(p for p in (parts.get("forename"), parts.get("surname")) if p)
    name = " ".join((name or data.get("name") or "").split())
    if not name:
        return ""
    detail = control(data.get("natures_of_control"))
    return f"{name} ({role}, {detail})" if detail else f"{name} ({role})"


def owners(lines):
    """(company number, owner) for each current, named owner in the
    snapshot's JSON lines."""
    for line in lines:
        if not line.strip():
            continue
        item = json.loads(line)
        company = (item.get("company_number") or "").strip().upper()
        company = company.zfill(8) if company.isdigit() else company
        text = person(item.get("data") or {})
        if company and text:
            yield company, text


def companies(pairs):
    """One record per company from (company number, owner) pairs sorted by
    company number."""
    for company, group in itertools.groupby(pairs, key=lambda pair: pair[0]):
        people = []
        for _, text in group:
            if text not in people:
                people.append(text)
        can, why = rule("GB", True, "company on Companies House: a corporate body under PECR")
        # The snapshot has no company names; the master table joins this
        # record to the company's other entries on its number.
        yield record(SOURCE, company, "", kind="company", country="GB", people=people,
                     registration_number=company, company_number=company,
                     can_email=can, rule_reason=why)


def sorted_pairs(pairs, folder, chunk=2_000_000):
    """The pairs sorted by company number without holding them all in
    memory: sorted runs go to files in folder and are merged back."""
    runs, batch = [], []
    os.makedirs(folder, exist_ok=True)
    work = tempfile.mkdtemp(prefix="psc-sort-", dir=folder)
    try:
        for pair in pairs:
            batch.append(pair)
            if len(batch) >= chunk:
                runs.append(_write_run(sorted(batch), work, len(runs)))
                batch = []
        if not runs:  # Small enough to sort in memory.
            yield from sorted(batch)
            return
        if batch:
            runs.append(_write_run(sorted(batch), work, len(runs)))
        handles = [open(path, encoding="utf-8") for path in runs]
        try:
            lines = heapq.merge(*handles)
            yield from (tuple(line.rstrip("\n").split("\t", 1)) for line in lines)
        finally:
            for handle in handles:
                handle.close()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _write_run(batch, folder, number):
    path = os.path.join(folder, f"run-{number:03d}.tsv")
    with open(path, "w", encoding="utf-8") as out:
        out.writelines(f"{company}\t{text}\n" for company, text in batch)
    return path


def rows(cache):
    path = latest_zip(cache)
    with zipfile.ZipFile(path) as archive:
        member = next(n for n in archive.namelist() if not n.endswith("/"))
        with archive.open(member) as raw:
            lines = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
            yield from companies(sorted_pairs(owners(lines), cache))
