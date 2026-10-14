"""Sectors: one tree for every kind of organisation, so the map and search can
start broad ("Marketing, media and creative") and narrow down ("Agencies",
then "SEO agencies").

Three levels:
- sector: a plain-English group, defined by Companies House industry (SIC)
  code prefixes plus the words other registers use for the same thing
  ("hair salon", "charity", "care home");
- industry: the SIC division (two digits, "43 Specialised construction"),
  or "Other listings" for organisations known only by those words;
- niche: one five-digit SIC code ("43220 Plumbing, heat and air-conditioning
  installation"), or one of those words ("barber").

Every organisation in the master database carries its SIC codes in
`category` ("43910 - Roofing activities; ...") and its words in `kind`
("company; roofers"), so all three levels are worked out from those two
columns. An organisation can sit in more than one sector.

Counting the whole tree means reading every organisation once, so
`python -m recon.sectors build` writes a small index (one row per
organisation: its area, postcode district, codes, words and contact flags)
that the counts and the heat map read in a moment.
"""

import argparse
import glob
import json
import os
import re
import tempfile
import threading

SECTORS = [
    # slug, name, SIC prefixes, words other registers use
    ("trades", "Trades and construction",
     ["41", "42", "43", "4520", "95", "8121", "8122", "8129", "8130"],
     ["builders", "builder", "contractor", "plumber", "plumbers", "electrician", "electricians",
      "roofer", "roofers", "roofing", "garages", "garage", "automotive repair", "locksmith",
      "locksmiths", "gardener", "gardeners", "cleaners", "cleaning service", "painter",
      "decorator", "carpenter", "handyman", "hvac", "landscaping", "plasterer", "glazier",
      "appliance repair", "car wash", "tiler", "scaffolding"]),
    ("marketing", "Marketing, media and creative",
     ["58", "59", "60", "73", "741", "742", "743"],
     ["marketing agency", "advertising agency", "advertising", "media", "graphic designer",
      "photographer", "photography", "printing service", "web designer", "design agency",
      "public relations", "video production", "publisher", "radio station", "tv station"]),
    ("technology", "Technology and software",
     ["61", "62", "63"],
     ["software company", "it service", "computer service", "information technology company",
      "web hosting", "telecommunications", "internet service provider"]),
    ("professional", "Professional services",
     ["69", "70", "71", "72", "749", "78"],
     ["accountant", "lawyer", "solicitor", "law firm", "consultant", "professional service",
      "b2b business management service", "architect", "engineering service",
      "employment agency", "recruiter", "notary", "surveyor", "business consultant"]),
    ("finance", "Finance, insurance and property",
     ["64", "65", "66", "68"],
     ["financial service", "insurance agency", "insurance", "real estate agent", "estate agent",
      "mortgage broker", "bank", "credit union", "property management", "letting agent",
      "financial advisor", "accounting firm"]),
    ("beauty", "Beauty, wellness and fitness",
     ["9602", "9604", "9313"],
     ["beauty salon", "hair salon", "barber", "spa", "nail salon", "gym", "massage",
      "tanning salon", "tattoo", "yoga studio", "pilates studio", "fitness", "beauty",
      "health spa", "aesthetics", "personal trainer", "salon"]),
    ("health", "Health and care",
     ["86", "87", "88", "75"],
     ["care home", "pharmacy", "dentist", "doctor", "clinic", "hospital", "optician",
      "physiotherapist", "chiropractor", "veterinarian", "nursing home", "home care",
      "medical center", "gp surgery", "counselling", "therapist"]),
    ("education", "Education and childcare",
     ["85", "8891"],
     ["school", "elementary school", "primary school", "secondary school", "education",
      "nursery", "preschool", "university", "college", "tutor", "tutoring", "academy",
      "driving school", "language school", "childcare", "music school"]),
    ("hospitality", "Food, drink and hospitality",
     ["55", "56"],
     ["restaurant", "cafe", "pub", "bar", "hotel", "bed and breakfast", "coffee shop",
      "fast food restaurant", "bakery", "food business", "takeaway", "campground",
      "holiday rental home", "indian restaurant", "fish and chips restaurant",
      "pizza restaurant", "chinese restaurant", "caterer", "catering", "guest house", "inn"]),
    ("retail", "Shops and retail",
     ["47", "451", "453", "454"],
     ["convenience store", "clothing store", "grocery store", "flowers and gifts store",
      "furniture store", "shopping", "gas station", "auto dealer", "building supply store",
      "supermarket", "florist", "jewelry store", "shoe store", "hardware store",
      "electronics store", "gift shop", "bookstore", "pet store", "department store"]),
    ("manufacturing", "Manufacturing and wholesale",
     [f"{n:02d}" for n in range(10, 34)] + ["46"],
     ["manufacturer", "factory", "wholesaler", "wholesale", "brewery", "distillery", "printer"]),
    ("transport", "Transport and logistics",
     ["49", "50", "51", "52", "53"],
     ["haulier", "taxi", "courier", "removals", "moving company", "logistics", "freight",
      "bus company", "car rental", "coach company", "storage facility"]),
    ("leisure", "Arts, events and leisure",
     ["90", "91", "92", "931", "8230"],
     ["venue", "event planner", "event venue", "wedding venue", "sport league", "museum",
      "theatre", "music venue", "cinema", "art gallery", "sports club", "golf course",
      "bowling alley", "arts organisation", "entertainment"]),
    ("community", "Charities, unions and communities",
     ["94"],
     ["charity", "charity organization", "community interest company", "union", "trade union",
      "labor union", "students' union", "student union", "professional body",
      "professional association", "christian place of worship", "place of worship", "church",
      "mosque", "synagogue", "temple", "community center", "social or community service",
      "club", "association", "society", "youth organization", "non-profit"]),
    ("public", "Public sector",
     ["84"],
     ["council", "government office", "police", "fire station", "local government",
      "public service", "courthouse", "library"]),
    ("land", "Farming, energy and utilities",
     ["01", "02", "03", "05", "06", "07", "08", "09", "35", "36", "37", "38", "39"],
     ["farm", "farmer", "agriculture", "energy", "solar", "utility", "waste", "recycling",
      "water company"]),
    ("services", "Other business services",
     ["77", "79", "80", "82", "96"],
     ["travel agency", "security", "rental", "call centre", "funeral", "dry cleaner",
      "laundry", "pet groomer", "storage", "office services", "translation"]),
]
BY_SLUG = {s[0]: s for s in SECTORS}

