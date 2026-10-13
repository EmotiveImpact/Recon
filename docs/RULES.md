# Contact rules

A cautious reading of the rules for business outreach, written so the tool errs on the safe side. This is not legal advice; check with a solicitor before a large UK campaign.

## United Kingdom

Two sets of rules apply: PECR (the Privacy and Electronic Communications Regulations) and UK GDPR. The Information Commissioner's Office (ICO) enforces both.

**Email**
- **Companies and limited liability partnerships** ("corporate subscribers") may be sent business marketing email without asking first. Each email must say who we are and give a simple way to opt out, and we must honour opt-outs straight away.
- **Sole traders and ordinary partnerships** count as individuals. They must agree first (or be existing customers who were given the chance to opt out). Most small salons, barbers and therapists are sole traders, so they get post instead.
- An email to a named person at a company is still personal data under UK GDPR. We rely on legitimate interests, keep only what we need, and say where we got the address if asked.

**Post**
Business-to-business letters are allowed without consent, as long as we honour requests to stop. Postcards suit the sole traders.

**Phone**
Calls are allowed unless the number is on the Corporate Telephone Preference Service (CTPS) or the TPS for sole traders. Screen before any calling campaign. Recon does not do this yet.

How Recon applies it: a business matched to Companies House as a company or LLP gets `can email`. Everything else, including any business we could not match, gets `post only`.

**Named people.** Recon may put one person's name and address on a `can email` row, so an email can go to the owner rather than a shared inbox. To keep this fair under UK GDPR:
- Only for companies and LLPs we may email. Never for `post only` rows, even with `--all-emails`, so a sole trader's personal address is never worked out.
- The name is an active director (or LLP member) from Companies House, which is public by law. Secretaries, former directors and companies acting as directors are left out.
- One person per business, nothing more about them than name, role and address.
- A worked-out address is marked as such, with its confidence and the reason, and is never presented as published. Our first email must say where we got their details and how to opt out, and an opt-out goes on the suppression list.

## United States

CAN-SPAM allows business email without consent, as long as each email has an honest sender and subject line, a working unsubscribe that is honoured within ten business days, and a real postal address. Recon marks every US business `can email`. Some states add rules for texts and calls; Recon does neither.

## Anywhere else

Recon marks businesses `check local rules`. Look the rules up before adding a target for a new country, and add them to `recon/rules.py` and to this file.

## Rules for any campaign sent from Recon's lists

- Send from a separate domain, so complaints never touch a product's own email reputation.
- Keep one suppression list across every project, and check it before each send.
- Keep a note of where each address came from (`email_found_on` does this).
