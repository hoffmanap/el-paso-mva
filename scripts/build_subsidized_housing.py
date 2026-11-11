"""
Build a combined subsidized/assisted-housing point layer for El Paso County
from two HUD sources, then spatial-join to block groups.

Sources (live HUD ArcGIS services, no key required):
  1. LIHTC Properties  -- egis.hud.gov/.../gotit/LIHTCProperties/MapServer/0
     Low-Income Housing Tax Credit projects. Fields used: PROJECT, STD_ADDR,
     N_UNITS, LI_UNITS (low-income units), HUD_ID.
  2. Multifamily Properties -- egis.hud.gov/.../gotit/MultifamilyProperties/MapServer/0
     HUD-insured/subsidized multifamily (includes project-based Section 8,
     202/811 elderly & disabled housing, and other HUD-financed subsidized
     properties). 72 El Paso properties matched by city/name -- BUT this
     service returns null geometry for every record (confirmed: the layer
     advertises esriGeometryPoint but every query comes back ungeocoded).
     So it contributes county-level counts/units only, not mappable points.
     Reported in the README/about panel as a known limitation, not silently
     dropped.

Note on tenant-based Section 8 (Housing Choice Vouchers): HUD does not
publish voucher-holder addresses at all -- that's individual-household data
and is not public for privacy reasons. The closest public proxies are (a)
project-based assistance (the Multifamily Properties layer above -- present
in the data but not geocoded) and (b) PHA-level aggregate voucher counts
with no addresses (PublicHousing/MapServer, not pulled in here since it has
nothing point-level to add). Net: LIHTC is the one HUD subsidized-housing
source that is both available AND mappable for El Paso; Section 8 exists in
HUD's data but isn't addressable from public sources.

Only LIHTC ends up in the point layer below, since it's the only source
with real coordinates.
"""
import json
import statistics
from collections import defaultdict

from shapely.geometry import shape, Point
from shapely.strtree import STRtree

BASE = "/tmp/claude-0/-home-claude/b146bc85-bf48-59da-a6cf-542322a888e1/scratchpad/mva"

lihtc = json.load(open(f"{BASE}/lihtc_epc.geojson"))["features"]
mf = json.load(open(f"{BASE}/mf_epc.geojson"))["features"]


def norm_addr(a):
    return (a or "").strip().upper()


records = {}  # norm_addr -> record

for f in lihtc:
    p = f["properties"]
    key = norm_addr(p["STD_ADDR"])
    lon, lat = f["geometry"]["coordinates"]
    records[key] = {
        "name": p.get("PROJECT") or p.get("COMPANY"),
        "address": p.get("STD_ADDR"),
        "city": p.get("STD_CITY"),
        "zip": p.get("STD_ZIP5"),
        "lon": lon, "lat": lat,
        "total_units": p.get("N_UNITS") or 0,
        "assisted_units": p.get("LI_UNITS") or 0,
        "programs": ["LIHTC"],
        "hud_id": p.get("HUD_ID"),
    }

# The Multifamily Properties service returns null geometry for every
# record despite advertising a point layer -- not usable for the map, so
# it's summarized separately rather than merged into the mappable points.
mf_total_assisted_units = sum((f["properties"].get("TOTAL_ASSISTED_UNIT_COUNT") or 0) for f in mf)
print(f"HUD Multifamily (incl. project-based Section 8 / 202-811): {len(mf)} El Paso "
      f"properties, {mf_total_assisted_units} assisted units -- NOT geocoded by HUD, "
      f"county-level count only, not mapped.")

points = list(records.values())
print(f"Mappable subsidized-housing properties (LIHTC): {len(points)}, "
      f"total low-income units: {sum(p['assisted_units'] for p in points)}")

# Spatial join to block groups
bg_geo = json.load(open(f"{BASE}/bg_test.geojson"))
bg_shapes = []
bg_geoids = []
for f in bg_geo["features"]:
    bg_shapes.append(shape(f["geometry"]))
    bg_geoids.append(f["properties"]["GEOID"])
tree = STRtree(bg_shapes)

by_bg = defaultdict(lambda: {"properties": 0, "assisted_units": 0, "total_units": 0})
unmatched = 0
for p in points:
    pt = Point(p["lon"], p["lat"])
    idx = tree.query(pt, predicate="intersects")
    matched = False
    for i in idx:
        if bg_shapes[i].contains(pt) or bg_shapes[i].intersects(pt):
            geoid = bg_geoids[i]
            by_bg[geoid]["properties"] += 1
            by_bg[geoid]["assisted_units"] += p["assisted_units"]
            by_bg[geoid]["total_units"] += p["total_units"]
            matched = True
            break
    if not matched:
        unmatched += 1

print(f"Matched to block groups: {len(points) - unmatched}/{len(points)} "
      f"({len(by_bg)} block groups with at least one subsidized property)")

json.dump({
    "points": points,
    "by_bg": dict(by_bg),
    "mf_county_summary": {
        "n_properties": len(mf),
        "assisted_units": mf_total_assisted_units,
        "note": "HUD Multifamily Properties (incl. project-based Section 8, 202/811) "
                "for El Paso -- not geocoded by HUD, county total only, not mapped.",
    },
}, open(f"{BASE}/subsidized_housing.json", "w"), indent=0)
print(f"Wrote {BASE}/subsidized_housing.json")
