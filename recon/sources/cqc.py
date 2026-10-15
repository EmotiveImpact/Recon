"""Care Quality Commission care directory (Open Government Licence).

Every registered location in England: care homes, home care, GP and dental
practices, clinics and hospitals, with phone, website and the provider's
legal name. Reuses the CQC preset in recon/registers.py, which finds the
newest monthly file on CQC's data page.
"""

import re

from .. import registers
from . import corporate_name, record, rule

PRESET = registers.PRESETS["cqc"]

SOURCE = {
    "name": "cqc-care-directory",
    "title": "CQC care directory (England)",
    "country": "GB",
    "url": PRESET["page"],
    "licence": "Open Government Licence v3.0 (Care Quality Commission)",
    "updated": "monthly",
    "fields": "location and provider name, service types, address, phone, website",
}

# Councils and NHS bodies are public bodies. A plain "trust" may be an
# unincorporated charity, so it does not count on its own.
_PUBLIC = re.compile(r"\b(nhs|council|borough|county council|city of|university)\b", re.I)

KINDS = (("dentist", "dental practice"), ("doctors/gps", "GP practice"), ("gp", "GP practice"),
         ("care home", "care home"),
         ("residential home", "care home"), ("nursing home", "care home"), ("homecare", "home care"), ("hospital", "hospital"),
         ("clinic", "clinic"))


def kind_of(services):
    lowered = (services or "").lower()
    for words, kind in KINDS:
        if words in lowered:
            return kind
    return "care service"


def corporate(provider):
    """A company, LLP, NHS body or council may be emailed; a named person or
    a partnership running a practice is post only."""
    return corporate_name(provider) or bool(_PUBLIC.search(provider or ""))


def rows(cache):
    columns = PRESET["columns"]
    path = registers._file(PRESET, cache)
    for row in registers._rows(path, columns):
        value = lambda field: (row.get(columns.get(field, ""), "") or "").strip()
        provider = value("legal_name")
        is_corp = corporate(provider)
        can, why = rule("GB", is_corp, "provider is a company, NHS body or council: a corporate body"
                        if is_corp else "provider not shown to be incorporated: post only")
        address = value("address")
        yield record(
            SOURCE, value("id") or f"{value('name')}|{value('postcode')}", value("name"),
            other_name=provider, kind=kind_of(value("kind")), category=value("kind"),
            address=address, town=address.split(",")[-1].strip() if address else "",
            postcode=value("postcode"), country="GB",
            website=registers._website(value("website")), phones=registers._phone(value("phone")),
            registration_number=f"CQC {value('id')}" if value("id") else "",
            can_email=can, rule_reason=why)
