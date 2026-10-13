# How Recon came about: the conversation, step by step

A record of the 13 October 2026 conversation in SALEANE's project ("Elevator pitch" thread) that led to Recon. Kept so later agents understand the context behind each decision. Figures are as found that day; sources are linked.

## 1. SALEANE's elevator pitch

Edem asked for SALEANE's elevator pitch, for both studio owners and investors. Final versions:

- **One-liner:** "The calm, beautiful app that runs your whole beauty studio, with its own AI assistant built in."
- **Studio owners:** one calm app for bookings, checkout, clients, team pay, stock and marketing; Ask SALEANE answers guests and books them in, in the studio's voice, with an optional phone receptionist; £59 a month per location with every feature included, room to grow, no hidden catches, and a free move from the old system.
- **Investors:** around 170,000 hair, beauty and nail studios with staff across the UK and US; one app for the whole studio with its own AI assistant; £59 a month per location, about £43 kept; more from extras (a £79 phone receptionist, bigger allowances) and later card payments; one studio in a hundred is about £1.2m a year; the AI engine (LUMANE) can work inside other apps too; the app is built and tested, next is a pilot with a real studio.

Pricing facts that must stay right: the phone receptionist is an extra (+£79 a month), and £59 covers five people who take bookings, then £9 a month each.

## 2. Who SALEANE can serve, and how many

Edem pointed out it isn't only salons. The full market page is at https://claude.ai/artifact/PDMj4G6VyfxMKK85NYbp64. In short, businesses with staff across the UK and US:

| Group | Count | Fit |
|---|---|---|
| Beauty and wellness (hair, nails, beauty, lashes and brows, spas, massage, facials, holistic) | about 190,000 | Ready now |
| Body and health (physios, chiropractors, osteopaths) | about 89,000 | Needs SALEANE's separate Clinical part |
| Barbers and tattoo | about 31,000 | Small changes: a darker look and different wording |
| Aesthetics and med spas | about 16,600 | Needs Clinical |
| **Total** | **about 325,000** | |

On top of that the US has about 1.28 million self-employed hair, nail and barber businesses, left out because they mostly work alone.

Main sources: ONS Annual Business Survey 2024 (50,438 UK hair and beauty businesses), the NHBF (63,800), US Census County Business Patterns 2023 (84,176 beauty salons with staff), ISPA (21,980 US spas), AmSpa (10,488 US med spas), CQC data via BCAM (6,117 UK aesthetics clinics), Orbital (39,000 US physical therapy clinics), First Research (40,000 US chiropractic practices). US tattoo studios (about 20,000) and UK physio, chiro and osteo practices (about 10,000) are estimates.

Not counted for lack of good figures: massage studios, UK spas, pet groomers, float and sauna rooms, piercing studios, make-up artists and mobile therapists.

**Direction recommended (not yet decided by Edem):** lead with beauty and wellness, described as "beauty and wellness" rather than "female", because many salons and spas serve men too. Widen later with sector editions of the same app (look, photos, wording): barbers and tattoo from year 2, Clinical from year 3.

**Five-year projection** (locations at end of year 5): cautious 5,000, steady 13,000, strong 26,000, worth about £3.5m, £9.2m or £18.4m a year from the £59 price alone.

## 3. How many studios in the first six months

With a strong campaign and a clear problem solved: about **150 UK locations** in six months (floor 60, stretch 300), building roughly 5, 15, 35, 65, 100, 150 by month. Limits: studios rarely switch mid-year, and each free move-in takes hands-on time (about 5 to 8 a week per person). What pushes towards 300: one sharp message about a daily pain, Professional Beauty London in March, Instagram ads, refer-a-studio rewards, and two people doing move-ins. The US should start from month 6 at the earliest, expecting 20 to 50 locations in its first three months. The clock starts when studios can actually sign up and pay.

## 4. Reaching them: emails

- **We had no lists.** UK rules (PECR): limited companies and LLPs may be emailed with an opt-out; sole traders and partnerships need consent first, and most small studios are sole traders. US (CAN-SPAM): business email allowed with honest subjects, an unsubscribe and a postal address.
- **Paid options** (Cognism, Apollo, Data Axle) cost a few hundred to a couple of thousand pounds.
- **Edem asked for free.** Companies House's free monthly file shows which UK businesses are companies (so may be emailed); emails come from each business's own website.
- **Edem asked for open source.** Overture Maps and OpenStreetMap give the businesses; Scrapy-style crawling (Recon uses the standard library) gets published emails; Reacher checks them. Google Maps scrapers were rejected because they break Google's terms.
- **For sole traders:** post (letters and postcards are allowed business to business) and Instagram.

## 5. Should it be a product?

Edem asked whether to turn it into another product. Advice: not yet. It's a crowded market (Apollo, Cognism, Hunter, Outscraper, Clay), the UK legal side is easy for customers to get wrong, and it would pull focus before SALEANE's first paying studio. Build it in-house first; revisit with evidence. A sector-specific version (helping beauty suppliers and training academies find studios) is the most promising angle if it ever goes further.

Edem then decided it should live in its own repository, **Recon**, and be the in-house outreach tool for every project he builds, with all the thinking in the repository so a new project can load it and continue.
