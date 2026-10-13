"""Check each email is real before sending, using Reacher (open source).

Run Reacher yourself, for example:
    docker run -p 8080:8080 reacherhq/backend:latest
then `recon verify ...`. Without Reacher this step only checks the address
looks right. Many home internet providers block the port Reacher needs, so
run it on a small cloud server if every result comes back "unknown".
"""

import json
import os
import re
import urllib.error
import urllib.request

REACHER = os.environ.get("RECON_REACHER_URL", "http://localhost:8080")
_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,24}$", re.I)


def check(email):
    """'safe', 'risky', 'invalid' or 'unknown'."""
    if not _SHAPE.match(email):
        return "invalid"
    request = urllib.request.Request(
        f"{REACHER}/v0/check_email", data=json.dumps({"to_email": email}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read()).get("is_reachable", "unknown")
    except Exception:
        return "unknown"


def reacher_running():
    try:
        urllib.request.urlopen(REACHER, timeout=3)
        return True
    except urllib.error.HTTPError:
        return True  # It answered, even if not on this path.
    except Exception:
        return False


def fill(places):
    live = reacher_running()
    if not live:
        print(f"  Reacher is not running at {REACHER}; only checking each address's shape")
    checked = 0
    for place in places:
        if not place["email"] or place["email_check"]:
            continue
        place["email_check"] = check(place["email"]) if live else (
            "looks right" if _SHAPE.match(place["email"]) else "invalid")
        checked += 1
    return checked
