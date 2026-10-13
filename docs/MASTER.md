# The master database

One table of organisations in the UK and US, built from free open registers, so any project can pick its targets from it. It is a starting list: Recon's other steps (websites, emails, Companies House) then fill the gaps.

## What is in it

Every row is one entry from one register, in the same columns whatever the source:

| Column | What it holds |
|---|---|
| `name`, `other_name` | The name, and a trading or provider name if there is one |
| `kind` | The type of organisation in plain words: company, charity, students' union, trade union, school, care service, carrier and so on |
| `category` | The trade or activity, as the register gives it (for example a NAICS industry) |
| `legal_form` | Company, LLC, CIO, trust, partnership and so on, when the register says |
| `address`, `town`, `region`, `postcode`, `country` | Where it is (`GB` or `US`) |
| `website`, `emails`, `phones`, `socials`, `people` | Contact details; several are joined with "; " |
| `can_email`, `rule_reason` | "can email" or "post only", and the reason in a sentence |
| `source`, `licence`, `source_url`, `fetched` | Which register it came from, under what licence, and when |
| `group_id` | The same organisation found in several registers shares this |

`organisations.parquet` has one row per organisation, with the contacts from every register merged. `sources.csv` lists every register with its link, licence and counts.

## Who may be emailed

The rules in RULES.md, applied per register and per legal form:
- UK companies, LLPs, CIOs, charitable companies, councils, health boards, academy trusts, colleges and universities: can email.
- UK sole traders, partnerships, trusts, unincorporated charities and associations (most trade unions), childminders, and anyone not shown to be incorporated: post only.
- US organisations: can email under CAN-SPAM, except where the register's own terms forbid marketing to individuals (Washington state), where anyone not plainly incorporated is post only.
- When one register shows an organisation is a company, the merged organisation may be emailed.

## Registers left out on purpose

The ICO register of fee payers (its emails are named people, and its licence excludes personal data), the business rates valuation list (licensed for rating only), the Scottish charity register (bans direct marketing), anything scraped from Google Maps, Yelp or LinkedIn, breached data, and anything under a non-commercial licence. Web Data Commons is waiting on Edem's decision because it states no licence.

## Building it

    python -m recon.master sources                       # the registers it knows
    python -m recon.master build --out /mnt/project-files/master-db --cache data/master-cache
    python -m recon.master build --only charity-commission --out ...   # refresh one register
    python -m recon.master export --out ... --where "kind = 'students'' union'" --to su.csv
    python -m recon.master summary --out ...

Downloads are kept in the cache folder, so a rebuild only fetches what is new. Each register's loader lives in `recon/sources/`, one file per register (or a few small registers in one file); adding a register means adding a loader and naming it in `LOADERS`.

The built database holds contact details, so it never goes in this repository. It lives in the project's private files (`/mnt/project-files/master-db/`).
