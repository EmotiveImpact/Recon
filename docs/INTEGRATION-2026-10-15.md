# Recon integration review, 15 October 2026

## Reviewed heads

| PR | Head reviewed | Dependency |
|---|---|---|
| #2 | 8b1254cb3eb0cb44f61be73541b514bc32ca611d | main |
| #3 | 8cbec2021a6adc4f186238fae62046b76e6a2713 | #2 |
| #4 | c3baad9465b5611f7c5c014afe2ef1dd79e00703 | #2 |
| #5 | 91905d1d0ccf83ec2fe310948d8fa1eebd975681 | earlier #4 head a09047f |
| #6 | 61404ab9507b52111a6fd8b9b33229f3c1de8c74 | #3 |

All five PRs were open. #6 has continued beyond its description: UK sector/industry/niche filters and Ask Recon are included. #5 missed #4's latest documentation decision about Common Crawl. This integration includes it too.

## Safest combination

The integration branch starts at #6, combines #5, then includes #4's latest head. It retains all five reviewed heads as ancestors. Only README.md and docs/NEXT.md conflicted; both lines' instructions are retained. Existing implementation branches and main are untouched. Review this combined branch against #6 to see the added matching, master loaders and integration fixes. Do not independently squash both lines and assume they are compatible afterwards.

## Confirmed defects fixed

- Master summary `may_email` counted only eligible organisations with an email. Sector and geographic queries counted all eligible organisations. Country summaries now use the same eligibility definition; `can_email_with_email` separately counts those with an address.
- Company number, email and website identity keys crossed country boundaries. Keys are now country-scoped.
- A shared website or email could join distinct company numbers, including through a third listing without a number. Such ambiguous connected groups are refused in full. This favours separate rows over wrongly transferring contacts or eligibility. It may reduce deduplication and counts must be rebuilt.
- Empty and US-only master folders could make the website's availability check raise while looking for UK files. Availability now checks areas without attempting a search.

- Installed packages previously omitted the new `recon.sources` subpackage and trade-word JSON. Package discovery and package data now include both.

## What actually connects

The master builder writes country parquet files and country counts. Directory reads these files directly; sectors builds its index from them. The integration fixture uses real master output, local synthetic postcode centres and both pipeline stages. It checks nearby trade searches, eligibility, sector totals, dashboard totals and exported rows.

There are two distinct data views:

- Every-register search and map use master country files. Coordinates represent postcode centres, not verified operating premises.
- Trade map and financial filters use `trades/*.csv` and optional `plumbers/uk-plumbers-with-money.csv`. Master build does not create these lists. Their generating sweep is not reproducible from a committed command here. A new installation needs private exports or a future reproducible trade export job. Financial values in master category text do not automatically become structured map financial columns.

The company-growth overlays expect a separate `companies-house/*.parquet` cache. The master Companies House loader reads a ZIP under its source cache and does not itself publish that dashboard cache. Missing overlays are optional, not proof of a broken master search.

The target editor already preserves unknown root and sector fields, including registers and trade words. Existing regression tests cover this. Matching regressions from #4 remain included.

## Ardent research

Use UK Trades and construction, then industry 43 and niche 43220 for plumbing/heating. Roofing, electrical work and other niches can be compared with the same geographic and contact filters. The plumbers target is included. Trade exports can provide premise coordinates and financial filters when supplied separately.

These are market-research starting points, not a verified list of Ardent buyers. Registered offices may be accountants' addresses. SIC 43220 combines plumbing, heating and air-conditioning. Net assets and staff are not turnover or budget. Multiple sector membership is intentional, so sector totals cannot be added into one market size. Compare samples by area and trade before relying on segment counts.

## Continuation and release gate

1. Review this branch's fixes and regression tests, keeping the original PRs open until a single integration decision is made. No merge or deployment is part of this work.
2. On a machine with the private source files, rebuild into a NEW folder. Never overwrite the only known-good database. Run `python -m recon.master combine --out data/master-db-review`, then `python -m recon.sectors build --master data/master-db-review --cache data/sectors-review --group uk`. First copy the source CSV.GZ inputs into the new folder's sources directory. `combine` also segments and rewrites summaries. For a fresh download use `build --out data/master-db-review` instead.
3. Keep the matching sector index paired with that exact database. The server currently reads its index from `data/sectors` under its root even with `--master`; use an isolated checkout/root for review and build its index there. Do not point the server at a new master while retaining an old index.
4. Reconcile pre/post counts by source, country and trade; inspect ambiguous identity groups and a sample of contact classifications. New identity guards can increase organisation counts. Previously built `counts.csv` needs regeneration for the corrected metric.
5. Supply or regenerate the private trade CSVs and optional company cache. Compare the same sampled company identities and contact rules in the trade and master views. They are independent snapshots and the code does not automatically reconcile them.
6. Start the local server with the reviewed database and index; check Dashboard, Find, Map, Ask, target editing and downloads in a real browser at desktop and phone sizes. Check actual private financial overlays and compare postcode-centre pins with premises.
7. Choose either one combined PR to main after review, or an explicitly ordered sequence #2, #4, #5 plus the UI line and integration fixes. Do not merge all existing stacked PRs unchanged in arbitrary order.

## Evidence and limits

Final combined suite: 177 tests passed, none skipped, with DuckDB 1.5.6. The wheel builds and includes recon.sources and trades.json. Frontend TypeScript check and production build passed; Vite reports a large bundle warning. Four new integration regressions cover real build-to-website data contracts, cross-country identity, conflicting legal-company identity and database availability.

No private database, 15 trade CSVs or full register downloads were available in this checkout. The reported 19.5 million organisations, 2.36 million emails and Austin timing have not been revalidated. No live-data browser verification or full-scale performance claim is made. Email presence and eligibility remain separate; confidence and published-versus-inferred labels belong to run exports and are not fully preserved as structured columns in the master view. Use original run exports for confidence-led selection.
