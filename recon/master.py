"""The master database: every open register in recon/sources/ in one table.

    python -m recon.master build --out /mnt/project-files/master-db
    python -m recon.master build --only charity-commission --out ...
    python -m recon.master export --where "kind = 'students'' union'" --to su.csv
    python -m recon.master summary

Each source is written to <out>/sources/<name>.csv.gz, then joined into
<out>/master.parquet (one row per register entry, with `group_id` linking the
same organisation found in several registers) and <out>/organisations.parquet
(one row per organisation, contacts merged). <out>/sources.csv lists every
source with its licence, link and row counts. Never commit any of it: the
repository is public.
"""

import argparse
import csv
import gzip
import os
import re
from datetime import date

from . import contacts, text
from .sources import FIELDS, catalogue, registry

# A shared email or website joins two records only when few records share
# it; an accountant's or agent's address used by hundreds of firms must not
# turn them into one organisation.
MAX_SHARED = 5
# The same name at the same postcode, or the same company number, joins up to
# this many records; more means a shared building or a data fault.
MAX_SAME_NAME = 50


def _source_path(out, name):
    return os.path.join(out, "sources", f"{name}.csv.gz")


def load_source(name, out, cache):
    """Run one loader, writing its rows. Returns the row count."""
    module = registry()[name]
    path = _source_path(out, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    count = 0
    with gzip.open(path + ".part", "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, FIELDS)
        writer.writeheader()
        for row in module.rows(os.path.join(cache, name)):
            writer.writerow(row)
            count += 1
    os.replace(path + ".part", path)
    return count


# ---- matching the same organisation across registers -------------------

def _keys(row):
    """Strings that identify an organisation. Two records sharing any key
    are the same organisation."""
    keys = []
    if row.get("company_number"):
        keys.append("c:" + row["company_number"])
    name = text.name_key(row["name"])
    place = row["postcode"].replace(" ", "").upper()[:7] or row["town"].lower()
    if name and place:
        keys.append(f"n:{row['country']}:{name}:{place}")
    for email in filter(None, row["emails"].split("; ")):
        if contacts.email_label(email) != contacts.PERSONAL:
            keys.append("e:" + email)
        elif name:
            keys.append(f"pe:{email}:{name}")
    try:
        site = text.domain(row["website"]) if text.own_website(row["website"]) else ""
    except ValueError:  # A malformed web address, such as "http://[None]".
        site = ""
    if site:
        keys.append("w:" + site)
    return keys


def write_keys(rows, path):
    """Each record's keys, one (record_id, key) pair per line."""
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["record_id", "key"])
        for row in rows:
            writer.writerows((row["record_id"], key) for key in set(_keys(row)))


def group_in(db, keys_path, record_ids):
    """Joins records that share a key, in DuckDB so that millions of records
    fit in memory. Creates the table groups(record_id, group_id).

    Records and keys form a graph; each record's group is the smallest record
    number it can reach, found by passing the smallest number back and forth
    through the keys until nothing changes."""
    db.execute(f"""CREATE OR REPLACE TABLE ids AS
                   SELECT record_id, row_number() OVER () AS rid FROM {record_ids}""")
    db.execute(f"""CREATE OR REPLACE TABLE pairs AS
                   SELECT p.key, i.rid FROM read_csv('{keys_path}', header=true, all_varchar=true, delim=',', quote='"', escape='"') p
                   JOIN ids i USING (record_id)""")
    # A key shared by many records (an agent's email, a chain's website) says
    # nothing about which organisation a record is, so it joins nothing.
    db.execute(f"""CREATE OR REPLACE TABLE edges AS
                   SELECT key, rid FROM pairs WHERE key IN (
                       SELECT key FROM pairs GROUP BY key
                       HAVING count(*) > 1 AND count(*) <= CASE WHEN key LIKE 'n:%' OR key LIKE 'c:%'
                                                                THEN {MAX_SAME_NAME} ELSE {MAX_SHARED} END)""")
    db.execute("DROP TABLE pairs")
    db.execute("CREATE OR REPLACE TABLE comp AS SELECT DISTINCT rid, rid AS c FROM edges")
    for _ in range(100):
        db.execute("""CREATE OR REPLACE TABLE next AS
                      WITH k AS (SELECT e.key, min(c.c) AS c FROM edges e JOIN comp c USING (rid)
                                 GROUP BY e.key)
                      SELECT e.rid, min(k.c) AS c FROM edges e JOIN k USING (key) GROUP BY e.rid""")
        changed = db.execute("""SELECT count(*) FROM next n JOIN comp c USING (rid)
                                WHERE n.c <> c.c""").fetchone()[0]
        db.execute("DROP TABLE comp")
        db.execute("ALTER TABLE next RENAME TO comp")
        if not changed:
            break
    db.execute("""CREATE OR REPLACE TABLE groups AS
                  SELECT i.record_id, coalesce(g.record_id, i.record_id) AS group_id
                  FROM ids i LEFT JOIN comp c USING (rid) LEFT JOIN ids g ON g.rid = c.c""")
    for table in ("ids", "edges", "comp"):
        db.execute(f"DROP TABLE {table}")


def group(rows):
    """{record_id: group_id} for a few rows; used by the tests."""
    import tempfile
    rows = list(rows)
    db = _connect()
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "keys.csv")
        write_keys(rows, path)
        db.execute("CREATE TABLE r (record_id VARCHAR)")
        db.executemany("INSERT INTO r VALUES (?)", [(r["record_id"],) for r in rows])
        group_in(db, path, "r")
    return dict(db.execute("SELECT record_id, group_id FROM groups").fetchall())


