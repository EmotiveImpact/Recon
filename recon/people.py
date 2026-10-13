"""Who runs each company, from Companies House's free public API.

Directors' names are public by law and published under the Open Government
Licence. Knowing one lets Recon work out a person's address from the pattern
the business uses (see patterns.py).

The API is free but needs a key: register at
https://developer.company-information.service.gov.uk/, create an application
with a "REST" key, then set RECON_COMPANIES_HOUSE_KEY. Without a key this step
is skipped and nothing else changes.

To collect as little as possible, Recon only looks up companies it may email
and that have their own website, keeps active directors who are people (not
other companies), and puts one name on each row.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request

from . import patterns, text

API = "https://api.company-information.service.gov.uk"
PAUSE = 0.6  # The API allows 600 requests every five minutes.


def _fetch(number, key):
    url = f"{API}/company/{number}/officers?items_per_page=50"
    auth = base64.b64encode(f"{key}:".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def directors(reply):
    """Active directors who are people, as {'name', 'role'} in the API's order."""
    found = []
    for officer in reply.get("items", []):
        role = officer.get("officer_role", "")
        if officer.get("resigned_on") or role.startswith("corporate"):
            continue
        if "director" not in role and "member" not in role:
            continue  # Secretaries and the like are not who we write to.
        if not patterns.split_name(officer.get("name", "")):
            continue
        last, _, rest = officer["name"].partition(",")
        name = f"{rest.strip().split()[0].title()} {last.strip().title()}" if rest.strip() \
            else officer["name"].title()
        found.append({"name": name, "role": "member" if "member" in role else "director"})
    return found


def _load_cache(path):
    cache = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    cache[row["company_number"]] = row["people"]
                except (json.JSONDecodeError, KeyError):
                    continue
    return cache


def load(cache_path):
    """Everyone already looked up: {company number: [people]}."""
    return _load_cache(cache_path)


def wanted(place):
    return bool(place["company_number"] and place["contact_rule"] == "can email"
                and text.own_website(place["website"]))


def fill(places, cache_path, key=None, fetch=_fetch):
    """Put one director's name on each company we may email. Returns how many
    companies were looked up, or None when there is no API key."""
    key = os.environ.get("RECON_COMPANIES_HOUSE_KEY", "") if key is None else key
    cache = _load_cache(cache_path)
    todo = sorted({p["company_number"] for p in places if wanted(p)} - set(cache))
    if todo and not key:
        return None
    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    with open(cache_path, "a", encoding="utf-8") as log:
        for count, number in enumerate(todo, 1):
            try:
                found = directors(fetch(number, key))
            except urllib.error.HTTPError as error:
                if error.code in (401, 403):
                    raise SystemExit("Companies House did not accept the API key "
                                     "(RECON_COMPANIES_HOUSE_KEY)")
                found = []  # 404: no officers listed.
            except (urllib.error.URLError, TimeoutError, ValueError):
                continue  # Try again next run.
            cache[number] = found
            log.write(json.dumps({"company_number": number, "people": found}) + "\n")
            log.flush()
            if count % 100 == 0:
                print(f"  {count} of {len(todo)} companies looked up")
            time.sleep(PAUSE)
    for place in places:
        people = cache.get(place["company_number"]) if wanted(place) else None
        if people and not place["contact_name"]:
            place["contact_name"] = people[0]["name"]
            place["contact_role"] = people[0]["role"]
    return len(todo)
