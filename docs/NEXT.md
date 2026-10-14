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
14. ~~**Dashboard and map**~~: done 13 October 2026. Front page dashboard (headline numbers, places, trades, who publishes their money, biggest sources) and one map of businesses near a postcode, ZIP code or town (UK trade lists with company size and net worth, or every register in the UK and US), with a download of the area.
15. **Fix the SALEANE category names** Overture renamed in 2026-09-23.1 (`spas` is now `spa`, `chiropractor` is now `chiropractic`, and so on). The target list editor marks each one.

16. ~~**Sectors**~~: done 14 October 2026 for the UK. Every organisation sorted into 17 sectors, then industries, then niches (`python -m recon.sectors build`); the map opens on every organisation and narrows from sector to niche.
17. **US sectors**: the same index for the United States. Left for another day (Edem, 14 October 2026). Build it a part file at a time with a memory cap, since the full UK run crashed the cloud workspace.
18. **Lists, today's calls and do-not-contact**: the small CRM in the plan at `/mnt/project-files/plans/recon-platform-plan.md`, shaped like the prototype Edem saw on 14 October 2026.
19. **Calling**: built into Recon on Twilio (browser calling, outcome buttons, call records), with TPS and CTPS screening first. Research and steps in `/mnt/project-files/plans/calling-platforms.md`. Waiting for Edem's go-ahead.
20. **Fit scores, email hand-off and signals**: the rest of the platform plan, then the link to 8BALL and ENDSTATE.

Things decided against, so they are not reopened without a reason: scraping Google Maps, booking platforms or professional registers; buying lists; selling Recon as a product before it has proved itself on SALEANE.
