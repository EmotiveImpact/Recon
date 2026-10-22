# Recon product requirements

Status: proposed product direction, 22 October 2026.

## Purpose and users

Give the owner one place to discover and understand potential customers for each business he builds. Initial projects include SALEANE, Ardent and Emotive Impact. The first user is the owner; later internal collaborators may follow. Prove usefulness before packaging Recon as a commercial service.

Example question: "Find UK hotel groups, identify relevant marketing contacts, research recent openings, show available contact routes and rank the strongest prospects for Emotive Impact."

## The complete-picture principle

A useful profile joins six layers without pretending missing information exists:

| Layer | Questions answered | Likely source |
|---|---|---|
| Legal organisation | Who is the registered entity and is it active? | Companies House |
| Trading business and locations | Where does it operate and under which name? | Existing Recon registers, Overture, OSM |
| Company description | What does it do, how large is it, which market? | PDL, BigPicture, website evidence |
| People and roles | Who directs it and who handles the relevant function? | Officers API, team pages, optional professional-data providers |
| Contact routes | Which public inbox, main phone, named work email or direct number is available? | Websites, available Overture fields, optional contact providers |
| Current signals and project fit | Why approach this company for this project now? | Dated news, vacancies, website evidence and transparent scoring |

More rows do not necessarily add coverage. More sources do not establish truth by majority vote. A legal entity may operate several locations and brands; multiple people may share a name.

## Core journeys

### Discover

Choose project, geography, sector, company size and required fields. Search current Recon sources and save a list. Keep table and map views. Explain missing filters when a dataset lacks the field. Distinguish registered office, headquarters and actual premises.

### Understand

Open a company profile showing aliases, domain, registration identifiers, locations, people, contact routes, evidence and last checks. Show conflicts and uncertain matches. Opening a profile should not trigger paid lookups automatically.

### Research

Add a column in ordinary language: "Does this business run multiple locations?", "Who handles marketing?" or "What relevant expansion happened recently?" Preview a small selection, inspect evidence and estimated spend, then run on selected rows. Sources must support the answer and match the correct entity. Unknown remains unknown.

### Enrich

Choose company, person, email or phone fields separately. Try cache and eligible free sources before configured paid providers. State expected cost, hard ceiling and unavailable providers. Allow cancellation and resume. A request for email only must never buy phone enrichment.

### Prioritise

Rank by project-specific fit, evidence freshness and contact quality. Show reasons, missing evidence and uncertainty. Keep company fit, research confidence, deliverability and outreach eligibility as distinct concepts.

### Export and hand off

Export the approved list and provenance allowed by the data terms. Recheck suppression and eligibility at export. Record what was exported and why. Do not enable sending or calling as part of this pack.

## Contact semantics

- Business inbox and named work address are separate contact types.
- Switchboard, branch number and direct/mobile number are separate phone types.
- Published address, inferred pattern, vendor-supplied address and independently checked address remain distinguishable.
- "Provider verified" means the provider asserted it, with a date and method where available. It is not independent proof.
- Email verification cannot prove the person still works at the employer.
- A director is not automatically the operational buyer.
- Unknown, catch-all, timeout and rejected are distinct email check outcomes.
- Contact availability never automatically grants permission to market.

## MVP boundary

Deliver a reliable integrated Recon base, field-level evidence, one company-gap importer, first-party research columns and configurable email/phone provider contracts. Actual paid connectors are enabled only after an account is configured, entitlements are checked and a spend limit is set.

Do not build a new CRM, campaign sender, billing system, surveillance product or multi-tenant SaaS during this MVP. Add later capabilities only when they solve demonstrated needs.

## Success measurements

Measure against the current integrated Recon baseline on the same private UK sample:
- Incremental unique business coverage and duplicate rate.
- Correct legal-entity and domain match rate.
- Correct current decision-maker role on a manually checked subset.
- Published business email/phone coverage and separately named/direct-contact coverage.
- Percentage of research answers supported by the cited source.
- Cost per usable contact, not cost per API call.
- Time to prepare an actionable list and human corrections required.

Use 100 to 200 businesses across representative sectors first. Report denominators, unknowns and sampling method. Do not promise a target fill rate before measurement.

## Acceptance criteria

No unconfigured source calls; no client-side provider secrets; no cross-project private-note exposure; no automatic paid requests; no silent conflict overwrite; no duplicate billing on resume; no invented email/phone fields; no export of suppressed contacts; no imported personal records in git; existing CLI and map behaviour preserved.

Quality must be visible: a profile can be useful with gaps, but must never look complete by hiding them.