def _connect(out=None):
    try:
        import duckdb
    except ImportError as error:
        raise SystemExit("This step needs DuckDB: pip install duckdb") from error
    db = duckdb.connect()
    db.execute("SET preserve_insertion_order=false")
    db.execute("SET enable_progress_bar=false")
    db.execute("SET memory_limit='8GB'")
    if out:  # Big joins spill to disk next to the database.
        temp = os.path.join(out, ".duckdb-temp")
        os.makedirs(temp, exist_ok=True)
        db.execute(f"SET temp_directory='{temp}'")
    return db


_ORGANISATION_COLUMNS = ("name, kind, category, legal_form, address, town, region, postcode, country, "
                        "website, emails, phones, socials, people, can_email")


def combine(out, names):
    """Join the written sources into master.parquet and organisations.parquet.
    Rows are streamed from the source files rather than held in memory, so
    tens of millions fit on a small machine."""
    db = _connect(out)
    files = [_source_path(out, n) for n in names if os.path.exists(_source_path(out, n))]
    keys_path = os.path.join(out, "keys.csv.part")

    def rows():
        for path in files:
            with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    yield {k: v or "" for k, v in row.items()}

    write_keys(rows(), keys_path)
    group_in(db, keys_path, f"(SELECT DISTINCT record_id FROM read_csv('{keys_path}', header=true, "
                            "all_varchar=true, delim=',', quote='\"', escape='\"'))")
    os.remove(keys_path)
    # Only records joined to another need a group; the rest are their own.
    db.execute("DELETE FROM groups WHERE record_id = group_id AND group_id NOT IN "
               "(SELECT group_id FROM groups WHERE record_id <> group_id)")
    listing = ", ".join("'" + f.replace("'", "''") + "'" for f in files)
    columns = ", ".join(f"r.{f}" for f in FIELDS)
    master = os.path.join(out, "master.parquet")
    db.execute(f"""COPY (
        SELECT {columns}, coalesce(g.group_id, r.record_id) AS group_id
        FROM read_csv([{listing}], header=true, all_varchar=true, delim=',', quote='"', escape='"',
                      union_by_name=true) r
        LEFT JOIN groups g USING (record_id)
    ) TO '{master}' (FORMAT parquet, COMPRESSION zstd)""")
    organisations = os.path.join(out, "organisations.parquet")
    db.execute(f"""COPY (
        SELECT group_id, {_ORGANISATION_COLUMNS}, source AS sources, record_id AS record_ids, fetched
        FROM '{master}' WHERE group_id NOT IN (SELECT group_id FROM groups)
        UNION ALL BY NAME
        SELECT group_id,
               first(name ORDER BY length(emails) DESC) AS name,
               string_agg(DISTINCT kind, '; ' ORDER BY kind) AS kind,
               string_agg(DISTINCT nullif(category, ''), '; ' ORDER BY nullif(category, '')) AS category,
               string_agg(DISTINCT nullif(legal_form, ''), '; ' ORDER BY nullif(legal_form, '')) AS legal_form,
               first(nullif(address, '')) AS address, first(nullif(town, '')) AS town,
               first(nullif(region, '')) AS region, first(nullif(postcode, '')) AS postcode,
               first(country) AS country,
               string_agg(DISTINCT nullif(website, ''), '; ' ORDER BY nullif(website, '')) AS website,
               {_merge('emails')} AS emails, {_merge('phones')} AS phones,
               {_merge('socials')} AS socials, {_merge('people')} AS people,
               -- One register calling it a company is enough; it is the
               -- legal form, not the register, that decides.
               CASE WHEN bool_or(can_email = 'can email') THEN 'can email'
                    ELSE first(can_email) END AS can_email,
               string_agg(DISTINCT source, '; ' ORDER BY source) AS sources,
               string_agg(record_id, '; ') AS record_ids,
               max(fetched) AS fetched
        FROM '{master}' WHERE group_id IN (SELECT group_id FROM groups) GROUP BY group_id
    ) TO '{organisations}' (FORMAT parquet, COMPRESSION zstd)""")
    return db


