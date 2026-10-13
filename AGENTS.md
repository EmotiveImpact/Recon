# Recon: start here

Recon is Edem's in-house outreach finder for all his projects. Read docs/THINKING.md (why and decisions), docs/RULES.md (who may be contacted and how) and docs/NEXT.md (what to build next) before changing anything.

- Plain British English everywhere, no em dashes.
- The repository is public. Never commit contact data: data/ and out/ stay ignored.
- Open data only. Never scrape Google Maps, booking platforms or professional registers.
- When unsure whether a business may be emailed, the answer is "post only".
- Keep the standard library only, apart from DuckDB for Overture.
- Run `python3 -m unittest discover -s tests -t .` before pushing; the tests need no internet.
- Record new decisions in docs/THINKING.md and tick off docs/NEXT.md as you go.
