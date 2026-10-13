# Recon

Recon is the in-house outreach finder for every project Edem builds. You give it a **target list** (which kinds of business, in which country), and it produces one spreadsheet of real businesses. Each row says whether the business may be emailed or should only get post, and carries the email from its own website where one is published.

It uses free, open data only. Nothing is bought and nothing is scraped from Google or booking sites.

> This repository is public. The lists Recon makes are private and are never committed: `data/` and `out/` are ignored by git.

## What it does

1. **Finds businesses** in [Overture Maps](https://overturemaps.org) (open data from Microsoft, Meta, Amazon and others) and [OpenStreetMap](https://www.openstreetmap.org), then joins duplicates.
2. **Marks UK companies** using the free [Companies House](https://download.companieshouse.gov.uk/en_output.html) monthly file.
3. **Applies the contact rules** for the country. In the UK, companies and LLPs may be emailed; sole traders and partnerships get post only. See [docs/RULES.md](docs/RULES.md).
4. **Finds emails** on each business's own website, only for those we may email, politely and with a cache.
5. **Checks emails** with [Reacher](https://github.com/reacherhq/check-if-email-exists) if you run it, otherwise only checks they look right.
6. **Exports** `out/<target>-<date>.csv`, which opens in Excel or Google Sheets.

## Running it

```bash
python3 -m pip install duckdb        # needed for Overture Maps
# Download BasicCompanyDataAsOneFile from Companies House (about 470 MB, free)
python3 -m recon run targets/saleane-uk.json --companies-house BasicCompanyData-2026-10-01.zip
```

Each step can be run on its own, repeated or resumed:

```bash
python3 -m recon places    targets/saleane-uk.json
python3 -m recon companies targets/saleane-uk.json --companies-house BasicCompanyData.zip
python3 -m recon rules     targets/saleane-uk.json
python3 -m recon emails    targets/saleane-uk.json
python3 -m recon verify    targets/saleane-uk.json
python3 -m recon export    targets/saleane-uk.json
```

To find Overture's exact category names for a new kind of business:

```bash
python3 -m recon categories targets/saleane-uk.json --words groom yoga pilates
```

## Adding a project

Copy `targets/saleane-uk.json`, give it the project name and country, and list the sectors with their Overture categories, OpenStreetMap tags and (UK only) Companies House trade codes. Nothing else changes.

## The spreadsheet

| Column | Meaning |
|---|---|
| `name`, `sector`, `category` | The business and how we classified it |
| `address`, `town`, `postcode`, `lat`, `lon` | Where it is |
| `website`, `phone` | From the map data; booking-platform and social links are left out |
| `company_number`, `company_name`, `company_type` | Its Companies House record, when matched |
| `contact_rule` | `can email`, `post only` or `check local rules` |
| `email`, `email_found_on`, `email_check` | The published email, the page it was on, and the check result |
| `source` | `overture`, `osm` or both |

## Credits

Contains Overture Maps data (CDLA Permissive 2.0), © OpenStreetMap contributors (ODbL), and Companies House data (Open Government Licence). Keep these credits on anything shared outside the team.

## For the next agent

Read [docs/THINKING.md](docs/THINKING.md) first, then [docs/RULES.md](docs/RULES.md) and [docs/NEXT.md](docs/NEXT.md). Run the tests with `python3 -m unittest discover -s tests -t .`; they need no internet.