DIVISIONS = {
    "01": "Farming", "02": "Forestry", "03": "Fishing", "05": "Coal mining",
    "06": "Oil and gas", "07": "Metal mining", "08": "Quarrying", "09": "Mining support",
    "10": "Food products", "11": "Drinks", "12": "Tobacco", "13": "Textiles", "14": "Clothing",
    "15": "Leather goods", "16": "Wood products", "17": "Paper", "18": "Printing",
    "19": "Fuel refining", "20": "Chemicals", "21": "Medicines", "22": "Rubber and plastics",
    "23": "Glass, stone and clay", "24": "Metals", "25": "Metal products",
    "26": "Electronics", "27": "Electrical equipment", "28": "Machinery",
    "29": "Motor vehicles", "30": "Other vehicles", "31": "Furniture",
    "32": "Other manufacturing", "33": "Machine repair and installation",
    "35": "Electricity and gas", "36": "Water supply", "37": "Sewerage",
    "38": "Waste and recycling", "39": "Clean-up services", "41": "Building",
    "42": "Civil engineering", "43": "Specialist trades", "45": "Motor trade",
    "46": "Wholesale", "47": "Shops", "49": "Road and rail", "50": "Water transport",
    "51": "Air transport", "52": "Warehousing", "53": "Post and couriers",
    "55": "Accommodation", "56": "Food and drink", "58": "Publishing",
    "59": "Film, video and music", "60": "Broadcasting", "61": "Telecoms",
    "62": "Software and IT", "63": "Information services", "64": "Banking and finance",
    "65": "Insurance and pensions", "66": "Financial support", "68": "Property",
    "69": "Legal and accounting", "70": "Management consultancy",
    "71": "Architecture and engineering", "72": "Research", "73": "Advertising and research",
    "74": "Design, photography and translation", "75": "Vets", "77": "Rental and leasing",
    "78": "Recruitment", "79": "Travel", "80": "Security", "81": "Cleaning and landscaping",
    "82": "Office support and events", "84": "Public administration", "85": "Education",
    "86": "Health", "87": "Residential care", "88": "Social work and childcare",
    "90": "Arts", "91": "Libraries and museums", "92": "Gambling",
    "93": "Sport and recreation", "94": "Membership organisations", "95": "Repairs",
    "96": "Personal services", "97": "Households as employers", "99": "International bodies",
}

