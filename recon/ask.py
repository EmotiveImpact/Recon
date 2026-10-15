"""Ask Recon: a question in plain words ("salons in Leeds I can email")
turned into a sector search, answered from the sector index.

No language model: the question is read with simple rules. A business word
("salons", "plumbers") picks a sector and, where it can, a niche; "in" or
"near" a place picks the area; "can email", "with an email" or "with a phone"
narrow it. The counts come from the sector index by postcode district, so an
answer takes a moment rather than a search of every register.
"""

import json
import math
import os
import re

from recon import sectors

UK_POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)(?:\s*\d[A-Z]{2})?\b", re.I)
PLACE = re.compile(r"\b(?:in|near|around|of)\s+([a-z][a-z' -]*?)(?=\s+(?:that|which|who|with|i|we|and|can|"
                   r"may|having|within)\b|[?.!,]|$)", re.I)
MILES = re.compile(r"\b(\d{1,3})\s*(?:mi|mile|miles)\b", re.I)
STOP = {"find", "show", "me", "all", "the", "a", "an", "any", "some", "list", "get", "who", "which", "that",
        "can", "could", "may", "email", "emailed", "emails", "phone", "phones", "call", "with", "have", "has",
        "near", "in", "around", "of", "and", "or", "i", "we", "to", "for", "how", "many", "are", "there",
        "businesses", "business", "companies", "company", "organisations", "organisation", "uk", "miles",
        "mile", "within", "number", "numbers", "contact", "details", "please", "what", "where", "best"}


# Words whose industry name is spelt differently ("dentists" are "dental practice").
SAME = {"dentist": "dental", "dentists": "dental", "solicitor": "legal", "solicitors": "legal",
        "lawyer": "legal", "lawyers": "legal", "accountant": "accounting", "accountants": "accounting",
        "vet": "veterinary", "vets": "veterinary", "hairdresser": "hairdressing", "hairdressers": "hairdressing",
        "builder": "buildings", "builders": "buildings", "electrician": "electrical",
        "electricians": "electrical", "cafe": "cafes", "cafes": "cafes", "pubs": "public houses"}


def stem(word):
    for end in ("ers", "ing", "er", "es", "s"):
        if word.endswith(end) and len(word) - len(end) >= 4:
            return word[: -len(end)]
    return word


