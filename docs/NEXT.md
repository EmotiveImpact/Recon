# What to build next

In rough order. Tick items off here as they land.

1. **First real run** of `targets/saleane-uk.json` on Edem's computer. Note the counts per sector, the Companies House match rate and the share of websites with an email in THINKING.md.
2. **Tune the categories** with `recon categories`, since Overture's names change between releases.
3. **Suppression list**: one shared file of businesses and addresses that asked not to be contacted, checked by every export.
4. **Postal export**: addresses laid out for a mail merge or a postcard printer, for the `post only` rows.
5. **US target** for SALEANE (`targets/saleane-us.json`), once the UK campaign is working.
6. **Instagram handles** from the map data's social links, for direct messages and ads audiences. The links are now collected in the `socials` column (Overture and OpenStreetMap); next is pulling out the Instagram handle on its own.
7. **Scoring**: rank businesses by fit (for example, has its own website, several staff, in a city we focus on).
8. **Sending**, kept separate from finding: a sender on its own domain, unsubscribe handling, the suppression list, and a record of what was sent to whom.
9. **Phone screening** against the TPS and CTPS before any calling.
10. ~~**Email finder**~~: done 13 October 2026. Patterns, named directors, mail record and mailbox checks, confidence scores, `recon find`, optional Hunter.
11. **Mailbox checks from a small server**: rent one with port 25 open, run `recon verify --smtp-from` there, and record how many guesses are confirmed.
12. **Names from the business's own site** (a "meet the team" page or its structured data) for companies whose directors don't match, and for US businesses, which have no Companies House.

13. ~~**Website**~~: done 13 October 2026. Projects, target list editor with ready-made business types, runs and a results browser (`python3 -m recon.server`). Searching near a postcode or town with a map added the same day.
14. **Fix the SALEANE category names** Overture renamed in 2026-09-23.1 (`spas` is now `spa`, `chiropractor` is now `chiropractic`, and so on). The target list editor marks each one.

Things decided against, so they are not reopened without a reason: scraping Google Maps, booking platforms or professional registers; buying lists; selling Recon as a product before it has proved itself on SALEANE.
