# Recon: start here

Recon is Edem's in-house outreach finder for every product he builds. SALEANE is the first.

Read these in order before changing anything:
1. docs/PURPOSE.md: what Recon is for and the principles it keeps.
2. docs/HISTORY.md: the conversation that created it, with the market figures and decisions.
3. docs/THINKING.md: the design decisions and how each step works.
4. docs/RULES.md: who may be contacted, and how, by country.
5. docs/NEXT.md: what to build next.

Ground rules:
- Plain British English everywhere, no em dashes. Edem is not technical: explain results in plain sentences.
- The repository is public. Never commit contact data: data/ and out/ stay ignored.
- Open data only. Never scrape Google Maps, booking platforms or professional registers. Never buy lists without Edem saying so.
- When unsure whether a business may be emailed, the answer is "post only".
- Recon finds; it does not send. Don't add sending without Edem's go-ahead and the safeguards in docs/RULES.md.
- Standard library only, apart from DuckDB for Overture.
- Run `python3 -m unittest discover -s tests -t .` before pushing; the tests need no internet.
- Record new decisions in docs/THINKING.md, and tick off docs/NEXT.md as you go.

First session in a new project: the first job is item 1 in docs/NEXT.md, a real run of targets/saleane-uk.json. It needs internet access to overturemaps-us-west-2.s3.amazonaws.com, overpass-api.de, download.companieshouse.gov.uk and the businesses' own websites. If the cloud workspace blocks those, run it on Edem's computer instead and say so.
