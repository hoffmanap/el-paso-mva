"""
El Paso Market Value Analysis (MVA) builder
Aggregates to Census block group, builds an internally-referenced
market-type typology via clustering. Modeled on Reinvestment Fund's MVA
methodology (block-group geography, multi-indicator cluster typology).

Inputs:
  - bg_test.geojson            : TIGER block group boundaries, El Paso County (598 BGs)
  - acs_bg_cr.json              : ACS 2024 5yr B19013/B25002/B25003/B25034 via Census Reporter
  - mls_bundle.json             : hoffmanap/MLSSales embedded bundle (geo_tract: 171 tracts w/ median_ppsf, median_dom, n)
  - result_00/01/02.csv         : Census batch-geocoded code violations (block group FIPS per address)
  - /home/claude/hoffmanap/permits/data/residential.geojson : 42,603 permit points w/ PID, Issued_Dat, JOBVALUE
"""
import json, csv, math
from collections import defaultdict

BASE = "/tmp/claude-0/-home-claude/b146bc85-bf48-59da-a6cf-542322a888e1/scratchpad/mva"

# ---------- 1. Block group geometry ----------
bg = json.load(open(f"{BASE}/bg_test.geojson"))
bg_feats = {f["properties"]["GEOID"]: f for f in bg["features"]}
print("block groups:", len(bg_feats))

# ---------- 2. ACS ----------
acs = json.load(open(f"{BASE}/acs_bg_cr.json"))["data"]
acs_by_bg = {}
for geoid_full, tabs in acs.items():
    geoid = geoid_full.split("US")[1]  # 12-digit BG GEOID
    e25002 = tabs.get("B25002", {}).get("estimate", {})
    e25003 = tabs.get("B25003", {}).get("estimate", {})
    e25034 = tabs.get("B25034", {}).get("estimate", {})
    e19013 = tabs.get("B19013", {}).get("estimate", {})
    total_units = e25002.get("B25002001") or 0
    vacant = e25002.get("B25002003") or 0
    own_total = e25003.get("B25003001") or 0
    own = e25003.get("B25003002") or 0
    yr_total = e25034.get("B25034001") or 0
    pre1960 = (e25034.get("B25034010") or 0) + (e25034.get("B25034011") or 0)  # built 1950-59 + before 1950 category tail
    # B25034 categories (2024 5yr): 002=2020+,003=2010-19,004=2000-09,005=1990-99,006=1980-89,
    # 007=1970-79,008=1960-69,009=1950-59,010=1940-49,011=before 1939
    acs_by_bg[geoid] = {
        "total_units_acs": total_units,
        "vacancy_rate": (vacant / total_units * 100) if total_units else None,
        "owner_occ_rate": (own / own_total * 100) if own_total else None,
        "median_hh_income": e19013.get("B19013001"),
        "pre1960_share": (pre1960 / yr_total * 100) if yr_total else None,
    }
print("ACS rows:", len(acs_by_bg))

# ---------- 3. MLS tract-level price/velocity -> assign to child block groups ----------
mls = json.load(open(f"{BASE}/mls_bundle.json"))
tract_stats = {}
for f in mls["geo_tract"]["features"]:
    p = f["properties"]
    tract_stats[p["GEOID"]] = {
        "median_ppsf": p.get("median_ppsf"),
        "median_dom": p.get("median_dom"),
        "n_sales": p.get("n"),
    }
print("MLS tracts with stats:", len(tract_stats))

# ---------- 4. Permits: spatial join (point in polygon) via shapely if available, else via tract/BG centroid grid fallback ----------
try:
    from shapely.geometry import shape, Point
    from shapely.strtree import STRtree
    HAVE_SHAPELY = True
except ImportError:
    HAVE_SHAPELY = False

bg_polys = {}
if HAVE_SHAPELY:
    for geoid, f in bg_feats.items():
        try:
            bg_polys[geoid] = shape(f["geometry"])
        except Exception:
            pass
    geoms = list(bg_polys.values())
    ids = list(bg_polys.keys())
    tree = STRtree(geoms)

