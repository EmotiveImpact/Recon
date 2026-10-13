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
| The main email is one the business publishes on its own website | Those are addresses the business chose to make public for enquiries. |
| A named director's address may be worked out, for companies we may email only (decided 13 October 2026) | Emails to the owner get read; shared inboxes often don't. It is what Hunter and others do. It is kept in its own columns (`contact_*`), with a score and reason, never mixed up with published addresses. See RULES.md. |
| Build the email finders' free techniques ourselves rather than add their tools | ColdReach, MailScout and theHarvester all do some of this, but each brings dependencies and a young or quiet codebase. The ideas (patterns, catch-all detection, mail record checks) are a few hundred lines of standard library. |
| Reacher stays optional and outside Recon | It is AGPL-licensed. Recon only talks to it over the network if you run it, so its licence never touches Recon's code. Recon also has its own simpler mailbox check. |
| Hunter only as a plug-in, off by default | It costs money beyond a small free allowance. It only runs with `--hunter` and a key Edem supplies, and only for businesses whose own website gave nothing to go on. |
| Use the emails Overture lists, but only for businesses we may email (decided 13 October 2026) | Overture's 2026-09-23.1 release added `emails` and `socials`. In a Bath test, 114 of 216 places listed an email. They score 75, the same as OpenStreetMap; an address also found on the business's own site is upgraded to 90. Listed emails on `post only` rows are dropped at the emails step unless `--all-emails` is used. |
| Overture's category column changed in 2026-09-23.1 | `categories.primary/alternate` became `taxonomy.primary/alternates`. Recon checks which columns a release has, so older and newer releases both work. Permanently closed places are left out. |
| Mailbox checks are a separate step that can run elsewhere | They need port 25, which this cloud workspace and most home connections block. `recon verify --smtp-from` can run later on a small rented server. |
| Be polite when crawling: robots.txt, a few pages per site, one page a second per site, an honest user agent | We are guests on small businesses' websites. |
| Standard library only, apart from DuckDB for Overture | Easy to run anywhere, nothing to break. |
| Keep it in-house, not a product for sale (for now) | Apollo, Cognism, Hunter, Outscraper and Clay already sell this. Prove it on SALEANE first; a sector-specific version (for example, helping beauty suppliers find studios) could be looked at later with evidence. |
| Recon finds people; it does not send | Sending needs a separate domain, a suppression list and an unsubscribe flow. That is a deliberate next stage, see NEXT.md. |
| The repository is public, the data never is | `.gitignore` blocks `data/`, `out/` and every CSV, zip and parquet file. |

## How each step works, briefly

- **Places.** Overture is queried with DuckDB straight from its public S3 bucket (anonymously, so stray AWS keys on a computer don't get it refused), filtered by country box, country code, category and a confidence of at least 0.5. OpenStreetMap is queried through Overpass, one tag at a time to keep the shared server happy. Duplicates are joined on a loose name plus postcode, or name plus position within about 100 metres; Overture's record wins and OSM fills gaps.
- **Companies.** The Companies House file is filtered to active companies with the target's trade (SIC) codes, then matched by loose name. A match needs the same postcode district or town, or a unique name of at least two words, because a company's registered office is often its accountant's.
- **Rules.** See RULES.md.
- **People.** For companies we may email that have their own website, the Companies House API (free, needs a key) gives the active directors. One goes on the row.
- **Emails.** The homepage, then up to three same-site pages (contact pages first, then about and team pages; `/contact` if none is linked). Every address is kept in the cache, including ones hidden from robots by Cloudflare or written as "name [at] domain [dot] com". The best address for the row is one on the business's own domain, then a shared inbox name such as info@ or bookings@.
- **Patterns.** Personal addresses on the site are matched against the directors' names to learn the pattern (sarah@, sarah.jones@, sjones@ and so on). If no name matches, the shape of an address is a weaker hint (j.smith@ suggests f.last). With nothing at all, Recon borrows the pattern seen most often on other businesses' sites in the same run, and scores the guess low.
- **Confidence.** Every address gets a score from 0 to 100 and a sentence saying why. Published on its own site starts at 90; a director's address made from a matched pattern at 70; a borrowed guess at 30. A confirmed mailbox lifts it to 90 or more; a domain that cannot take mail, or a mailbox the server says does not exist, drops it to 0. 70 or more counts as ready.
- **Checks.** First, does the domain take email at all (its mail records; Recon asks DNS itself, falling back to DNS over HTTPS where ordinary DNS is blocked). Then, if Reacher is running or `--smtp-from` is given, does the mailbox exist. Recon asks about a made-up address first so a server that accepts everything ("catch-all") is not taken as proof, tries the next likeliest patterns for a guessed person, and waits at least ten seconds between conversations with Google or Microsoft.

## What has not been tried yet

The email finder (people, patterns, scores, mailbox checks) has offline tests only. Things to note on the first real run: how many companies have a director whose name matches a published address, how often a guess is confirmed, and how many domains are catch-all.


The tool was written in a cloud workspace that cannot reach Overture, OpenStreetMap or Companies House, so the offline tests pass but **no real run has happened yet**. The first real run should be on Edem's computer. Expect to tune the Overture category names with `recon categories` (Overture renames categories now and then) and the name matching once real numbers come back.
