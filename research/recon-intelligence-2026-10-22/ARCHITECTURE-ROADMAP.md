# Architecture and staged build plan

Proposed, 22 October 2026. No runtime integration is implemented by this documentation change.

## System shape

Existing Recon discovery and geographic search remain the entry point. Add an evidence store and provider runner behind the existing server. Preserve DuckDB for large read-heavy dataset processing; use an appropriately migrated transactional store for jobs, evidence, budgets and project state. Confirm existing branch storage before selecting the job database.

Optional workers expose a narrow job interface. Do not replace Recon with several external applications sharing a database. There is one canonical identity layer and one contact-policy/export boundary.

## Data model

| Record | Purpose and key constraints |
|---|---|
| Organisation | Stable internal ID, country, registration IDs and canonical identity. Country qualifies registry numbers. |
| Brand/domain | Many-to-many links with an organisation; a chain/shared domain alone cannot merge entities. |
| Location | Trading premises with a typed relation to the organisation; registered office remains distinct. |
| Person | Minimal professional identity, independent of a single employer. |
| Role | Person-to-organisation relationship with title, dates, evidence and current/uncertain/former status. |
| ContactPoint | Email/phone, subject or organisation, purpose/type, publication origin and separate check history. |
| Observation | Field/value, source record ID/URL, retrieved time, source effective time, confidence, inference flag and restrictions. |
| SourceRelease | Publisher, version, import checksum, licence evidence and source counts. |
| ProjectMembership | Project-specific fit, list membership, private notes and export decisions. |
| ResearchCell | Prompt/schema version, entity, dependencies, result, evidence and execution state. |
| Attempt/Job | Provider call, result class, run ID, idempotency key, cost reservation and completion ledger. |
| Suppression | Contact/entity restriction with scope, reason and date; applied before exports and relevant lookups. |

Preserve original observations and derive a current view. Prioritise exact registration evidence for legal identity and dated first-party evidence for operational facts. Provider data can suggest a match, but cannot silently override conflicting legal IDs. Do not use a single confidence number to represent identity, role currency, contact deliverability and project fit.

## Ingestion and resolution

1. Register source release and applicable terms before ingestion. Sources with unestablished reuse rights stay disabled.
2. Stream or query UK subsets; do not load global files entirely into memory.
3. Normalise country codes, registration numbers, domains, phone formats and addresses without destroying originals.
4. Match exact qualified company IDs first. Use domain, name/address and geographic evidence to propose weaker links.
5. Block conflicting company IDs, different countries, shared accountant contacts and chain-domain collisions.
6. Retain ambiguous candidates in a review queue. Never use an uncertain merge to upgrade contact eligibility.
7. Record incremental coverage, match rate and conflicts relative to the existing database.

PDL mirrors are alternative inputs of the same source family, not independent corroboration. Keep publisher and release lineage.

## Provider contract

Input: job ID, entity identity, requested fields, permitted source set, budget reservation, freshness requirements and project scope.

Output: status; typed observations; evidence references; match explanation; vendor verification assertion and method; effective/retrieval dates; billable units and currency; provider request ID; retry/callback metadata; usage restrictions.

Statuses: found, not_found, ambiguous, retryable_error, permanent_error, unconfigured, blocked_terms, budget_exhausted and pending_callback.

An adapter performs one vendor interaction. The runner owns order, eligibility, caching, budgets, retry, audit and stop rules. Vendor-specific credits must not be added together as if they were a common currency.

## Waterfalls

Company: existing records -> current official identity -> eligible company-gap source -> first-party site -> configured paid company provider.

Person/role: current relevant team page -> eligible officer evidence for director questions -> configured professional-data provider. Do not label an officer as marketing manager.

Email: fresh eligible published work address -> optional finder -> optional verifier. Keep inferred and provider-asserted values distinct.

Phone: fresh published business phone -> optional direct-number provider only when requested. A switchboard does not satisfy a request for a direct number.

Research: cache -> permitted first-party/cited web evidence -> structured model answer -> validation/abstention. Web content is untrusted input, not instructions.

Stop when the field's quality criteria are met or the cap is reached. Weak results may be retained without ending a higher-quality search. Do not contact every available vendor by default.

## Cost, caching and jobs

Reserve maximum foreseeable cost transactionally before a paid call. Set conservative per-provider limits and handle vendors whose final charge is unknown. Bound retries and concurrent reservations. Record reconciliation between estimates and actual billable events. Pause spending when accounting cannot be reconciled.

Cache keys include provider, canonical identity, requested field, input identity and schema/contract version. Cached observations retain expiry and usage rights. A refresh creates a new observation rather than rewriting history.

Persistent jobs support queued, running, waiting_callback, succeeded, partial, failed and cancelled states. Use lease expiry and idempotent completion. Authenticate callbacks, validate provider request IDs and deduplicate retries. A cancelled/replaced job cannot overwrite a newer result or restart spending.

## Workbench

Navigation: Overview, Discover/Map, Companies, People, Project Lists, Research Workbooks, Sources/Providers and Runs.

A company profile shows locations, people/roles, contacts, timeline, evidence and project relevance. Keep source/quality details one click away. Research cells show progress, sources and failure reasons. The provider screen shows configured capability and entitlement rather than pretending every listed adapter is ready.

## Milestones

| Milestone | Delivery | Exit evidence |
|---|---|---|
| M0 integrated base | Compare #7/#8 and later #4/#5/#6 changes; reconcile useful fixes on one branch. Keep main untouched until reviewed. | Exact base SHA; combined tests/build; private-data rebuild requirements documented. |
| M1 identity/evidence | Migrations, source releases, observations, contact types and project separation. | Existing exports preserved; conflicting IDs and shared domains do not merge. |
| M2 dataset uplift | Audit current PDL coverage; evaluate BigPicture; import one approved UK company subset privately. | Incremental unique coverage and manually checked matching sample. |
| M3 free research | Team-page/structured-data extraction and cited research columns, with explicit gaps. | Sample answers checked against evidence; no invented people/contact values. |
| M4 contact runner | Per-field adapters, cache, budgets, attempt ledger and resumable jobs. Begin with a fake transport in tests and existing optional provider where suitable. | Disabled sources make zero calls; concurrency cannot overspend; email-only never buys phone. |
| M5 optional vendor pilot | One configured professional/contact provider, then another only if measured uplift warrants it. | Cost per usable contact and role accuracy on a representative private UK sample. |
| M6 workbench | Profile/table/map continuity, research previews, batch progress and reviewed export. | Actual end-to-end browser flow with source evidence and suppression checks. |
| M7 signals | User-requested refreshes and evidence-backed changes such as new branches or current vacancies. | Freshness and entity attribution measured; scheduling explicitly configured. |

Do not attach dates to this roadmap before the implementation base and source access are established. Do not build all optional providers at once.

## Validation and operational boundaries

Use the integrated branch's full offline tests and frontend checks; add tests around meaningful boundaries: identity conflict, budget reservation, cache expiry, callback replay, cancellation, suppression and evidence-backed abstention. Use synthetic records in committed fixtures. Validate live-provider behaviour separately with an authorised small sample and capped spend.

Secrets remain server-side. Protect optional crawlers against internal/private-address fetches, redirects and unbounded downloads. Private provider data never enters git. Preserve deletion/objection handling across caches and exports. The current public repository must not become a place to host downloadable personal contact lists.