# Postcode areas by nation. Areas that straddle the border with Wales (CH,
# SY, HR, GL, LD) go to the nation most of their postcodes are in.
_SCOTLAND = ("AB", "DD", "DG", "EH", "FK", "G", "HS", "IV", "KA", "KW", "KY", "ML", "PA", "PH",
             "TD", "ZE")
_WALES = ("CF", "LD", "LL", "NP", "SA")


def _nation_sql(postcode):
    area = f"regexp_extract(upper({postcode}), '^([A-Z]{{1,2}})[0-9]', 1)"
    scotland = ", ".join(f"'{a}'" for a in _SCOTLAND)
    wales = ", ".join(f"'{a}'" for a in _WALES)
    return f"""CASE WHEN {area} = 'BT' THEN 'northern-ireland'
                    WHEN {area} IN ({scotland}) THEN 'scotland'
                    WHEN {area} IN ({wales}) THEN 'wales'
                    WHEN {area} IN ('GY', 'JE', 'IM') THEN 'crown-dependencies'
                    WHEN {area} <> '' THEN 'england' ELSE 'unknown' END"""


def segment(out):
    """Split the organisations by country: <out>/uk/<nation>.parquet and
    <out>/us/<state>.parquet, plus a counts file for each country."""
    db = _connect(out)
    organisations = os.path.join(out, "organisations.parquet")
    parts = {
        "uk": ("country = 'GB'", _nation_sql("postcode")),
        "us": ("country = 'US'", "CASE WHEN regexp_matches(upper(trim(region)), '^[A-Z]{2}$') "
                                 "THEN lower(trim(region)) ELSE 'unknown' END"),
        "other": ("country NOT IN ('GB', 'US')", "lower(coalesce(nullif(country, ''), 'unknown'))"),
    }
    for folder, (where, area) in parts.items():
        path = os.path.join(out, folder)
        os.makedirs(path, exist_ok=True)
        db.execute(f"CREATE OR REPLACE TABLE part AS SELECT *, {area} AS area FROM '{organisations}' "
                   f"WHERE {where}")
        for (name,) in db.execute("SELECT DISTINCT area FROM part").fetchall():
            target = os.path.join(path, f"{safe_name(name) or 'unknown'}.parquet")
            db.execute(f"COPY (SELECT * EXCLUDE (area) FROM part WHERE area = ?) TO '{target}' "
                       "(FORMAT parquet, COMPRESSION zstd)", [name])
        db.execute(f"""COPY (
            SELECT area, count(*) AS organisations,
                   count(*) FILTER (WHERE emails <> '') AS with_email,
                   count(*) FILTER (WHERE emails <> '' AND can_email = 'can email') AS may_email,
                   count(*) FILTER (WHERE phones <> '') AS with_phone,
                   count(*) FILTER (WHERE website <> '') AS with_website
            FROM part GROUP BY area ORDER BY organisations DESC
        ) TO '{os.path.join(path, "counts.csv")}' (HEADER)""")
    db.execute("DROP TABLE part")


def _merge(column):
    return (f"array_to_string(list_distinct(flatten(list(string_split(nullif({column}, ''), '; ')))), '; ')")


