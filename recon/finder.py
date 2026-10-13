"""Put the best business address and, where allowed, one named person's
address on each row, with a confidence score and the reason for it.

The steps, in the order the paid email finders use them:
1. Addresses the business publishes on its own website (emails.py).
2. The pattern its addresses follow, learned from those addresses and the
   directors' names from Companies House (patterns.py, people.py).
3. A named person's address made from that pattern.
4. Optionally, Hunter's answer for the domain (hunter.py), only with a key.
5. Checks that the domain takes email and the mailbox exists (verify.py),
   which raise or lower the score.

Rules this keeps (docs/RULES.md): a person's address is only ever worked out
for a business we may email (a company or LLP in the UK), never for "post
only" rows, and only one person per business.
"""

import collections

from . import contacts, patterns, text
from .emails import best_email

CAN_EMAIL = "can email"
READY = 70  # A score at or above this counts as ready to use.
LISTINGS = ("openstreetmap", "overture")  # Map data that lists a business's email.

# Where an address came from: (starting score, reason).
BASIS = {
    "published": (90, "Published on the business's own website."),
    "published-other": (75, "Published on the business's own website, though not at its own "
                            "domain."),
    "openstreetmap": (75, "Listed for this business on OpenStreetMap."),
    "overture": (75, "Listed for this business in Overture Maps."),
    "hunter": (65, "Found by Hunter, not on the business's own website."),
    "pattern-matched": (70, "Made from {name}'s name using the pattern ({pattern}) that the "
                            "business's own published addresses follow."),
    "pattern-hunter": (60, "Made from {name}'s name using the pattern ({pattern}) Hunter reports "
                           "for this domain."),
    "pattern-shape": (50, "Made from {name}'s name; the business's published addresses look "
                          "like {pattern}."),
    "pattern-common": (30, "A guess from {name}'s name using a common pattern ({pattern}); "
                           "nothing on the website confirms it."),
}

CHECKS = {
    "safe": "The mail server confirmed the mailbox exists.",
    "invalid": "The mail server says this mailbox does not exist.",
    "risky": "A check marked it risky, usually because the mail server accepts any address.",
    "unknown": "The mailbox could not be confirmed.",
    "no mail server": "The domain cannot receive email.",
}


def score(basis, check="", mail_server="", name="", pattern=""):
    """(confidence from 0 to 100, reason in plain words) for one address."""
    if basis not in BASIS:
        return "", ""
    base, reason = BASIS[basis]
    reason = reason.format(name=name or "the director", pattern=pattern)
    if check in ("invalid", "no mail server") or mail_server == "no":
        return 0, reason + " " + CHECKS.get(check, CHECKS["no mail server"])
    if check == "safe":
        return min(max(base + 25, 90), 98), reason + " " + CHECKS["safe"]
    if check == "risky":
        return max(base - 10, 0), reason + " " + CHECKS["risky"]
    if basis.startswith("pattern") and mail_server == "yes":
        base += 5
        reason += " The domain does receive email."
    if check == "unknown":
        reason += " " + CHECKS["unknown"]
    return base, reason


def rescore(place):
    site = text.domain(place["website"])
    place["email_type"] = contacts.email_label(place["email"], site) if place["email"] else ""
    if place["email"]:
        contacts.add_emails(place, [place["email"]], site)
    place["email_confidence"], place["email_reason"] = score(
        place["email_basis"], place["email_check"], place["mail_server"])
    if place["email_type"] == contacts.PERSONAL and place["email_reason"]:
        place["email_reason"] += (" It is a personal address at "
                                  f"{place['email'].partition('@')[2]}.")
    if not place["contact_email"]:
        place["contact_email_confidence"] = place["contact_email_reason"] = ""
        return
    place["contact_email_confidence"], place["contact_email_reason"] = score(
        place["contact_email_basis"], place["contact_email_check"], place["mail_server"],
        place["contact_name"], place["email_pattern"])


def _own(address, site):
    host = address.partition("@")[2]
    return bool(site) and (host == site or host.endswith("." + site))


def _basis(place, site):
    """Where the row's main address came from, judged from email_found_on."""
    found_on = place["email_found_on"]
    host = place["email"].partition("@")[2]
    if found_on in ("openstreetmap", "overture"):
        return found_on
    if found_on == "hunter.io":
        return "hunter"
    if found_on.startswith("http"):
        return "published" if host == site or host.endswith("." + site) else "published-other"
    return ""


def _set(place, field, value):
    """Change an address, forgetting any check made on the old one."""
    if place[field] != value:
        place[field] = value
        place[f"{field}_check"] = ""


def alternatives(place):
    """Other addresses the named person might have, most likely first."""
    person = patterns.split_name(place["contact_name"])
    site = text.domain(place["website"])
    if not person or not site:
        return []
    return [(p, f"{patterns.make(p, *person)}@{site}") for p in patterns.usual_order()
            if f"{patterns.make(p, *person)}@{site}" != place["contact_email"]]


def _hunter_person(found, person):
    for item in (found or {}).get("emails", []):
        if (patterns.plain(item["first"]), patterns.plain(item["last"])) == person:
            return item["email"]
    return ""


