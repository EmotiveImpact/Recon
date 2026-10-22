# Recon implementation handoff

The owner requests consolidation of company datasets and Clay-style research/enrichment into Recon, including an explanation of the emerging product. This pack is the planning handoff, not implemented functionality.

## Goal

Build Recon into an in-house business intelligence workspace: discover businesses, establish identity, identify relevant people, find available contact routes, research context and rank project fit with evidence.

## First actions

1. Read root AGENTS.md and required docs. Then read this research pack and docs/CLAY-UK-DATA-2026-10-22.md.
2. Refresh repository and PR state. At research time #7 and #8 are separate open integration attempts; #9 is documentation. Main remains the initial implementation.
3. Compare actual changes in #7/#8 plus current #4/#5/#6 heads. Preserve identity/count corrections from #7 and UK-eligibility/private-data corrections from #8 where applicable. Do not assume one supersedes the other.
4. Establish one isolated implementation branch, record its exact source SHA and run the applicable Python/frontend checks.
5. Deliver M1 first, then one measured M2 importer. Do not try to merge every external platform or enable every provider.

## Technical choices

- Retain existing Python/DuckDB discovery and current interface.
- Model companies, brands, locations, people, roles, contacts and evidence separately.
- Preserve project-specific notes and fit scores.
- Use the platform assessment to choose small compatible pieces. MIT OpenProspector/enrichment-kit are selective candidates; their external runtime dependencies are not automatically cleared.
- Implement original research-column behaviour rather than copying unlicensed Altclay/Bricks code.
- New runtimes remain optional; no silent core dependency-policy change.
- Create and record migration/rollback paths before schema changes.

## Data choices

sources.json is a research registry, not executable configuration. Every entry starts disabled. Validate source terms, freshness, fields and existing Recon coverage before ingestion.

Start with approved company sources and current public business contact channels. BigPicture has an explicit dataset licence but an older snapshot. PDL mirrors overlap. Saleleads/OpenDataFoundation remain on hold for reuse investigation. OpenDataFoundation's people count does not establish contact fields or permission to use them.

No bulk contact data in the public repository. No subscriptions, purchases, outreach sending or calling are authorised by this handoff. If supplied provider credentials later permit a pilot, use a small sample and explicit spend cap.

## Required demonstrations

- One company profile combines at least two eligible sources without duplicate entities.
- Conflicting company identifiers stay separate.
- Sources and dates explain each chosen field.
- A research question returns a cited answer or a clear unknown.
- Email-only and phone-only requests remain separate.
- Retry/resume does not duplicate billable calls.
- Suppressed contacts never reappear in exports.
- Existing map/CLI flows still work.

## Report

Publish a draft PR with concrete before/after behaviour, exact validation evidence, limitations and remaining access needs. Keep changes reviewable. Do not auto-merge or deploy.

Treat this product synthesis as a direction to implement incrementally. Do not claim completeness, independent email verification, live vendor support or imported dataset coverage without evidence.

