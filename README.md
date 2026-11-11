# El Paso Market Value Analysis

A block-group market typology for El Paso County, TX, built in the spirit of
[Reinvestment Fund's Market Value Analysis](https://www.reinvestment.com/research/market-value-analysis/)
methodology: a data-based, internally-referenced index of residential real
estate markets, clustered at the Census block group level to surface
investment-relevant variation that neighborhood-level studies miss.

**[View the live dashboard →](https://hoffmanap.github.io/el-paso-mva/)**

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
| Subsidized housing | HUD LIHTC Properties, live ArcGIS feed (`egis.hud.gov`) | 88 El Paso County properties, 5,888 low-income units — mapped as an overlay, see below |

## Known gaps vs. a full MVA

- **Subsidized housing isn't a clustering input yet** — LIHTC is pulled in and mapped (see below), but it's shown as an overlay, not folded into the six indicators
- **Section 8 is only partly available** — see below for what HUD does and doesn't publish
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

## Subsidized housing: LIHTC yes, Section 8 partly

**LIHTC** is a clean win. HUD runs a live, geocoded, nationwide ArcGIS feed
of every Low-Income Housing Tax Credit property
(`egis.hud.gov/arcgis/rest/services/gotit/LIHTCProperties/MapServer/0`), no
key required — the same pattern as the TIGERweb geometry and the ACS pull.
`scripts/build_subsidized_housing.py` queries it for El Paso County (90 raw
records, 88 unique addresses, 5,888 low-income units), spatial-joins it to
block groups, and the dashboard shows it as a toggleable gold-dot overlay
with a per-property tooltip and a per-block-group unit count in the detail
panel.

**Section 8 is split into two very different stories:**

- *Project-based* assistance (privately-owned buildings with HUD
  contracts, including 202/811 elderly & disabled housing) is in the same
  HUD system, as a sister layer called Multifamily Properties
  (`.../gotit/MultifamilyProperties/MapServer/0`) — 72 El Paso properties,
  roughly 5,100 assisted units. The catch: HUD doesn't publish coordinates
  for this layer (every record comes back with null geometry, despite the
  service advertising point geometry), so it contributes a county-level
  count only — it's in `data/subsidized_housing.json` as
  `mf_county_summary`, but it's not on the map.
- *Tenant-based* assistance (Housing Choice Vouchers, what most people
  mean by "Section 8") isn't public at any address resolution. Voucher
  holders are individual low-income households, and HUD doesn't release
  where they live — for good reason. The closest public substitute is a
  housing authority's aggregate voucher count (no addresses), which adds
  nothing spatial here and isn't pulled in.

## Rebuilding the analysis

```bash
# 1. Aggregate all sources to block group (writes data/bg_table.json)
python3 scripts/build_mva.py

# 2. Spatial-join point-level sales for true block-group $/sqft
python3 scripts/join_sales_points.py

# 3. Cluster into market types A–F (writes data/mva_result.json)
python3 scripts/cluster_mva.py

# 4. Pull HUD LIHTC + check Multifamily/Section 8 (writes data/subsidized_housing.json)
python3 scripts/build_subsidized_housing.py

# 5. Rebuild data/mva_map.geojson (block-group geometry + market_type + subsidized counts)
python3 scripts/build_full_map.py
```

Each script documents its inputs and assumptions inline.
