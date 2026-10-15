"""NHS Organisation Data Service reports (NHS England, Open Government Licence).

Every GP practice, dental practice, community pharmacy, care home and
optician site known to the NHS in England (and Wales for some reports), with
address and, for GP practices and pharmacies, a phone number. No emails or
websites: Recon finds them later. Updated weekly to quarterly per report.

The files have no header row. Every ODS "standard" report uses the same 27
columns, mapped below by position from the ODS data dictionary:
 0 organisation code, 1 name, 2 national grouping, 3 health geography,
 4-7 address lines 1 to 4 (line 4 is the town), 8 address line 5 (county),
 9 postcode, 10 open date, 11 close date, 12 status, 13 sub-type or role,
 14 parent organisation (commissioner, or owner for pharmacies, care homes
 and opticians), 15-16 joined and left parent, 17 phone, 21 amended flag,
 25 primary role (GP report), 26 country (care home reports).
A row is active when it has no close date and is not marked inactive.
"""

import csv
import os
import types

from . import corporate_name, download, joined, record, rule

REPORT_URL = "https://www.odsdatasearchandexport.nhs.uk/api/getReport?report={}"
LICENCE = "Open Government Licence v3.0"

CODE, NAME, GROUP, GEOGRAPHY = 0, 1, 2, 3
CLOSED, STATUS, SUBTYPE, PARENT, PHONE, ROLE, NATION = 11, 12, 13, 14, 17, 25, 26

# Owners outside the UK's marketing rules (crown dependencies) are left out.
_NOT_UK = {"ISLE OF MAN", "JERSEY", "GUERNSEY"}


def _report(cache, name):
    path = download(REPORT_URL.format(name), os.path.join(cache, f"{name}.csv"))
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) >= 27:
                yield row


def _active(row):
    return not row[CLOSED] and row[STATUS] not in ("INACTIVE", "CLOSED") \
        and row[NATION] not in _NOT_UK


def _owners(cache, report):
    """Owner (headquarters) code to name, from the matching HQ report."""
    return {row[CODE]: row[NAME] for row in _report(cache, report)} if report else {}


def _make(name, title, report, kind, fields, hq_report=None, keep=None, category=None,
          what="practice", partnership=False):
    source = {
        "name": name, "title": title, "country": "GB", "url": REPORT_URL.format(report),
        "licence": LICENCE, "updated": "weekly", "fields": fields,
    }

    def rows(cache):
        owners = _owners(cache, hq_report)
        for row in _report(cache, report):
            if not _active(row) or (keep and not keep(row)):
                continue
            owner = owners.get(row[PARENT], "")
            is_corp = corporate_name(row[NAME]) or corporate_name(owner)
            if is_corp:
                why = f"{what} run by a company"
            elif partnership:
                why = f"{what} not shown to be incorporated: usually a partnership, post only"
            else:
                why = f"{what} not shown to be incorporated: post only"
            can, why = rule("GB", is_corp, why)
            yield record(
                source, row[CODE], row[NAME], other_name=owner, kind=kind,
                category=category(row) if category else "",
                status=row[STATUS].lower() or "active",
                address=joined(row[4], row[5], row[6]), town=row[7], region=row[8],
                postcode=row[9], country="GB", phones=row[PHONE],
                registration_number=f"ODS {row[CODE]}", can_email=can, rule_reason=why)

    return types.SimpleNamespace(SOURCE=source, rows=rows)


SOURCES = [
    # Only the GP practice role (RO76): the report also lists out-of-hours,
    # prison, walk-in and other prescribing cost centres.
    _make("nhs-ods-gp-practices", "NHS ODS GP practices (England and Wales)", "epraccur",
          "GP practice", "practice name, address, phone",
          keep=lambda row: "RO76" in row[ROLE].split("|"), what="GP practice", partnership=True),
    _make("nhs-ods-dental-practices", "NHS ODS dental practices (England and Wales)", "egdpprac",
          "dental practice", "practice name, address", what="dental practice", partnership=True),
    _make("nhs-ods-pharmacies", "NHS ODS pharmacies and appliance contractors (England)",
          "edispensary", "pharmacy", "pharmacy name, owner, address, phone",
          hq_report="epharmacyhq", what="pharmacy",
          category=lambda row: "appliance contractor" if row[SUBTYPE] == "RO94" else "community pharmacy"),
    _make("nhs-ods-care-homes", "NHS ODS care homes (England and Wales)", "ecarehomesite",
          "care home", "care home name, provider, address", hq_report="ecarehomehq",
          what="care home", category=lambda row: row[NATION].title()),
    _make("nhs-ods-opticians", "NHS ODS optician sites (England)", "eoptsite", "optician",
          "optician name, owner, address", hq_report="eopthq", what="optician"),
]
