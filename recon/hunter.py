"""Optional: ask Hunter (hunter.io) what it knows about a domain.

Switched off unless Edem supplies a key (RECON_HUNTER_KEY) and runs the emails
step with --hunter. Hunter is a paid service with a small free allowance, and
each domain looked up uses one search, so Recon only asks about businesses it
may email whose own website gave no address and no pattern.

Hunter's addresses come from its own crawl of the web, not from the business's
site, so they are marked as Hunter's and scored a little lower.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.hunter.io/v2/domain-search"


def key():
    return os.environ.get("RECON_HUNTER_KEY", "")


def _fetch(domain, api_key):
    query = urllib.parse.urlencode({"domain": domain, "api_key": api_key, "limit": 10})
    with urllib.request.urlopen(f"{API}?{query}", timeout=20) as response:
        return json.loads(response.read())


def summarise(reply):
    """What we keep: the pattern, plus each address with its type and name."""
    data = reply.get("data") or {}
    found = []
    for item in data.get("emails") or []:
        if not item.get("value"):
            continue
        found.append({
            "email": item["value"].lower(),
            "type": item.get("type") or "",
            "confidence": int(item.get("confidence") or 0),
            "first": item.get("first_name") or "",
            "last": item.get("last_name") or "",
        })
    return {"pattern": data.get("pattern") or "", "emails": found}


class Lookup:
    """One question per domain per run, remembered in a cache file."""

    def __init__(self, cache_path, api_key=None, fetch=_fetch):
        self.cache_path = cache_path
        self.api_key = key() if api_key is None else api_key
        self.fetch = fetch
        self.cache = {}
        self.asked = 0
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                        self.cache[row["domain"]] = row["found"]
                    except (json.JSONDecodeError, KeyError):
                        continue

    def __call__(self, domain):
        if domain in self.cache:
            return self.cache[domain]
        if not self.api_key:
            return None
        try:
            found = summarise(self.fetch(domain, self.api_key))
        except urllib.error.HTTPError as error:
            if error.code in (401, 403, 429):
                print(f"  Hunter stopped answering (HTTP {error.code}); carrying on without it")
                self.api_key = ""
            return None
        except (urllib.error.URLError, TimeoutError, ValueError):
            return None
        self.asked += 1
        self.cache[domain] = found
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        with open(self.cache_path, "a", encoding="utf-8") as log:
            log.write(json.dumps({"domain": domain, "found": found}) + "\n")
        return found
