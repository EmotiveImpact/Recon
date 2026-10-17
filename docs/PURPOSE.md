# Purpose

## What Recon is for

Recon is Edem's in-house outreach engine. Every product Edem builds will need its first customers, and the hardest part of that is knowing exactly who to approach and being allowed to approach them. Recon answers both questions, for any product, in any country it knows the rules for:

1. **Who are they?** Every real business of the right kind, with where it is, its website and its phone number.
2. **May we contact them, and how?** Email where the law allows it, post where it doesn't.
3. **What's their address?** The contact email the business itself publishes, checked before anything is sent.

It does this for free, from open data, in a way Edem would be comfortable explaining to any of the businesses on the list.

## Who it serves

- **Edem**, deciding where to aim a campaign and how big a market really is.
- **Every Edem product.** SALEANE (software for salons, spas and studios) is the first. Others follow by adding a target list file; no code changes.
- **Future agents** who pick the work up. Everything they need to continue is written down in this folder.

## What good looks like

- One command gives one spreadsheet that a person can act on the same day.
- Nobody on the list is contacted in a way the law doesn't allow. When Recon is unsure, it says "post only".
- Running it costs nothing except time.
- The numbers it produces are honest: counts, match rates and email rates are reported, not guessed.

## Principles

- **Open data, used fairly.** Overture Maps, OpenStreetMap and Companies House. No scraping Google, booking platforms or the search pages of professional registers; official bulk downloads published for reuse are fine. No bought lists.
- **See everything, use only what's allowed.** Recon shows every email, phone and social link it finds (Edem's choice), labelled, while `contact_rule` decides who may be emailed.
- **Be a good guest online.** Respect robots.txt, visit few pages, go slowly, say who we are.
- **Finding and sending stay separate.** Recon finds. Sending is a later, deliberate stage with its own domain, unsubscribe handling and suppression list.
- **The code is public; the lists never are.**
- **Simple to run anywhere.** Python's standard library plus DuckDB.

## Where it could go

- A sending stage that respects every rule in [RULES.md](RULES.md).
- More countries, each with its rules written down first.
- Scoring, so the best-fit businesses come first.
- Possibly, one day, a product for others. Not before it has proved itself on SALEANE. See [THINKING.md](THINKING.md) for why.
