# Platform assessment and combination strategy

22 October 2026. Selected source files and licences were inspected. This is not a runtime or security certification.

## Component decisions

| Platform | Capability we want | Integration decision |
|---|---|---|
| OpenClay / Altclay | Spreadsheet import, prompt-defined research columns, sample then batch, model selection | Implement the research-column experience in Recon with original code. Reuse licence unestablished. Its inspected route turns provider output into JSON; Recon additionally needs durable evidence and schema validation. |
| Bricks | Configurable research/formula columns, optional local models, browser-assisted extraction | Reference only until reuse permission is established. Do not enable arbitrary JavaScript or browser scripts from a research column. |
| OpenGTM | Workbooks, discovery/enrichment/research separation and broader workflow design | Evaluate as an alternative deployment or design reference. Actual LICENSE states AGPL v3. Do not graft its backend into Recon without deciding licence and runtime implications. |
| OpenProspector | Separate email/phone waterfalls, provider adapters, freshness-aware cache, attempt ledger and deferred callbacks | Best current selective-reuse candidate alongside enrichment-kit. MIT verified. Its Cloudflare/D1 and @clawnify runtime dependencies make wholesale adoption a poor fit for existing Recon. |
| enrichment-kit | Small provider registry and waterfall building blocks | MIT verified. Good small reference or optional TypeScript worker after dependency decision. Do not assume included provider pricing, endpoints or availability remain correct. |
| OpenEnrich | Compact normalisation, cache, domain-pattern memory and verified-result stopping | AGPL v3. Reference or separately evaluated service; archived for research, not imported into the Recon runtime. |
| OpenKiln | Modular workflow skills, CRM and touch history concepts | Elastic License 2.0. Hosted-service restrictions mean it is not the default foundation for a future Recon SaaS. |
| Crawl4AI | Optional extraction from JavaScript-heavy first-party websites | Separate optional worker if measured coverage warrants it. Apache text with additional attribution requirement. |
| Firecrawl | Website extraction API | Alternative to Crawl4AI rather than an additional mandatory extraction layer. AGPL core; hosted service differs. |
| dlt | Incremental imports and source/schema handling | Later optional importer. Core Apache 2.0; do not treat all dltHub extensions as equally licensed. |
| Reacher | Mailbox checks | Inspected pinned revision has an MIT licence. Existing optional service. Preserve unknown/catch-all outcomes and recognise SMTP reachability limits. |

## Source-code evidence

The following repository revisions were inspected through GitHub. They are evidence pins for research snapshots, not installed dependencies:

- https://github.com/masteranime/enrichment-kit/tree/6998898c038a1f61c900aa8d96290b93049d0b84
- https://github.com/clawnify/OpenProspector/tree/2443c450224f210da2e1cac9529daa4b785a5a36
- https://github.com/raghav3600/Altclay/tree/874d0ed8ef0a279b12c4ec01e87d42a5a7130b0d
- https://github.com/BraaMohammed/bricks/tree/586186e0d71d49a1a2fb762b66f65ad4f33d44f6
- https://github.com/debpalash/OpenGTM/tree/ac011a6891749ca456ec4820cd20b28c71479f64
- https://github.com/openenrich/openenrich/tree/570042c8b5db008aeb9026e4c2cfbd7f90712b82
- https://github.com/OrbiSearch/openkiln/tree/96786195ad1120c81388b28928b3a0ebd1f07a0d

Selected inspected paths:
- enrichment-kit: src/waterfall/builder.ts and LICENSE.
- OpenProspector: src/server/providers/index.ts, src/server/enrich.ts, package.json and LICENSE.
- Altclay: app/api/enrich/route.ts on its actual default branch.
- OpenEnrich: src/core/enrich.ts.
- OpenGTM: LICENSE.
- OpenKiln: LICENSE.

OpenProspector's inspected registry defines 19 provider adapters, with independent email/phone ordering and cache/deferred-result interfaces. This does not prove all integrations work or that a user's subscription permits them. Its vendor price comments are not independent pricing evidence.

OpenEnrich's inspected loop assumes a particular charging model for provider results. Recon must instead declare charging behaviour per provider and reserve costs before concurrent calls; misses, retries and deferred callbacks may have charges.

## Recommended composition

Keep Recon as the owner of identity, private records, project context, contact eligibility and exports.

Build an original workbook/research interface informed by OpenClay's workflow. Use MIT-compatible provider patterns from OpenProspector/enrichment-kit only when their exact files and dependencies are reviewed and required notices are retained. Keep website extraction replaceable and optional.

The roles are complementary:
- Datasets supply candidate facts.
- Matching decides which entity a fact belongs to.
- Research workers answer custom questions from evidence.
- Contact providers fill requested contact gaps.
- Verification grades a contact route.
- Project scoring explains fit.
- Export preserves provenance and restrictions.

An AI provider does not substitute for a contact database. A crawler does not substitute for a company matcher. Installing a Clay alternative does not grant access to its supported paid providers.

## Copying and runtime policy

This pack preserves research and pinned source archives with their licences. Bricks/Altclay private research copies are excluded from the public repository. Restricted or copyleft projects require an explicit applicable licence/deployment decision before adoption. MIT code reuse must retain the copyright and licence notice and respect dependency terms.

Existing core rule: Python standard library plus DuckDB. Initial contracts and evidence storage can follow that rule. Any Node/browser worker is an optional separate executable and must not silently become required for CLI discovery. A service boundary alone does not settle copyright or data licensing.

Review quality beyond the README: source correctness, recent provider API compatibility, tests, dependency availability, deployability, evidence retention and expected cost. Prefer the smallest piece that demonstrably closes a Recon gap.

