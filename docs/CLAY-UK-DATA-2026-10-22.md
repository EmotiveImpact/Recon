# Recon: Clay-style enrichment and UK data integration brief

Research date: 22 October 2026. Status: proposal and source shortlist, not an implemented integration.

## Intended outcome

Extend Recon into a business research workspace: find UK businesses, resolve their company identity, identify relevant decision-makers, research the business, enrich missing fields through ordered providers, rank prospects and export an evidence-backed list for each project.

Keep the current business finder, geography and company matching. Add enrichment around them. Do not combine entire third-party applications into one codebase.

The user's request authorises researching commercial sources and reusable software. It does not authorise purchasing subscriptions, importing a vendor's complete personal dataset, publishing contact data or sending outreach.

## Verified repository position

- Repository: https://github.com/EmotiveImpact/Recon
- Main at inspection: bbc435513acef1cfb55c35e691c0bff61e330681. Main contains the initial Python finder; its README is not the full development state.
- PRs #2 through #6 remain open, including named-contact finding, the website, improved matching, master database and map dashboard.
- PR #7: https://github.com/EmotiveImpact/Recon/pull/7, branch integration/recon-2026-10-15, inspected head 5aed55fa5a813740f8bf7f88f460c04db207c806. Reports 177 Python tests and identity/count integration fixes, without private-data validation.
- PR #8: https://github.com/EmotiveImpact/Recon/pull/8, branch claude/integrate-recon-branches-ftplvm, inspected head 67508ee1d65f684dfd24cf2f1ad5d34fe9a4dc13. Reports 175 Python tests and fixes validated against private master data, including UK contact eligibility.
- These are separate integration attempts. Compare their actual changes and preserve both sets of useful fixes before choosing a development base. Neither is established as superseding the other.
- PR #5 reports 62 UK/US registers and an initial 19.5 million organisations with 2.36 million email-bearing records. These are author-reported totals, not independently reproduced here. PR #8 reports 11,500,283 UK organisations. Do not treat a register entry count as a count of unique active trading businesses.
- PR #8's NEXT.md says the private master requires rebuilding to apply stricter UK eligibility rules. Rebuild and regenerate sectors before relying on eligibility totals.

This research branch is based on main for an isolated documentation diff. It is not another integration attempt.

## Reusable software shortlist

| Component | Repository | Evidence and licence position | Proposed use |
|---|---|---|---|
| enrichment-kit | https://github.com/masteranime/enrichment-kit | MIT reported by GitHub and README. TypeScript library/CLI for multi-provider enrichment waterfalls. | Best first reference for an ordered provider engine. Inspect actual provider adapters and pin a revision before copying anything. |
| Crawl4AI | https://github.com/unclecode/crawl4ai | Apache 2.0 text with an appended public-use attribution requirement in LICENSE. | Optional separate worker for JavaScript-heavy company websites and structured extraction. Honour robots and Recon's crawl limits. |
| dlt | https://github.com/dlt-hub/dlt | Core library Apache 2.0. Some separately marketed dltHub capabilities have different terms. | Optional ingestion worker if the growing register catalogue outgrows current loaders. Not necessary for the first enrichment release. |
| OpenGTM | https://github.com/debpalash/OpenGTM | Advertised AGPL-3.0; workbooks, enrichment waterfalls, research, signals and integrations. | Evaluate workflow and data-model ideas. Do not copy AGPL code into Recon without an explicit licence decision. |
| Firecrawl | https://github.com/firecrawl/firecrawl | Core advertised AGPL-3.0; hosted service includes additional capabilities. | Alternative website extraction service to evaluate, not an additional mandatory crawler. |
| OpenKiln | https://github.com/OrbiSearch/openkiln | LICENSE is Elastic License 2.0 and restricts providing a substantial feature set as a hosted/managed service. Not a permissively licensed foundation. | Reference only pending a specific permitted deployment assessment. |
| Bricks | https://github.com/BraaMohammed/bricks | Claims open source, but GitHub returned no recognised licence and the inspected main tree contained no LICENSE/COPYING file. | UI/workflow reference; do not copy code without permission or a verified applicable licence. |
| OpenClay / Altclay | https://openclay.io/ and https://github.com/raghav3600/Altclay | Site claims open source. GitHub metadata returned no recognised licence. Reuse permission remains unverified. | Reference for prompt-based spreadsheet research, not cleared for code incorporation. |

This corrects the earlier assumption that every project advertising itself as an open-source Clay alternative is suitable for incorporation.

