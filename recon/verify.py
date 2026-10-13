"""Check each address before anything is sent, and score it.

Three levels, best available first:
1. Reacher (open source), if you run it yourself, for example
       docker run -p 8080:8080 reacherhq/backend:latest
   Recon only talks to it over the network, so its AGPL licence does not
   touch Recon's code.
2. Recon's own mailbox check (mailbox.py), with --smtp-from you@yourdomain.
3. Otherwise: does the domain take email at all (its mail records), and does
   the address look right.

Levels 1 and 2 need the mail port (25) open, which most home and cloud
connections block. This step can be run on its own, later, from a small
rented server; everything else runs anywhere.
"""

import json
import os
import re
import urllib.error
import urllib.request

from . import contacts, dns, finder, text
from .mailbox import Checker

REACHER = os.environ.get("RECON_REACHER_URL", "http://localhost:8080")
GUESSES_TO_TRY = 3  # Other patterns tried for a named person, when a check can answer.


def check(email):
    """Ask Reacher: 'safe', 'risky', 'invalid' or 'unknown'."""
    if not contacts.valid_email(email):
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


def _reacher(domain, hosts, addresses):
    return {a: (check(a), "") for a in addresses}


def _ask(ask, mx, address, extra=()):
    """Check one address (and any extra ones on the same domain)."""
    domain = address.partition("@")[2]
    status, hosts = mx(domain)
    if status == dns.NO:
        return {a: "no mail server" for a in (address, *extra)}
    if not contacts.valid_email(address):
        return {address: "invalid"}
    if not ask:
        return {a: "looks right" for a in (address, *extra)}
    return {a: result for a, (result, _) in ask(domain, hosts, [address, *extra]).items()}


def fill(places, smtp_from=None, mx=None, ask=None):
    """Check every unchecked address and refresh each row's score.

    ask(domain, hosts, addresses) -> {address: (result, reason)} can be given
    directly (the tests do); otherwise Reacher, then --smtp-from, then none.
    """
    mx = mx or dns.Cache()
    if ask is None:
        if reacher_running():
            ask = _reacher
        elif smtp_from:
            ask = Checker(smtp_from).check
            print(f"  Checking mailboxes directly, as {smtp_from}")
        else:
            print(f"  Reacher is not running at {REACHER} and no --smtp-from was given; "
                  "checking that each domain takes email and each address looks right")
    checked = 0
    for place in places:
        site = text.domain(place["website"])
        if (place["email"] or place["contact_email"]) and site and not place["mail_server"]:
            place["mail_server"] = mx(site)[0]
        if place["email"] and not place["email_check"]:
            place["email_check"] = _ask(ask, mx, place["email"])[place["email"]]
            checked += 1
        if place["contact_email"] and not place["contact_email_check"]:
            _check_contact(place, ask, mx)
            checked += 1
        finder.rescore(place)
    return checked


def _check_contact(place, ask, mx):
    """Check a person's address. For a guess, also try the next likeliest
    patterns, and keep whichever the mail server confirms."""
    address = place["contact_email"]
    guessing = place["contact_email_basis"] in ("pattern-common", "pattern-shape")
    others = finder.alternatives(place)[:GUESSES_TO_TRY] if guessing and ask else []
    results = _ask(ask, mx, address, [a for _, a in others])
    place["contact_email_check"] = results.get(address, "unknown")
    if place["contact_email_check"] == "safe":
        return
    for pattern, other in others:
        if results.get(other) == "safe":
            place["contact_email"], place["contact_email_check"] = other, "safe"
            place["email_pattern"] = pattern
            return