def point_to_bg(lon, lat):
    if not HAVE_SHAPELY:
        return None
    pt = Point(lon, lat)
    idxs = tree.query(pt)
    for i in idxs:
        if geoms[i].contains(pt) or geoms[i].intersects(pt):
            return ids[i]
    return None

permits = json.load(open("/home/claude/hoffmanap/permits/data/residential.geojson"))
permit_count = defaultdict(int)
permit_recent_count = defaultdict(int)  # issued in last 5 years (2021-2026)
matched = 0
for f in permits["features"]:
    coords = f["geometry"]["coordinates"]
    lon, lat = coords[0], coords[1]
    cat = (f["properties"].get("CENSUSCATE") or "").strip()
    if "Single Family" not in cat and "Duplex" not in cat and "Triplex" not in cat and "Quadr" not in cat:
        continue
    bgid = point_to_bg(lon, lat)
    if bgid:
        matched += 1
        permit_count[bgid] += 1
        issued = f["properties"].get("Issued_Dat")
        if issued and issued > 1609459200000:  # Jan 1 2021 ms epoch
            permit_recent_count[bgid] += 1
print("permits matched to BG:", matched, "of", len(permits["features"]))

# ---------- 5. Code violations: geocoded block FIPS -> block group (first digit of block) ----------
viol_count = defaultdict(int)
viol_total = 0
for fn in ["result_00.csv", "result_01.csv", "result_02.csv"]:
    with open(f"{BASE}/{fn}", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < 12:
                continue
            match = row[2]
            if match != "Match":
                continue
            state, county, tract, block = row[8], row[9], row[10], row[11]
            if not (state and county and tract and block):
                continue
            blkgrp = block[0]
            geoid = f"{state}{county}{tract}{blkgrp}"
            viol_count[geoid] += 1
            viol_total += 1
print("geocoded violations assigned:", viol_total)

# ---------- 6. Assemble block-group table ----------
rows = []
for geoid, feat in bg_feats.items():
    tract_fips = geoid[:11]
    acsd = acs_by_bg.get(geoid, {})
    mlsd = tract_stats.get(tract_fips, {})
    total_units = acsd.get("total_units_acs") or 0
    land_sqmi = (feat["properties"].get("AREALAND") or 0) / 2_589_988.0
    rows.append({
        "GEOID": geoid,
        "NAME": feat["properties"].get("NAME"),
        "tract": tract_fips,
        "vacancy_rate": acsd.get("vacancy_rate"),
        "owner_occ_rate": acsd.get("owner_occ_rate"),
        "median_hh_income": acsd.get("median_hh_income"),
        "pre1960_share": acsd.get("pre1960_share"),
        "total_units_acs": total_units,
        "median_ppsf": mlsd.get("median_ppsf"),
        "median_dom": mlsd.get("median_dom"),
        "n_sales": mlsd.get("n_sales"),
        "permit_count": permit_count.get(geoid, 0),
        "permit_recent_count": permit_recent_count.get(geoid, 0),
        "permits_per_1000_units": (permit_count.get(geoid, 0) / total_units * 1000) if total_units else None,
        "violation_count": viol_count.get(geoid, 0),
        "violations_per_1000_units": (viol_count.get(geoid, 0) / total_units * 1000) if total_units else None,
        "land_sqmi": land_sqmi,
    })

print("assembled rows:", len(rows))
json.dump(rows, open(f"{BASE}/bg_table.json", "w"))
print("wrote bg_table.json")

# quick coverage check
have_mls = sum(1 for r in rows if r["median_ppsf"] is not None)
have_acs = sum(1 for r in rows if r["vacancy_rate"] is not None)
print(f"BGs with MLS price data: {have_mls}/{len(rows)}")
print(f"BGs with ACS data: {have_acs}/{len(rows)}")