SLUG = re.compile(r"^[a-z]{1,32}$")
CODE = re.compile(r"^\d{2}(\d{3})?$")
WORDS = re.compile(r"^[a-z0-9 '&,.()/-]{1,60}$")


def sector_of(slug):
    if not SLUG.match(slug or "") or slug not in BY_SLUG:
        raise ValueError("Unknown sector")
    return BY_SLUG[slug]


# SQL over the master database's own columns (category, kind) -------------------

def _code_sql(prefixes, column):
    return [f"regexp_matches({column}, '(^|; )({'|'.join(prefixes)})[0-9]*( - |;|$)')"]


def _word_sql(words, column):
    quoted = ", ".join("'" + w.replace("'", "''") + "'" for w in words)
    return [f"list_has_any(string_split(lower(coalesce({column}, '')), '; '), [{quoted}])"]


def clause(query, category="category", kind="kind"):
    """SQL limiting the rows to the chosen sector, industry and niche, or
    ("", []) when none is chosen. Values are checked against fixed shapes and
    the sector table, so they can sit in the SQL text."""
    slug = (query.get("sector") or [""])[0]
    industry = (query.get("industry") or [""])[0]
    niche = (query.get("niche") or [""])[0]
    parts = []
    if slug:
        _, _, prefixes, words = sector_of(slug)
        parts.append("(" + " OR ".join(_code_sql(prefixes, category) + _word_sql(words, kind)) + ")")
    if industry and industry != "other":
        if not CODE.match(industry) or len(industry) != 2:
            raise ValueError("Unknown industry")
        parts.append(_code_sql([industry], category)[0])
    if niche:
        if CODE.match(niche) and len(niche) == 5:
            parts.append(_code_sql([niche], category)[0])
        elif WORDS.match(niche.lower()):
            parts.append(_word_sql([niche.lower()], kind)[0])
        else:
            raise ValueError("Unknown niche")
    return " AND ".join(parts)


# The index ---------------------------------------------------------------------

def index_path(cache, group):
    return os.path.join(cache, f"{group}.parquet")


