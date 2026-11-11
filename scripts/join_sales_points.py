"""
Spatial-join housetrends' point-level sales to Census block groups,
replacing the tract-assigned median $/sqft from the MLSSales bundle with
true block-group resolution. DOM (days-on-market) isn't in housetrends'
columns, so median_dom is still carried over from the tract-level bundle
as a supplementary (coarser) indicator.
"""
import csv, json
from collections import defaultdict
from shapely.geometry import shape, Point
from shapely.strtree import STRtree

BASE = "/tmp/claude-0/-home-claude/b146bc85-bf48-59da-a6cf-542322a888e1/scratchpad/mva"

bg = json.load(open(f"{BASE}/bg_test.geojson"))
bg_polys = {f["properties"]["GEOID"]: shape(f["geometry"]) for f in bg["features"]}
ids = list(bg_polys.keys())
geoms = list(bg_polys.values())
tree = STRtree(geoms)

def point_to_bg(lon, lat):
    pt = Point(lon, lat)
    for i in tree.query(pt):
        if geoms[i].intersects(pt):
            return ids[i]
    return None

ppsf_by_bg = defaultdict(list)
n_by_bg = defaultdict(int)
matched = 0
total = 0
with open("/home/claude/hoffmanap/housetrends/data/el_paso_sales.csv", newline="") as f:
    r = csv.DictReader(f)
    for row in r:
        total += 1
        if not row["latitude"] or not row["longitude"]:
            continue
        date = row.get("lastSaleDate") or ""
        if date < "2023-01-01":  # keep it current: last ~3.5 years
            continue
        ppsf = row.get("price_per_sqft")
        if not ppsf:
            continue
        try:
            ppsf = float(ppsf)
        except ValueError:
            continue
        if ppsf <= 0 or ppsf > 1000:  # drop obvious junk
            continue
        lon, lat = float(row["longitude"]), float(row["latitude"])
        bgid = point_to_bg(lon, lat)
        if bgid:
            matched += 1
            ppsf_by_bg[bgid].append(ppsf)
            n_by_bg[bgid] += 1

print(f"total rows {total}, matched to BG {matched}")
print(f"block groups with >=3 sales: {sum(1 for v in n_by_bg.values() if v>=3)}")

import statistics
out = {}
for bgid, vals in ppsf_by_bg.items():
    out[bgid] = {
        "median_ppsf_bg": round(statistics.median(vals), 2),
        "n_sales_bg": len(vals),
    }
json.dump(out, open(f"{BASE}/bg_ppsf.json", "w"))
print("wrote bg_ppsf.json for", len(out), "block groups")