def _contact(place, site, own, people, pattern, how, seen, found):
    """Choose one person and their address."""
    named = [(patterns.split_name(p["name"]), p) for p in people]
    named = [(n, p) for n, p in named if n]
    if not named:
        return
    # A person whose address the business itself publishes comes first.
    for address in own:
        for _, person in patterns.matches(address.partition("@")[0], [n for n, _ in named]):
            chosen = next(p for n, p in named if n == person)
            place["contact_name"], place["contact_role"] = chosen["name"], chosen["role"]
            _set(place, "contact_email", address)
            place["contact_email_basis"] = "published"
            return
    person, chosen = named[0]
    place["contact_name"], place["contact_role"] = chosen["name"], chosen["role"]
    hunted = _hunter_person(found, person)
    if hunted:
        _set(place, "contact_email", hunted)
        place["contact_email_basis"] = "hunter"
        return
    if not pattern:
        pattern, how = patterns.usual_order(seen)[0], "common"
        place["email_pattern"] = pattern
    _set(place, "contact_email", f"{patterns.make(pattern, *person)}@{site}")
    place["contact_email_basis"] = f"pattern-{how}"


def _clear_contact(place):
    for field in ("contact_name", "contact_role", "contact_email", "contact_email_check",
                  "contact_email_basis", "contact_email_confidence", "contact_email_reason"):
        place[field] = ""


def fill(places, found, people=None, hunter=None, everyone=True):
    """found: {site: {email: page}} from emails.load(); people: {company number:
    [{'name', 'role'}]} from people.load(); hunter: a hunter.Lookup or None."""
    people = people or {}

    def own_addresses(site):
        return [e for e in found.get(site, {})
                if e.endswith("@" + site) or e.endswith("." + site)]

    def names(place):
        if place["contact_rule"] != CAN_EMAIL:
            return []
        return [n for n in (patterns.split_name(p["name"])
                            for p in people.get(place["company_number"], [])) if n]

    # First, every pattern learned from a business's own addresses, so that
    # businesses with nothing to go on can borrow the most usual one.
    seen = collections.Counter()
    for place in places:
        site = text.domain(place["website"])
        if site in found:
            pattern, how = patterns.learn(own_addresses(site), names(place))
            if pattern:
                seen[pattern] += 1

    for place in places:
        site = text.domain(place["website"])
        may_email = place["contact_rule"] == CAN_EMAIL
        if not may_email:
            _clear_contact(place)
            if not everyone and place["email_found_on"] in LISTINGS:
                # Map data lists some emails; we keep none we may not use.
                place["email"] = place["email_found_on"] = place["email_check"] = ""
        if not text.own_website(place["website"]) or not (may_email or everyone):
            place["email_basis"] = _basis(place, site) if place["email"] else ""
            rescore(place)
            continue
        candidates = found.get(site, {})
        if candidates:
            on_site = best_email(list(candidates), site)
            listed = place["email"] if place["email_found_on"] in LISTINGS else ""
            if listed in candidates:
                place["email_found_on"] = candidates[listed]  # Also on its own site.
            elif not place["email"] or (listed and not _own(listed, site) and _own(on_site, site)):
                _set(place, "email", on_site)
                place["email_found_on"] = candidates[on_site]
        own = own_addresses(site)
        pattern, how = patterns.learn(own, names(place))
        hunted = None
        if hunter and may_email and not pattern and not any(
                not patterns.is_role(e.partition("@")[0]) for e in own):
            hunted = hunter(site)
            if hunted:
                pattern = patterns.from_hunter(hunted.get("pattern", ""))
                how = "hunter" if pattern else ""
                if not place["email"]:
                    generic = sorted((e for e in hunted["emails"] if e["type"] == "generic"),
                                     key=lambda e: -e["confidence"])
                    if generic:
                        _set(place, "email", generic[0]["email"])
                        place["email_found_on"] = "hunter.io"
        place["email_pattern"] = pattern
        place["email_basis"] = _basis(place, site) if place["email"] else ""
        if may_email:
            _contact(place, site, own, people.get(place["company_number"], []),
                     pattern, how, seen, hunted)
        rescore(place)


def lookup(domain, name, crawl, mx, ask=None):
    """One person at one business, as the paid finders do it: every likely
    address, best first, as [(address, confidence, reason)].

    crawl is emails.crawl; mx and ask are as in verify.fill.
    """
    from . import verify  # Here to avoid a loop: verify uses this module.

    site = text.domain(domain)
    person = patterns.split_name(name)
    if not person:
        raise ValueError("Give a first and last name, such as 'Sarah Jones'")
    found_on, _ = crawl(site)
    own = [e for e in found_on if e.endswith("@" + site)]
    pattern, how = patterns.learn(own, [person])
    guesses = []
    for address in own:
        if patterns.matches(address.partition("@")[0], [person]):
            guesses.append((address, "published", ""))
    if pattern:
        guesses.append((f"{patterns.make(pattern, *person)}@{site}", f"pattern-{how}", pattern))
    for other in patterns.usual_order():
        guesses.append((f"{patterns.make(other, *person)}@{site}", "pattern-common", other))
    seen, ranked = set(), []
    status = mx(site)[0]
    results = {}
    if ask and status != "no":
        results = verify._ask(ask, mx, guesses[0][0], [g[0] for g in guesses[1:4]])
    for rank, (address, basis, used) in enumerate(guesses):
        if address in seen:
            continue
        seen.add(address)
        check = results.get(address, "")
        confidence, reason = score(basis, check, status, name, used)
        if basis == "pattern-common" and check != "safe":
            confidence = max(confidence - rank, 0)  # Less usual patterns rank lower.
        ranked.append((address, confidence, reason))
    ranked.sort(key=lambda item: -item[1])
    shared = [e for e in found_on if patterns.is_role(e.partition("@")[0])]
    return ranked, shared
