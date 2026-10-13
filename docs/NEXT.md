# What to build next

One plan, combining the first real runs, the research into free data sources (the "Free business email sources for Recon" document) and the GitHub leads. Tick items off here as they land. The website (projects, target lists, runs and results in the browser) is built separately; target lists stay the same JSON files, and the new keys below are optional.

## Done

- ~~**First real run**~~ of `targets/saleane-uk.json`, 13 October 2026, in the cloud: 174,533 UK businesses, 20,702 may be emailed. Numbers in THINKING.md.
- ~~**Email finder**~~: patterns, named directors, mail record and mailbox checks, confidence scores, `recon find`, optional Hunter.
- ~~**Every contact detail**~~: all emails (personal ones labelled), phones (mobiles marked), social links, from Overture, OpenStreetMap and the websites.
- ~~**OpenStreetMap from the daily download**~~, and duplicates joined by place and name.
- ~~**Company matching that rarely guesses wrong**~~: rare shared words, real distances to registered offices, checked by hand on Brighton and Bath.
- ~~**Any kind of business**~~: trade words come from `recon/trades.json` and the target list, not the code.
- ~~**SALEANE's categories**~~ renamed to Overture's September 2026 names (spas alone was missing about 14,000 places).
- ~~**Open registers**~~: the CQC directory as a preset; any open CSV by naming its columns.
- ~~**Full free-mail and throwaway lists**~~.
- ~~**Master database**~~ of 62 open UK and US registers (companies, charities, students' unions, trade unions, schools, care, transport, non-profits, state licence files), joined and split by country. See MASTER.md.

## Next, in order

1. **Postal export.** Most businesses are "post only" (88% across the UK), so the post campaign is the bigger one. Lay out names and addresses for a mail merge or a postcard printer.
2. **Companies House API key** (free; Edem registers for one). It switches on named directors for the 20,702 companies, which is what makes a cold email land.
3. **Suppression list**: one shared file of businesses and addresses that asked not to be contacted, checked by every export. Needed before any sending.
4. **Mailbox checks from a small rented server** with port 25 open (a few pounds a month): run `recon verify --smtp-from` there, and record how many guessed addresses are confirmed.
5. **Second look at unmatched businesses whose website says "Ltd"**: 17% of Brighton homepages mention Ltd or Limited, and 4% give a company number. Matching those by the number on the site is near certain.
6. **More registers, one per trade as needed**: the Food Standards Agency's hygiene ratings are now in the master database; next, council special treatment licences for massage, nails and tattoo where a council publishes them openly.
7. **Check the categories of every business type** against the current Overture release, starting with the website's 31 ready-made types. The places step now names any category that found nothing, and `recon categories` finds the new names.
8. **Instagram handles** pulled out of the `socials` column, for direct messages and ad audiences.
9. **Scoring**: rank businesses by fit (own website, several staff, in a city we focus on).
10. **Names from the business's own site** (a "meet the team" page or its structured data) for companies whose directors don't match, and for US businesses.
11. **US target** for SALEANE, once the UK campaign is working.
12. **Phone screening** against the TPS and CTPS before any calling.
13. **Sending**, kept separate from finding and only with Edem's go-ahead: a sender on its own domain, unsubscribe handling, the suppression list, and a record of what was sent to whom.

## Measured and left for later

- **People Data Labs' free company list** (2.4 GB, CC BY 4.0): fills a website for about 6% of businesses without one, right about 9 times in 10. Worth adding only with a check that the suggested site mentions the business.
- **Common Crawl** for websites that fail: most failures are domains that no longer exist, which an archive cannot fix.

Things decided against, so they are not reopened without a reason: scraping Google Maps, booking platforms or the search pages of professional registers (official bulk downloads are allowed, see THINKING.md); buying lists; leaked or breached data; selling Recon as a product before it has proved itself on SALEANE.
