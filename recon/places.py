"""The one record shape every step reads and writes, saved as CSV between steps."""

import csv
import os

FIELDS = [
    "key", "name", "sector", "category", "address", "town", "postcode",
    "lat", "lon", "website", "phone", "source", "source_id",
    "company_number", "company_name", "company_type",
    "email", "email_found_on", "email_check", "contact_rule",
]


def blank(**values):
    place = dict.fromkeys(FIELDS, "")
    place.update({k: ("" if v is None else str(v)) for k, v in values.items()})
    return place


def read(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return [blank(**row) for row in csv.DictReader(handle)]


def write(path, places):
    """Write atomically so an interrupted run never leaves half a file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temp = path + ".part"
    # utf-8-sig so Excel shows accents and £ correctly.
    with open(temp, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(places)
    os.replace(temp, path)
