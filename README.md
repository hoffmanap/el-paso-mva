# El Paso Market Value Analysis

A block-group market typology for El Paso County, TX, built in the spirit of
[Reinvestment Fund's Market Value Analysis](https://www.reinvestment.com/research/market-value-analysis/)
methodology: a data-based, internally-referenced index of residential real
estate markets, clustered at the Census block group level to surface
investment-relevant variation that neighborhood-level studies miss.

**[View the live dashboard →](index.html)** (open via GitHub Pages once enabled, or the published Claude artifact)

## What it does

Standardizes six indicators across 598 El Paso County block groups and
clusters them with k-means into six market types, **A** (highest value /
least distress) through **F** (most distressed):

- Median sale price per sq ft (block-group resolution)
- Median days-on-market (tract-level, supplementary)
- New residential permits per 1,000 housing units
- Owner-occupancy rate
- Vacancy rate
- Code-enforcement (physical blight) violations per 1,000 units

Like the original MVA, types are **internally referenced** — meaningful
relative to each other within El Paso County only, not comparable to
another city's MVA.

## Data sources

| Layer | Source | Notes |
|---|---|---|
| Home sales | [`hoffmanap/housetrends`](https://github.com/hoffmanap/housetrends) | 27,448 geocoded closed sales since 2023, spatial-joined to block group |
| Days-on-market | [`hoffmanap/MLSSales`](https://github.com/hoffmanap/MLSSales) | Tract-level only (source bundle has no finer resolution) |
| Permits | [`hoffmanap/permits`](https://github.com/hoffmanap/permits) | 42,603 residential permits, City of El Paso ArcGIS feed, re-fetchable live |
| Code enforcement | City of El Paso case export (Nov 2024) | Filtered to physical-blight categories; geocoded via Census Bureau batch geocoder |
| Foreclosures | El Paso County Clerk's Foreclosure Map feed | Snapshotted monthly (see below) — accumulating, not yet used as a clustering input |
| Demographics / housing stock | ACS 2020–2024 5-year estimates, via Census Reporter | Block-group level: vacancy, owner-occupancy, income, housing age |
| Geography | US Census TIGERweb | 598 block groups, El Paso County (FIPS 48141) |

## Known gaps vs. a full MVA

- **No subsidized-housing layer** (HUD LIHTC/Section 8 data not yet pulled in)
- **Foreclosure history is still accumulating** — see below for why, and the plan to fold it in once there's enough history

## The foreclosure data problem

El Paso County's searchable foreclosure form
(`apps.epcountytx.gov/publicrecords/Foreclosures`) is gated by a Cloudflare
Turnstile CAPTCHA, and its results only expose legal descriptions
(subdivision/lot/block) — no address, parcel ID, or coordinates, which is
why a manual export caps out at 500 records with nothing spatially usable.

The same site's **Foreclosure Map** page (`.../Foreclosures/Map`) is not
CAPTCHA-gated and server-renders a JS array with `PropertyId` (the EPCAD
parcel ID), geocoded lat/lon, street/city/zip, and sale date — a direct
parcel join key. The catch: it only ever shows the *next* posted sale
date(s), since Texas law requires posting 21+ days ahead of a first-Tuesday
sale. It's a live docket, not a historical archive.

`foreclosures/fetch_foreclosures.py` snapshots that feed and de-duplicates
by `ForeclosureId` into a running CSV. `.github/workflows/monthly-foreclosure-pull.yml`
runs it on the 1st of each month and commits any new postings. Run it
manually any time from the Actions tab, or locally:

```bash
python3 foreclosures/fetch_foreclosures.py --out foreclosures/foreclosures_history.csv
```

Given a year or two of accumulated snapshots, foreclosure density per
block group becomes a real sixth-or-seventh clustering input alongside the
indicators above.

## Rebuilding the analysis

```bash
# 1. Aggregate all sources to block group (writes data/bg_table.json)
python3 scripts/build_mva.py

# 2. Spatial-join point-level sales for true block-group $/sqft
python3 scripts/join_sales_points.py

# 3. Cluster into market types A–F (writes data/mva_result.json)
python3 scripts/cluster_mva.py

# 4. Rebuild data/mva_map.geojson (block-group geometry + market_type) for the dashboard
```

Each script documents its inputs and assumptions inline.
