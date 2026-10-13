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
from collections import Counter
from datetime import date

from . import contacts, text
from .sources import FIELDS, catalogue, registry

# A shared email or website joins two records only when few records share
# it; an accountant's or agent's address used by hundreds of firms must not
# turn them into one organisation.
MAX_SHARED = 5


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


def group(rows):
    """Union-find over the keys: returns {record_id: group_id}."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    users = Counter()
    row_keys = []
    for row in rows:
        keys = _keys(row)
        row_keys.append((row["record_id"], keys))
        users.update(set(keys))
    for record_id, keys in row_keys:
        keys = [k for k in keys if k.startswith("n:") or users[k] <= MAX_SHARED]
        for key in keys:
            a, b = find(record_id), find("k:" + key)
            if a != b:
                parent[b] = a
    return {record_id: find(record_id) for record_id, _ in row_keys}


def _connect():
    try:
        import duckdb
    except ImportError as error:
        raise SystemExit("This step needs DuckDB: pip install duckdb") from error
    db = duckdb.connect()
    db.execute("SET preserve_insertion_order=false")
    return db


def combine(out, names):
    """Join the written sources into master.parquet and organisations.parquet."""
    db = _connect()
    files = [_source_path(out, n) for n in names if os.path.exists(_source_path(out, n))]
    listing = ", ".join("'" + f.replace("'", "''") + "'" for f in files)
    db.execute(f"""CREATE TABLE raw AS SELECT * FROM read_csv([{listing}], header=true,
                   all_varchar=true, union_by_name=true)""")
    columns = ", ".join(FIELDS)
    rows = (dict(zip(FIELDS, r)) for r in db.execute(f"SELECT {columns} FROM raw").fetchall())
    groups = group({k: (v or "") for k, v in r.items()} for r in rows)
    group_file = os.path.join(out, "groups.csv.part")
    with open(group_file, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["record_id", "group_id"])
        writer.writerows(groups.items())
    db.execute(f"""CREATE TABLE groups AS SELECT * FROM read_csv('{group_file}', header=true,
                   all_varchar=true)""")
    os.remove(group_file)
    db.execute("""CREATE TABLE master AS
                  SELECT r.*, g.group_id FROM raw r JOIN groups g USING (record_id)""")
    master = os.path.join(out, "master.parquet")
    db.execute(f"COPY master TO '{master}' (FORMAT parquet, COMPRESSION zstd)")
    organisations = os.path.join(out, "organisations.parquet")
    db.execute(f"""COPY (
        SELECT group_id,
               first(name ORDER BY length(emails) DESC) AS name,
               string_agg(DISTINCT kind, '; ') AS kind,
               string_agg(DISTINCT nullif(category, ''), '; ') AS category,
               string_agg(DISTINCT nullif(legal_form, ''), '; ') AS legal_form,
               first(nullif(address, '')) AS address, first(nullif(town, '')) AS town,
               first(nullif(region, '')) AS region, first(nullif(postcode, '')) AS postcode,
               first(country) AS country,
               string_agg(DISTINCT nullif(website, ''), '; ') AS website,
               {_merge('emails')} AS emails, {_merge('phones')} AS phones,
               {_merge('socials')} AS socials, {_merge('people')} AS people,
               -- One register calling it a company is enough; it is the
               -- legal form, not the register, that decides.
               CASE WHEN bool_or(can_email = 'can email') THEN 'can email'
                    ELSE first(can_email) END AS can_email,
               string_agg(DISTINCT source, '; ') AS sources,
               string_agg(record_id, '; ') AS record_ids,
               max(fetched) AS fetched
        FROM master GROUP BY group_id
    ) TO '{organisations}' (FORMAT parquet, COMPRESSION zstd)""")
    return db


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
    parser.add_argument("command", choices=["build", "combine", "summary", "export", "sources"])
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
        for name in args.only or names:
            print(f"Loading {name}…", flush=True)
            print(f"  {load_source(name, args.out, args.cache):,} records", flush=True)
    if args.command in ("build", "combine"):
        print("Joining the same organisation across sources…", flush=True)
        combine(args.out, names)
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