def build(master, cache, groups=("uk", "us"), geo="data/geo", db=None):
    """One small row per organisation, from the master database's area files,
    plus the middle of each postcode district and the name of each SIC code."""
    from recon import directory  # The area files and their parts folders.
    if db is None:
        import duckdb
        db = duckdb.connect()
        db.execute("SET enable_progress_bar = false")
        db.execute("SET preserve_insertion_order = false")
    os.makedirs(cache, exist_ok=True)
    finder = directory.Directory(master)
    for group in groups:
        files = finder.files(group)
        out = index_path(cache, group)
        temp = out + ".part"
        district = ("CASE WHEN length(pc) >= 5 THEN pc[:-4] END" if group == "uk"
                    else "CASE WHEN regexp_matches(pc, '^[0-9]{5}') THEN pc[:3] END")
        db.execute(f"""COPY (
            SELECT regexp_extract(filename, '([^/\\\\]+?)([/\\\\]part-[0-9]+)?\\.parquet$', 1) AS area,
                   {district} AS district,
                   regexp_extract_all(coalesce(category, ''), '(?:^|; )([0-9]{{5}}) - ', 1) AS codes,
                   list_filter(string_split(lower(coalesce(kind, '')), '; '),
                               k -> k NOT IN ('', 'company', 'place', 'business',
                                              'business (listing site)', 'llp')) AS words,
                   can_email = 'can email' AS may,
                   coalesce(emails, '') <> '' AS email,
                   coalesce(phones, '') <> '' AS phone
            FROM (SELECT *, upper(replace(coalesce(postcode, ''), ' ', '')) AS pc
                  FROM read_parquet(?, filename = true, union_by_name = true))
        ) TO '{temp}' (FORMAT parquet, COMPRESSION zstd)""", [files])
        os.replace(temp, out)
        names = dict(db.execute("""
            SELECT pair[:5], any_value(trim(pair[9:]))
            FROM (SELECT unnest(regexp_extract_all(category, '[0-9]{5} - [^;]+')) AS pair
                  FROM read_parquet(?, union_by_name = true) WHERE category LIKE '%_____ - %')
            GROUP BY 1""", [files]).fetchall())
        with open(os.path.join(cache, f"{group}-codes.json"), "w", encoding="utf-8") as handle:
            json.dump(names, handle, sort_keys=True)
        places = os.path.join(geo, f"{group}-postcodes.parquet")
        if os.path.exists(places):
            key = "code[:-4]" if group == "uk" else "code[:3]"
            db.execute(f"""COPY (SELECT {key} AS district, round(avg(lat), 4) AS lat,
                                        round(avg(lon), 4) AS lon
                                 FROM read_parquet(?) GROUP BY 1)
                           TO '{os.path.join(cache, f"{group}-districts.parquet")}' (FORMAT parquet)""",
                       [places])