def summary(out):
    """Counts per source and overall, as rows of dicts."""
    db = _connect()
    master = os.path.join(out, "master.parquet")
    organisations = os.path.join(out, "organisations.parquet")
    per_source = db.execute(f"""
        SELECT source, count(*) AS records,
               count(*) FILTER (WHERE emails <> '') AS with_email,
               count(*) FILTER (WHERE emails <> '' AND can_email = 'can email') AS can_email_with_email,
               count(*) FILTER (WHERE phones <> '') AS with_phone,
               count(*) FILTER (WHERE website <> '') AS with_website
        FROM '{master}' GROUP BY source ORDER BY records DESC""").fetchall()
    total = db.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE emails <> ''),
               count(*) FILTER (WHERE emails <> '' AND can_email = 'can email'),
               count(*) FILTER (WHERE phones <> ''), count(*) FILTER (WHERE website <> ''),
               count(*) FILTER (WHERE sources LIKE '%;%')
        FROM '{organisations}'""").fetchone()
    return per_source, total


def write_catalogue(out, per_source):
    counts = {r[0]: r for r in per_source}
    path = os.path.join(out, "sources.csv")
    fields = ["name", "title", "country", "url", "licence", "updated", "fields",
              "records", "with_email", "can_email_with_email", "with_phone", "with_website", "built",
              "pending"]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for source in catalogue():
            numbers = counts.get(source["name"])
            if numbers:
                source.update(zip(fields[7:12], numbers[1:]))
                source["built"] = date.today().isoformat()
            writer.writerow(source)
    return path


def export(out, where, path):
    """Write organisations matching a SQL condition to a CSV, for example
    "kind = 'students'' union'" or "category ILIKE '%salon%' AND country = 'US'"."""
    db = _connect()
    organisations = os.path.join(out, "organisations.parquet")
    db.execute(f"COPY (SELECT * FROM '{organisations}' WHERE {where}) TO '{path}' (HEADER)")
    return db.execute(f"SELECT count(*) FROM '{organisations}' WHERE {where}").fetchone()[0]


def safe_name(value):
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="recon.master", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["build", "combine", "segment", "summary", "export",
                                            "sources"])
    parser.add_argument("--out", default=os.path.join("data", "master"),
                        help="folder for the database (keep it private)")
    parser.add_argument("--cache", default=os.path.join("data", "master-cache"),
                        help="folder for downloaded registers")
    parser.add_argument("--only", nargs="*", help="source names to (re)load; others are kept")
    parser.add_argument("--include-pending", action="store_true",
                        help="also load sources still waiting on a decision (see 'sources')")
    parser.add_argument("--where", help="for 'export': a condition, such as \"country = 'GB'\"")
    parser.add_argument("--to", help="for 'export': the CSV file to write")
    args = parser.parse_args(argv)

    loaders = registry()
    # A source marked "pending" waits on a decision about its licence or
    # Recon's rules, so it is left out unless asked for by name.
    names = [n for n, m in loaders.items() if args.include_pending or not m.SOURCE.get("pending")]
    if args.command == "sources":
        for source in catalogue():
            note = f"  (waiting: {source['pending']})" if source.get("pending") else ""
            print(f"{source['name']:<34} {source['country']}  {source['licence']}{note}")
        return 0
    if args.command == "build":
        failed = []
        for name in args.only or names:
            print(f"Loading {name}…", flush=True)
            try:
                print(f"  {load_source(name, args.out, args.cache):,} records", flush=True)
            except Exception as error:  # One broken register must not stop the rest.
                failed.append(name)
                print(f"  FAILED: {error!r}; its previous copy, if any, is kept", flush=True)
        if failed:
            print("Failed: " + ", ".join(failed))
    if args.command in ("build", "combine"):
        print("Joining the same organisation across sources…", flush=True)
        combine(args.out, names)
        print("Splitting by country…", flush=True)
        segment(args.out)
    if args.command == "segment":
        segment(args.out)
        return 0
    if args.command == "export":
        if not (args.where and args.to):
            parser.error("export needs --where and --to")
        print(f"{export(args.out, args.where, args.to):,} organisations written to {args.to}")
        return 0
    per_source, total = summary(args.out)
    print(f"{'source':<34}{'records':>11}{'email':>11}{'may email':>11}{'phone':>11}{'website':>11}")
    for row in per_source:
        print(f"{row[0]:<34}" + "".join(f"{n:>11,}" for n in row[1:]))
    print(f"Organisations after joining duplicates: {total[0]:,} ({total[1]:,} with email, "
          f"{total[2]:,} of those may be emailed, {total[3]:,} with phone, {total[4]:,} with "
          f"website, {total[5]:,} found in more than one source)")
    print("Source list:", write_catalogue(args.out, per_source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
