"""Who we may contact, and how, under each country's marketing rules.

This is a cautious reading of the rules, not legal advice. When unsure, the
answer is "post only", which is always allowed for business-to-business letters.
See docs/RULES.md for the reasoning.
"""

from .companies_house import is_corporate

CAN_EMAIL = "can email"
POST_ONLY = "post only"
CHECK = "check local rules"


def contact_rule(place, country):
    if country == "GB":
        # PECR: companies and LLPs may be emailed with a clear opt-out;
        # sole traders and partnerships need consent first.
        return CAN_EMAIL if is_corporate(place["company_type"]) else POST_ONLY
    if country == "US":
        # CAN-SPAM: business email is allowed with an honest subject,
        # a working unsubscribe and a postal address.
        return CAN_EMAIL
    return CHECK


def apply(places, country):
    for place in places:
        place["contact_rule"] = contact_rule(place, country)