Existing Recon docs already discuss Splink, structured-data extraction, email validation and optional Reacher. Reassess gaps before adding overlapping dependencies.

The existing standard-library-plus-DuckDB rule remains in effect. Keep new external runtimes optional and separate, or obtain an explicit architecture decision before changing the core dependency policy. A process boundary alone is not a blanket exemption from licence obligations.

Project descriptions and licences were checked. These external applications were not installed, benchmarked or security-audited in this session.

## UK businesses and named people: separate the data layers

A registered company, a trading location, a director and a current marketing manager are different entities. Preserve their relationships rather than treating them as interchangeable.

### Free and open foundations

| Source | Access | Useful data | Limit |
|---|---|---|---|
| Companies House basic company data | Monthly CSV ZIP: https://download.companieshouse.gov.uk/en_output.html | Registered names, company numbers, legal status, registered address, SIC categories and incorporation information. | Companies covered by the register, not every sole trader or trading location. Basic file is not an email or employee directory. |
| Companies House public API | Free account/API key: https://developer.company-information.service.gov.uk/ | Company records, officers and other public company information. Officers endpoint: https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference/officers/list | A director is not necessarily the operational buyer. Do not import residential addresses or dates of birth for prospecting. |
| Overture Places | Bulk/query access: https://docs.overturemaps.org/guides/places/ | Business locations, categories, websites, phones and available email/social fields. | Uneven completeness; many locations per company. Already used by Recon. Preserve source attribution/licences. |
| People Data Labs free company dataset | Download entry point: https://www.peopledatalabs.com/company-dataset ; schema: https://docs.peopledatalabs.com/docs/free-company-dataset | Documentation describes over 22 million global company records, with domains, industry, location, size and company LinkedIn URLs. Filter UK records. | Company dataset, not a free person/email database. Recon's branch docs already discuss or load this source, so verify coverage before adding a duplicate. Check the downloaded release's terms and freshness. |
| Food Standards Agency FHRS | https://www.api.gov.uk/fsa/food-hygiene-ratings-scheme-fhrs/ | Food premises and ratings for hospitality targeting. | Not a named decision-maker database. Already represented in the master development line. |
| Charity Commission for England and Wales | Daily downloadable extracts: https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download | Organisation records and available public financial/contact fields. | England and Wales, not the whole UK. Do not assume every personal field can be used for marketing. Already represented in the master development line. |
| Business's own website | Small, respectful crawl of contact/about/team pages and structured data. | Published staff names, roles and business contact channels with direct evidence URLs. | Coverage varies. Retain evidence and dates; distinguish a named role from an AI inference. |

The latest Companies House basic snapshot shown during research was dated 1 October 2026, about 471 MB as one ZIP. No bulk database was downloaded in this session.

### Professional and contact data providers

| Provider | What to evaluate | Access/cost position checked on 22 October 2026 |
|---|---|---|
| People Data Labs | Person Search/Enrichment plus Company Search/Enrichment; structured identities, job roles and business contacts; bulk licence feeds available. | Person pricing page shows free testing up to 100 credits/month with contact details excluded; Pro advertised from US$98/month, starting at 350 credits; enterprise bulk feeds by quote. Confirm billing term and field bundles at checkout. https://www.peopledatalabs.com/pricing/person |
| Coresignal | Company, employee and job data, role/location/company search, API or bulk datasets. Strong candidate for LinkedIn-style professional structure. | Pricing table shows Mini US$49/month with 2,500 credits and higher tiers. A full company or employee record is listed at 20 credits; a core record at 10, so credits are not profiles. Contact enrichment and feature entitlement require checking. Bulk datasets are separately quoted. https://coresignal.com/pricing/ |
| Cognism | Named business contacts and company/contact enrichment. Candidate to benchmark specifically for UK coverage. | API access is entitlement-based. Quote and sample required for the intended fields/use case. https://developers.cognism.com/ ; https://www.cognism.com/pricing |
| Apollo | People/company search and enrichment as an optional provider. | API key, endpoint entitlements, credits and contract restrictions apply. Confirm integration and storage rights rather than assuming a seat subscription permits bulk reuse. https://www.apollo.io/developers |
| Hunter | Domain Search, Email Finder and Email Verifier. Particularly useful after Recon has identified a company domain and relevant person. | Free/paid allowances and API plans. Existing development docs already describe optional Hunter support. Hunter's data-plan documentation restricts replicating its core features as a standalone offering, relevant if Recon becomes a commercial product. https://hunter.io/api.html ; https://help.hunter.io/en/articles/12149400-hunter-api-for-data-plans |

