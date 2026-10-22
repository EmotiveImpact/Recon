# Recon intelligence workspace: research and implementation pack

22 October 2026. This pack consolidates this conversation's datasets, contact providers, Clay alternatives, architectural synthesis and implementation handoff.

## What is emerging?

Recon is becoming a business intelligence and prospect research workspace for all of the owner's projects. It connects fragmented company and location data to relevant people, contact routes and current evidence, then explains which businesses fit a project and what to do next.

Product promise: **Find the right business, understand it, identify the right person and show the evidence behind the next step.**

The distinctive asset is a reliable, reusable company record enriched over time, rather than the number of imported rows. One business can support SALEANE, Ardent and Emotive Impact with different project-specific fit scores and research questions. Global identity is shared; private notes, lists and campaign decisions belong to the project.

This is a product direction, not a claim that Recon already implements these capabilities. Keep the initial delivery in-house. Commercial SaaS and outbound sending remain separate decisions.

## Read in order

1. [Product requirements](PRD.md)
2. [Source catalogue](sources.json)
3. [Platform and reuse assessment](PLATFORMS.md)
4. [Architecture and roadmap](ARCHITECTURE-ROADMAP.md)
5. [Implementation handoff](AGENT-HANDOFF.md)
6. [Earlier detailed source brief](../../docs/CLAY-UK-DATA-2026-10-22.md)

## What has been copied

The repository now holds research, primary-source links, licence findings, inspected software revision identifiers, proposed contracts, requirements and a build sequence. Pinned source archives are being preserved under research/vendor-archives, with original licences. See ACQUISITION-STATUS.md for the exact transfer status. Bulk datasets remain outside this public repository. The repository is public; imported datasets and lead records belong in private data storage.

All catalogue entries are disabled. A catalogue entry is a research candidate, not an installed connector or a grant of reuse rights. No subscriptions or credentials were acquired and no messages were sent.

## Corrections and new findings

- The PDL mirror overlaps the PDL original. Do not add the two advertised record counts together.
- Company datasets do not guarantee named people, emails or direct telephone numbers.
- BigPicture's free snapshot is listed as Q2 2024. Stale data can help discover a domain but cannot establish a current role.
- OpenDataFoundation's raw dataset card also advertises about 273M business locations and 101M company-linked business contacts, alongside 103M companies. These are publisher claims. The card does not establish a reuse licence, UK coverage, identity accuracy or email/phone availability. It is an investigation candidate, not an approved source.
- OpenClay/Altclay and Bricks have no established reuse licence in the inspected repositories. Private research copies were downloaded; do not republish or integrate their code without permission.
- OpenKiln uses Elastic License 2.0, including hosted-service restrictions.
- OpenGTM's actual LICENSE identifies AGPL v3 although GitHub's automated classifier returns NOASSERTION.
- OpenProspector has an MIT licence and useful provider workflow code. Its application depends on Cloudflare and several @clawnify packages whose availability and terms have not been validated here.
- Public availability does not establish commercial reuse permission. Apollo account exports are documented; no authorised public full Apollo contact dump was verified.

## Verification

The linked source pages, selected software files, licences and repository heads were inspected. External applications were not installed or benchmarked. Dataset counts, completeness and private Recon data were not reproduced. The required offline main-branch suite passes 21 tests. The pack also supplies a standalone acquisition helper; Recon runtime behaviour is unchanged.