def miles_between(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 3958.8 * 2 * math.asin(math.sqrt(a))


class Ask:
    def __init__(self, index, locate):
        """index: a sectors.Sectors; locate(place) -> (lat, lon, label) or raises."""
        self.index = index
        self.locate = locate

    def _codes(self):
        try:
            with open(os.path.join(self.index.cache, "uk-codes.json"), encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return {}

    def understand(self, text):
        """What the question asks for, as a sector query plus a place."""
        said = " ".join((text or "").split())
        low = said.lower()
        query, notes = {"group": ["uk"]}, []
        if re.search(r"\b(can|may|allowed to|ok to)\s+(be\s+)?email", low):
            query["rule"] = ["can email"]
        has = []
        if re.search(r"\b(with|have|has|having)\s+(an?\s+)?email", low):
            has.append("email")
        if re.search(r"\b(with|have|has|having)\s+(a\s+)?(phone|number)|\bto call\b|\bcall\b", low):
            has.append("phone")
        if has:
            query["has"] = has

        place, miles = None, 5
        found = MILES.search(low)
        if found:
            miles = max(1, min(100, int(found.group(1))))
        rest = low
        code = UK_POSTCODE.search(said)
        if code:
            place = code.group(0).upper()
            rest = rest.replace(code.group(0).lower(), " ")
        else:
            found = PLACE.search(said)
            if found:
                place = found.group(1).strip()
                rest = rest.replace(found.group(0).lower(), " ")

        words = [w for w in re.findall(r"[a-z']+", rest) if w not in STOP]
        phrase = " ".join(words)
        # A word other registers use ("hair salon", "plumber"), longest first.
        best = None
        for slug, name, _, known in sectors.SECTORS:
            for word in known:
                if re.search(rf"\b{re.escape(word)}(s|es)?\b", phrase) and (not best or len(word) > len(best[1])):
                    best = (slug, word)
            if re.search(rf"\b{re.escape(slug)}\b", phrase) or name.lower() in phrase:
                best = best or (slug, None)
        if best:
            query["sector"] = [best[0]]
            if best[1]:
                query["niche_word"] = [best[1]]
        # An industry code name ("plumbing", "roofing", "hairdressing").
        codes = self._codes()
        matches = []
        for word in words:
            root = SAME.get(word) or stem(word)
            if len(root) < 4:
                continue
            matches += [(c, n) for c, n in codes.items() if re.search(rf"\b{re.escape(root)}", n.lower())]
        if matches:
            sector_of_code = {}
            for code_, _ in matches:
                for slug, _, prefixes, _ in sectors.SECTORS:
                    if any(code_.startswith(p) for p in prefixes):
                        sector_of_code[code_] = slug
                        break
            if not best:
                slugs = {sector_of_code.get(c) for c, _ in matches} - {None}
                if len(slugs) == 1:
                    query["sector"] = [slugs.pop()]
            in_sector = [(c, n) for c, n in matches if sector_of_code.get(c) in query.get("sector", [None])]
            if len(in_sector) == 1:
                query["niche"] = [in_sector[0][0]]
                query["niche_name"] = [in_sector[0][1]]
            else:
                notes = [n for _, n in (in_sector or matches)[:4]]
        return query, place, miles, notes

    def answer(self, text):
        query, place, miles, notes = self.understand(text)
        if not self.index.available("uk"):
            return {"answer": "The sector index isn't built on this computer yet, so I can't count anything.",
                    "understood": {}}
        heat_query = {k: v for k, v in query.items() if k in ("sector", "niche", "rule", "has")}
        # A register word ("hair salon") is added beside the industry code, so
        # listings without codes count too; dropped if no listing uses it.
        word = (query.get("niche_word") or [None])[0]
        if word:
            tried = self.index.heat("uk", {**heat_query, "niche": [word]})
            if tried.get("districts"):
                heat_query["niche"] = heat_query.get("niche", []) + [word]
        districts = self.index.heat("uk", heat_query).get("districts", [])

        where = None
        if place:
            try:
                lat, lon, label = self.locate(place)
                where = {"lat": lat, "lon": lon, "label": label, "miles": miles}
                districts = [d for d in districts if miles_between(lat, lon, d["lat"], d["lon"]) <= miles]
            except (ValueError, LookupError):
                return {"answer": f"I couldn't find a place called \"{place}\". Try a town or a postcode such as LS1.",
                        "understood": self._understood(query, heat_query, None)}

        total = sum(d["count"] for d in districts)
        may = sum(d["may_email"] for d in districts)
        email = sum(d.get("with_email", 0) for d in districts)
        phone = sum(d.get("with_phone", 0) for d in districts)
        what = self._what(query, heat_query)
        area = f" within {miles} miles of {where['label']}" if where else " in the UK"
        lines = [f"I found {total:,} {what}{area}."]
        if total:
            ruled = "" if query.get("rule") else f"{may:,} are companies the rules let you email, "
            lines.append(f"{ruled}{email:,} have an email address on file and {phone:,} have a phone number.")
            top = sorted(districts, key=lambda d: -d["count"])[:5]
            if len(top) > 1:
                lines.append("Busiest areas: " + ", ".join(f"{d['district']} ({d['count']:,})" for d in top) + ".")
        if notes:
            lines.append("You could narrow it to: " + "; ".join(notes) + ".")
        if not query.get("sector") and not query.get("niche"):
            lines.append("Tip: name a kind of business, for example \"hair salons in Leeds I can email\".")

        link = {"source": ["all"], "group": ["uk"], **{k: v for k, v in heat_query.items() if k == "sector"}}
        if len(heat_query.get("niche", [])) == 1:
            link["niche"] = heat_query["niche"]
        if where:
            link["near"], link["miles"] = [where["label"].split(",")[0]], [str(miles)]
        return {"answer": " ".join(lines[:1]) + ("\n" + "\n".join(lines[1:]) if len(lines) > 1 else ""),
                "figures": {"total": total, "may_email": may, "with_email": email, "with_phone": phone},
                "districts": sorted(districts, key=lambda d: -d["count"])[:8],
                "map": link, "understood": self._understood(query, heat_query, where)}

    def _what(self, query, heat_query):
        if query.get("niche_word") and query["niche_word"][0] in heat_query.get("niche", []):
            lead = query["niche_word"][0] + "s"
        elif query.get("niche_name"):
            lead = f"businesses listed as \"{query['niche_name'][0]}\""
        elif query.get("sector"):
            lead = f"organisations in {sectors.sector_of(query['sector'][0])[1]}"
        else:
            lead = "organisations"
        extra = []
        if "email" in query.get("has", []):
            extra.append("with an email")
        if "phone" in query.get("has", []):
            extra.append("with a phone")
        if query.get("rule"):
            extra.append("that may be emailed")
        return " ".join([lead] + extra)

    def _understood(self, query, heat_query, where):
        sector = (query.get("sector") or [None])[0]
        return {"sector": sectors.sector_of(sector)[1] if sector else None,
                "niche": (query.get("niche_name") or heat_query.get("niche") or [None])[0],
                "place": where["label"] if where else None,
                "miles": where["miles"] if where else None,
                "rule": (query.get("rule") or [None])[0], "has": query.get("has", [])}
