# Why Recon exists, and the thinking behind it

Written 13 October 2026 from the conversation with Edem that started it. Update this file whenever a decision changes.

## Where it came from

Recon started in SALEANE's "Elevator pitch" thread. SALEANE is an all-in-one app for salons, spas and studios (£59 a month per location). Working out its pitch led to three questions in turn:

1. **How big is the market?** About 325,000 businesses with staff across the UK and US that SALEANE could serve: beauty and wellness about 190,000, physio, chiro and osteo about 89,000, barbers and tattoo about 31,000, aesthetics and med spas about 16,600. Sources and the five-year projection are on the market page: https://claude.ai/artifact/PDMj4G6VyfxMKK85NYbp64
2. **How many could we realistically bring on?** With a strong campaign and a clear problem solved, about 150 UK locations in the first six months (60 floor, 300 stretch), then the US from month six. Studios rarely switch mid-year, and free move-ins take hands-on time.
3. **How do we reach them, for free?** That is what Recon does.

Edem then asked for it to live in its own repository and to serve **all** his projects, not just SALEANE. That is why target lists are files and nothing about salons is built into the code.

## Decisions so far

| Decision | Why |
|---|---|
| Open data only: Overture Maps, OpenStreetMap, Companies House | Free, legal to reuse, and covers every business type and country we care about. |
| Never scrape Google Maps, booking sites (Fresha, Treatwell, Booksy and so on) or professional registers (HCPC, GOsC, GCC) | Their terms forbid it, and harvesting from registers is a data protection risk. Overture gives much the same data openly. |
| Only look up emails for businesses we may email | Collecting addresses we cannot lawfully use is pointless and goes against data minimisation under UK GDPR. `--all-emails` exists for special cases. |
| When unsure, the answer is "post only" | A business we could not match to Companies House might be a sole trader. Post to businesses is always allowed, so this never puts us in the wrong. |
| Only emails the business publishes on its own website | Those are addresses the business chose to make public for enquiries. |
| Be polite when crawling: robots.txt, a few pages per site, one page a second per site, an honest user agent | We are guests on small businesses' websites. |
| Standard library only, apart from DuckDB for Overture | Easy to run anywhere, nothing to break. |
| Keep it in-house, not a product for sale (for now) | Apollo, Cognism, Hunter, Outscraper and Clay already sell this. Prove it on SALEANE first; a sector-specific version (for example, helping beauty suppliers find studios) could be looked at later with evidence. |
| Recon finds people; it does not send | Sending needs a separate domain, a suppression list and an unsubscribe flow. That is a deliberate next stage, see NEXT.md. |
| The repository is public, the data never is | `.gitignore` blocks `data/`, `out/` and every CSV, zip and parquet file. |

## How each step works, briefly

- **Places.** Overture is queried with DuckDB straight from its public S3 bucket, filtered by country box, country code, category and a confidence of at least 0.5. OpenStreetMap is queried through Overpass, one tag at a time to keep the shared server happy. Duplicates are joined on a loose name plus postcode, or name plus position within about 100 metres; Overture's record wins and OSM fills gaps.
- **Companies.** The Companies House file is filtered to active companies with the target's trade (SIC) codes, then matched by loose name. A match needs the same postcode district or town, or a unique name of at least two words, because a company's registered office is often its accountant's.
- **Rules.** See RULES.md.
- **Emails.** Homepage first; if there is no address on the business's own domain, up to three same-site pages that look like contact or about pages. The best address is one on the business's own domain, then a shared inbox name such as info@ or bookings@.
- **Checks.** Reacher, which you run yourself, says whether each mailbox exists.

## What has not been tried yet

The tool was written in a cloud workspace that cannot reach Overture, OpenStreetMap or Companies House, so the offline tests pass but **no real run has happened yet**. The first real run should be on Edem's computer. Expect to tune the Overture category names with `recon categories` (Overture renames categories now and then) and the name matching once real numbers come back.


## 22 October 2026: intelligence and enrichment direction

The owner requested combining the dataset and Clay-alternative research into Recon and asked what product is emerging. The proposed direction is a business intelligence workspace joining companies, locations, relevant people, contact routes and project-specific research with source evidence. See [the consolidated pack](../research/recon-intelligence-2026-10-22/README.md).

This expands the research and roadmap, not implemented runtime scope. Existing restrictions on private data in git, purchases, sending and core dependencies remain. Source and platform candidates are not automatically approved integrations. The pack records licence limits, overlap, source-code evidence pins and the #7/#8 integration prerequisite.

