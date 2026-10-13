# Recon

Recon is the in-house outreach finder for every project Edem builds. You give it a **target list** (which kinds of business, in which country), and it produces one spreadsheet of real businesses. Each row says whether the business may be emailed or should only get post, and carries the email from its own website where one is published.

It uses free, open data only. Nothing is bought and nothing is scraped from Google or booking sites.

> This repository is public. The lists Recon makes are private and are never committed: `data/` and `out/` are ignored by git.

## What it does

1. **Finds businesses** in [Overture Maps](https://overturemaps.org) (open data from Microsoft, Meta, Amazon and others) and [OpenStreetMap](https://www.openstreetmap.org), then joins duplicates.
2. **Marks UK companies** using the free [Companies House](https://download.companieshouse.gov.uk/en_output.html) monthly file.
3. **Applies the contact rules** for the country. In the UK, companies and LLPs may be emailed; sole traders and partnerships get post only. See [docs/RULES.md](docs/RULES.md).
4. **Gathers every contact detail**: all emails (personal Gmail and Hotmail ones labelled), all phone numbers (mobiles told apart from landlines) and all social links, for every business, so you can see the full picture. Who may be emailed is still decided by step 3.
5. **Names a person** at each company we may email: an active director from Companies House (needs a free API key).
6. **Finds emails** on every business's own website, politely and with a cache. It learns the pattern the business uses (sarah@, sarah.jones@ and so on) and works out the director's address from it.
7. **Checks emails**: that the domain takes email, then whether the mailbox exists, using [Reacher](https://github.com/reacherhq/check-if-email-exists) or Recon's own check if either is switched on. Every address gets a confidence score from 0 to 100 and a sentence saying why.
8. **Exports** `out/<target>-<date>.csv`, which opens in Excel or Google Sheets.

## The website

Recon has a website. Its front page, **Find businesses**, searches the master database (every open register in one place, built with `python3 -m recon.master`): type a trade such as plumbers, pick the UK, the US or elsewhere and an area, and filter to those you may email or that list an email, phone or website. Each row shows which registers it came from, and the whole result downloads as a spreadsheet. In the UK and the US you can also give a postcode, ZIP code or town and a distance ("plumbers within 5 miles of Cardiff"): the list is sorted nearest first, shows how far away each one is, and every match is pinned on a map, where clicking a pin shows its phone, email, website and whether you may email it. Positions come from GeoNames' free postcode file, downloaded once to `data/geo/`; the map is OpenStreetMap. The site finds the database in `data/master-db/`, in `RECON_MASTER`, or with `--master <folder>`.

It also has everything below: projects (SALEANE first), target lists you can build by picking kinds of business, a Run button, and a results table you can filter and export.

```bash
cd web && npm install && npm run build && cd ..   # once, and after changes to web/
python3 -m recon.server                           # then open http://localhost:8765
```

The server only listens on the computer it runs on, because the results hold contact details. Never put it on the open internet. Runs started from the site are the same command line steps below, logged in `data/<target>/runs/`. To work on the site itself, run `npm run dev` in `web/` alongside the server.

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
python3 -m recon people    targets/saleane-uk.json
python3 -m recon emails    targets/saleane-uk.json
python3 -m recon verify    targets/saleane-uk.json
python3 -m recon export    targets/saleane-uk.json
```

### The email finder

- **Named directors** need a free Companies House API key: register at https://developer.company-information.service.gov.uk/, create a "REST" key, then `export RECON_COMPANIES_HOUSE_KEY=...`. Without it, everything else still works.
- **Mailbox checks** need port 25 open, which most home and cloud connections block. Run the `verify` step on a small rented server with `--smtp-from you@yourdomain` (your real address, so mail servers know who is asking), or run Reacher there. Without either, `verify` still checks each domain takes email.
- **Hunter** (optional, paid beyond a small free allowance): `export RECON_HUNTER_KEY=...` and add `--hunter` to the `emails` step. It is only asked about businesses whose own website gave nothing to go on.
- **One person at one business**, like Hunter's email finder:

```bash
python3 -m recon find glowroom.co.uk --name "Sarah Jones"
```

This lists the likely addresses, best first, with a score and reason for each. In the UK, only email a person at a limited company or LLP.

To find Overture's exact category names for a new kind of business:

```bash
python3 -m recon categories targets/saleane-uk.json --words groom yoga pilates
```

## Adding a project

In the website: New project, then New target list, and pick kinds of business from Quick add. By hand: add `projects/<name>.json` with a name and description, copy `targets/saleane-uk.json`, give it the project name and country, and list the sectors with their Overture categories, OpenStreetMap tags and (UK only) Companies House trade codes. Nothing else changes.

## The spreadsheet

| Column | Meaning |
|---|---|
| `name`, `sector`, `category` | The business and how we classified it |
| `address`, `town`, `postcode`, `lat`, `lon` | Where it is |
| `website` | From the map data; booking-platform and social links are left out |
| `phone`, `phone_type`, `mobile`, `landline`, `all_phones`, `mobile_only` | Every number from the map data and the website (tel: links), each labelled mobile, landline or non-geographic. `mobile_only` is "yes" when the only numbers are mobiles, often a sign of a sole trader. Screen against the TPS and CTPS before calling |
| `socials` | Every social link (Instagram, Facebook, TikTok and so on) from the map data and the website |
| `company_number`, `company_name`, `company_type`, `company_match` | Its Companies House record, when matched, and how the match was made |
| `contact_rule` | `can email`, `post only` or `check local rules` |
| `email`, `email_type`, `email_found_on`, `email_check` | The business's main email, its kind (shared inbox, named person, personal, other business domain), the page it was on, and the check result |
| `all_emails` | Every address found anywhere, each labelled the same way. Seeing an address is not permission to email it: `contact_rule` decides |
| `email_confidence`, `email_reason`, `email_basis` | A score from 0 to 100 (70 or more is ready), why, and where the address came from |
| `email_pattern`, `mail_server` | The pattern the business's addresses follow, and whether its domain takes email |
| `contact_name`, `contact_role` | One director, for companies we may email |
| `contact_email`, `contact_email_check`, `contact_email_confidence`, `contact_email_reason`, `contact_email_basis` | That person's address (published, or worked out from the pattern), its check, score and reason |
| `source` | `overture`, `osm` or both |

## Credits

Contains Overture Maps data (CDLA Permissive 2.0), © OpenStreetMap contributors (ODbL), and Companies House data (Open Government Licence). Keep these credits on anything shared outside the team.

## For the next agent

Read [docs/PURPOSE.md](docs/PURPOSE.md), [docs/HISTORY.md](docs/HISTORY.md), [docs/THINKING.md](docs/THINKING.md), [docs/RULES.md](docs/RULES.md) and [docs/NEXT.md](docs/NEXT.md), in that order. Run the tests with `python3 -m unittest discover -s tests -t .`; they need no internet.