class Sectors:
    """Counts for the sector tree and the heat map, from the index."""

    def __init__(self, cache):
        self.cache = cache
        self.lock = threading.Lock()
        self._db = None
        self._tree = {}

    def db(self):
        if self._db is None:
            import duckdb
            self._db = duckdb.connect()
            self._db.execute("SET enable_progress_bar = false")
        return self._db

    def warm(self):
        for group in ("uk", "us"):
            try:
                self.tree(group)
            except Exception:  # Only a head start: any problem shows on first use.
                pass

    def available(self, group):
        return bool(self.cache) and os.path.exists(index_path(self.cache, group))

    def _source(self, group):
        return f"read_parquet('{index_path(self.cache, group)}')"

    def _match(self, query):
        """The sector filter over the index's codes and words lists."""
        parts = []
        slug = (query.get("sector") or [""])[0]
        industry = (query.get("industry") or [""])[0]
        niche = (query.get("niche") or [""])[0]
        if slug:
            _, _, prefixes, words = sector_of(slug)
            pattern = "^(" + "|".join(prefixes) + ")"
            quoted = ", ".join("'" + w.replace("'", "''") + "'" for w in words)
            parts.append(f"(len(list_filter(codes, c -> regexp_matches(c, '{pattern}'))) > 0 "
                         f"OR list_has_any(words, [{quoted}]))")
        if industry == "other":
            parts.append("len(codes) = 0")
        elif industry:
            if not CODE.match(industry) or len(industry) != 2:
                raise ValueError("Unknown industry")
            parts.append(f"len(list_filter(codes, c -> c[:2] = '{industry}')) > 0")
        if niche:
            if CODE.match(niche) and len(niche) == 5:
                parts.append(f"list_contains(codes, '{niche}')")
            elif WORDS.match(niche.lower()):
                parts.append("list_contains(words, '" + niche.lower().replace("'", "''") + "')")
            else:
                raise ValueError("Unknown niche")
        rule = (query.get("rule") or [""])[0]
        if rule == "can email":
            parts.append("may")
        elif rule == "post only":
            parts.append("NOT may")
        has = set(query.get("has", []))
        if "email" in has:
            parts.append("email")
        if "phone" in has:
            parts.append("phone")
        return (" WHERE " + " AND ".join(parts)) if parts else ""

    def tree(self, group):
        """Every sector with its count; within each, its industries; within
        each industry, its biggest niches. Cached: it reads every row."""
        if group in self._tree:
            return self._tree[group]
        if not self.available(group):
            return {"available": False}
        try:
            with open(os.path.join(self.cache, f"{group}-codes.json"), encoding="utf-8") as handle:
                names = json.load(handle)
        except (OSError, ValueError):
            names = {}
        source = self._source(group)
        result = []
        with self.lock:
            db = self.db()
            total = db.execute(f"SELECT count(*) FROM {source}").fetchone()[0]
            for slug, name, prefixes, words in SECTORS:
                where = self._match({"sector": [slug]})
                count, may = db.execute(f"SELECT count(*), count(*) FILTER (may) FROM {source}{where}").fetchone()
                pattern = "^(" + "|".join(prefixes) + ")"
                codes = db.execute(f"""
                    SELECT c, count(*) FROM (SELECT unnest(list_filter(codes, c -> regexp_matches(c, '{pattern}'))) AS c
                                             FROM {source}{where})
                    GROUP BY 1 ORDER BY 2 DESC""").fetchall()
                quoted = ", ".join("'" + w.replace("'", "''") + "'" for w in words)
                kinds = db.execute(f"""
                    SELECT w, count(*) FROM (SELECT unnest(list_filter(words, w -> list_contains([{quoted}], w))) AS w
                                             FROM {source}{where} AND len(codes) = 0)
                    GROUP BY 1 ORDER BY 2 DESC LIMIT 30""").fetchall()
                industries = {}
                for code, n in codes:
                    division = code[:2]
                    entry = industries.setdefault(division, {
                        "industry": division, "name": DIVISIONS.get(division, division),
                        "count": 0, "niches": []})
                    entry["count"] += n
                    entry["niches"].append({"niche": code, "name": names.get(code, code), "count": n})
                listed = sorted(industries.values(), key=lambda i: -i["count"])
                if kinds:
                    listed.append({"industry": "other", "name": "Other listings",
                                   "count": sum(n for _, n in kinds),
                                   "niches": [{"niche": w, "name": w.capitalize(), "count": n} for w, n in kinds]})
                for entry in listed:
                    entry["niches"] = entry["niches"][:40]
                result.append({"sector": slug, "name": name, "count": count, "may_email": may,
                               "industries": listed})
        tree = {"available": True, "total": total, "sectors": result}
        self._tree[group] = tree
        return tree

    def heat(self, group, query):
        """Postcode districts (UK) or three-digit ZIP areas (US) for the chosen
        sector, each placed at the middle of its postcodes."""
        centres = os.path.join(self.cache, f"{group}-districts.parquet")
        if not self.available(group) or not os.path.exists(centres):
            return {"available": False}
        where = self._match(query)
        where += (" AND " if where else " WHERE ") + "district IS NOT NULL"
        with self.lock:
            rows = self.db().execute(f"""
                WITH found AS (SELECT district, count(*) AS n, count(*) FILTER (may) AS m,
                                      count(*) FILTER (email) AS e, count(*) FILTER (phone) AS p
                               FROM {self._source(group)}{where} GROUP BY 1)
                SELECT district, lat, lon, n, m, e, p
                FROM found JOIN read_parquet(?) USING (district)
                ORDER BY n DESC""", [centres]).fetchall()
        return {"available": True,
                "districts": [{"district": d, "lat": y, "lon": x, "count": n, "may_email": m,
                               "with_email": e, "with_phone": p}
                              for d, y, x, n, m, e, p in rows]}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m recon.sectors",
                                     description="Build the sector index the map and search count from.")
    parser.add_argument("command", choices=["build"])
    parser.add_argument("--master", default=os.environ.get("RECON_MASTER", "data/master-db"))
    parser.add_argument("--cache", default="data/sectors")
    parser.add_argument("--geo", default="data/geo", help="where the GeoNames postcode files are")
    parser.add_argument("--group", action="append", choices=["uk", "us"])
    args = parser.parse_args(argv)
    build(args.master, args.cache, tuple(args.group or ("uk", "us")), args.geo)
    print(f"Sector index written to {args.cache}")


if __name__ == "__main__":
    main()