These providers are candidates, not proof of current UK coverage, record accuracy or an automatic right to republish their data. Obtain a representative sample and applicable storage/display/export terms. Internal use and resale require different rights.

LinkedIn itself is not an openly downloadable professional database. Its official API permissions are limited; sales integrations require partner approval. A LinkedIn URL returned by a vendor does not make that vendor an authorised LinkedIn API partner. Official access overview: https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access

For Recon, compare PDL and Coresignal first, then add an email specialist only if it materially improves verified contact coverage. This is a recommendation for testing, not a purchase decision.

## Proposed Recon experience

1. Search a market: for example, UK hospitality businesses in a chosen area.
2. Save results into a project workbook, retaining the existing map.
3. Add columns such as company identity, owner/director, marketing contact, website summary, current recruitment, evidence and fit score.
4. Select rows and run enrichment. Show expected calls/spend, provider order and a hard budget cap.
5. Review results: source, retrieval date, observed versus inferred, match confidence and contact restrictions alongside each field.
6. Export suitable records. Keep outreach sending as a separate future feature.

## Implementation sequence

### R0: establish the integrated base

Compare #7 and #8, reconcile their identity/eligibility fixes and the later changes on #4/#5/#6. Run the resulting tests and rebuild private data. Do not merge either automatically. Capture the exact accepted base SHA before implementation.

### R1: evidence and provider contracts

Add separate organisation, location, person and field-evidence records. A proposed evidence record includes entity ID, field, value, source URL/provider ID, retrieval time, expiry, observed/inferred status, match confidence and applicable usage restrictions. Retain conflicting observations for review rather than silently overwriting identities.

Implement provider capability declarations and normalised results: found, not_found, ambiguous, retryable_error, blocked and budget_exhausted. Keep API keys server-side and out of exports/logs.

### R2: free-first named contact enrichment

Use Companies House for active directors and the company's own team pages for relevant operational roles. Keep director and employee roles separate. Stop on uncertain company identity. Verify whether the existing named-contact implementation already covers each step.

### R3: optional paid-provider waterfall

Use the local cache and permitted first-party sources, then one configured person-data provider, then optional email finding/verification. Stop once required fields and identity confidence are satisfied. Put spend limits on the whole run and each record; cache by provider, identity inputs and freshness policy.

No paid calls by default. Retry temporary failures with bounded backoff. A rerun should reuse fresh results and not charge for completed cells again. Never present guessed addresses or catch-all acceptance as confirmed delivery.

### R4: workbook and research columns

Add configurable enrichment columns, previews on a small sample, cancellation, progress, failure inspection and resume. Research answers require supporting URLs and should abstain when evidence is missing. Treat fetched webpages as untrusted data, never as instructions to execute tools.

### R5: measured provider selection

Use a private, representative UK sample, for example 100 to 200 organisations across salons, trades, hospitality, agencies and larger companies. Measure correct company match, correct current role, usable contact rate, stale/conflicting records, cost per usable contact and run time. Establish ground truth manually for a subset. Choose providers from measured uplift rather than advertised global record counts.

## Acceptance checks for the future build

- Disabled/unconfigured providers make zero external calls.
- The run cannot exceed its budget; retries and concurrent workers count towards it.
- Same-name businesses in different countries or conflicting company numbers remain separate.
- Named-person matches require adequate employer identity evidence.
- Public, inferred and verified contact values are visually distinct.
- Expired data and source deletion/objection requests can be removed from caches and future exports.
- Suppressed records remain suppressed after imports, merges and enrichment.
- Existing contact eligibility cannot be upgraded merely because a vendor found an email.
- No private lead data, API keys or third-party dataset extracts enter the public repository.
- Existing CLI, dashboard and geographic exports retain their behaviour.

UK named business contacts remain personal data. Use a documented lawful basis, appropriate transparency and objection handling; separate those requirements from the PECR rules for each channel/subscriber type. Official guidance: https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/business-to-business-marketing/

## Validation of this research change

Documentation only. The main-branch source at bbc435513acef1cfb55c35e691c0bff61e330681 was reconstructed locally for the repository-mandated offline check: 21 tests passed using python3 -m unittest discover -s tests -t . No production code changed. This does not revalidate the 175/177 test claims on the integration branches, the private master data or any external provider's runtime behaviour.
