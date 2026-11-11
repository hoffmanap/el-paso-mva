"""
Build the final map geojson from ALL 598 block groups, not just the 557
with complete indicator coverage. Block groups missing one or more of the
six clustering indicators keep whatever data they do have and are flagged
data_sufficient=false, instead of being dropped from the map entirely.
"""
import json

BASE = "/tmp/claude-0/-home-claude/b146bc85-bf48-59da-a6cf-542322a888e1/scratchpad/mva"

bg_geo = json.load(open(f"{BASE}/bg_test.geojson"))
bg_table = {r["GEOID"]: r for r in json.load(open(f"{BASE}/bg_table.json"))}
mva = {r["GEOID"]: r for r in json.load(open(f"{BASE}/mva_result.json"))["block_groups"]}
subsidized_by_bg = json.load(open(f"{BASE}/subsidized_housing.json"))["by_bg"]

TYPE_LABELS = {
    "A": "Highest Value / Strongest Market", "B": "Strong Market",
    "C": "Moderate-Strong Market", "D": "Moderate Market",
    "E": "Transitional / Softening Market", "F": "Distressed / Weakest Market",
}

feats = []
n_scored = 0
n_insufficient = 0
for f in bg_geo["features"]:
    geoid = f["properties"]["GEOID"]
    raw = bg_table.get(geoid)
    if raw is None:
        continue  # BG not in ACS/geometry universe at all -- genuinely nothing to show
    scored = mva.get(geoid)
    if scored:
        props = dict(scored)
        props["data_sufficient"] = True
        props["n_sales_bg"] = raw.get("n_sales_bg", 0)
        n_scored += 1
    else:
        # Carry whatever raw indicators exist, with no market_type assigned
        props = {
            "GEOID": geoid,
            "NAME": raw.get("NAME"),
            "tract": raw.get("tract"),
            "market_type": None,
            "market_type_label": "Insufficient data",
            "composite_score": None,
            "median_ppsf": raw.get("median_ppsf"),
            "median_dom": raw.get("median_dom"),
            "n_sales": raw.get("n_sales"),
            "n_sales_bg": raw.get("n_sales_bg", 0),
            "owner_occ_rate": raw.get("owner_occ_rate"),
            "vacancy_rate": raw.get("vacancy_rate"),
            "median_hh_income": raw.get("median_hh_income"),
            "pre1960_share": raw.get("pre1960_share"),
            "permit_count": raw.get("permit_count"),
            "permits_per_1000_units": raw.get("permits_per_1000_units"),
            "violation_count": raw.get("violation_count"),
            "violations_per_1000_units": raw.get("violations_per_1000_units"),
            "total_units_acs": raw.get("total_units_acs"),
            "data_sufficient": False,
        }
        # note which of the 6 clustering indicators are actually missing
        missing = []
        for label, field in [("$/sqft", "median_ppsf"), ("days-on-market", "median_dom"),
                              ("permits", "permits_per_1000_units"), ("owner-occ", "owner_occ_rate"),
                              ("vacancy", "vacancy_rate"), ("violations", "violations_per_1000_units")]:
            if props.get(field) is None:
                missing.append(label)
        props["missing_indicators"] = missing
        n_insufficient += 1

    sub = subsidized_by_bg.get(geoid, {})
    props["subsidized_properties"] = sub.get("properties", 0)
    props["subsidized_units"] = sub.get("assisted_units", 0)

    feats.append({"type": "Feature", "geometry": f["geometry"], "properties": props})

out = {"type": "FeatureCollection", "features": feats}
json.dump(out, open(f"{BASE}/mva_map.geojson", "w"))
print(f"wrote {len(feats)} features ({n_scored} scored, {n_insufficient} insufficient-data)")
