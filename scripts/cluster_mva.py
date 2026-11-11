"""
Cluster block groups into an internally-referenced MVA market typology.
Indicators (standard MVA set, adapted to available El Paso data):
  + median_ppsf          (higher = stronger)
  - median_dom           (higher = weaker, slower-moving market)
  + permits_per_1000     (higher = stronger, more new construction investment)
  + owner_occ_rate       (higher = stronger)
  - vacancy_rate         (higher = weaker)
  - violations_per_1000  (higher = weaker, more physical distress)

Standardize (z-score), combine into a single composite strength score,
then bucket into 6 market types (A=strongest ... F=weakest) by
composite-score quantile -- the same "internally-referenced index"
approach RF describes, run with KMeans for a true multi-dimensional
cluster rather than a single composite where possible.
"""
import json, statistics, math

BASE = "/tmp/claude-0/-home-claude/b146bc85-bf48-59da-a6cf-542322a888e1/scratchpad/mva"
rows = json.load(open(f"{BASE}/bg_table.json"))

# keep only BGs with at least ACS + some housing stock (drop slivers/non-residential BGs)
rows = [r for r in rows if r["total_units_acs"] and r["total_units_acs"] >= 20]
print("usable BGs:", len(rows))

INDICATORS = [
    ("median_ppsf", +1),
    ("median_dom", -1),
    ("permits_per_1000_units", +1),
    ("owner_occ_rate", +1),
    ("vacancy_rate", -1),
    ("violations_per_1000_units", -1),
]

def zscores(rows, field):
    vals = [r[field] for r in rows if r.get(field) is not None and not (isinstance(r[field], float) and math.isnan(r[field]))]
    if len(vals) < 2:
        return {}
    mean = statistics.mean(vals)
    sd = statistics.pstdev(vals) or 1.0
    return {id(r): (r[field] - mean) / sd for r in rows if r.get(field) is not None}

z_by_field = {f: zscores(rows, f) for f, _ in INDICATORS}

for r in rows:
    comps = []
    for f, sign in INDICATORS:
        z = z_by_field[f].get(id(r))
        if z is not None:
            comps.append(sign * z)
    r["_z_components"] = comps
    r["composite_score"] = sum(comps) / len(comps) if comps else None

scored = [r for r in rows if r["composite_score"] is not None]
scored.sort(key=lambda r: r["composite_score"], reverse=True)
print("scored BGs:", len(scored))

# ---- Try real multivariate clustering (KMeans) on the z-score vectors ----
try:
    import numpy as np
    from sklearn.cluster import KMeans

    fields = [f for f, _ in INDICATORS]
    X = []
    valid = []
    for r in scored:
        vec = []
        ok = True
        for f, sign in INDICATORS:
            z = z_by_field[f].get(id(r))
            if z is None:
                ok = False
                break
            vec.append(sign * z)
        if ok:
            X.append(vec)
            valid.append(r)
    X = np.array(X)
    k = 6
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(X)
    # order clusters by mean composite score (descending) so label A = strongest
    cluster_mean = {}
    for ci in range(k):
        idxs = [i for i, lab in enumerate(km.labels_) if lab == ci]
        cluster_mean[ci] = np.mean([valid[i]["composite_score"] for i in idxs])
    order = sorted(cluster_mean, key=lambda c: cluster_mean[c], reverse=True)
    rank = {cid: i for i, cid in enumerate(order)}
    letters = "ABCDEF"
    for i, r in enumerate(valid):
        r["market_type"] = letters[rank[km.labels_[i]]]
    print("KMeans clustering applied. Cluster sizes:",
          {letters[rank[c]]: int((km.labels_ == c).sum()) for c in range(k)})
    METHOD = "kmeans"
except ImportError:
    METHOD = "quantile"
    print("sklearn/numpy unavailable, falling back to quantile bucketing")
    n = len(scored)
    letters = "ABCDEF"
    for i, r in enumerate(scored):
        bucket = min(int(i / n * 6), 5)
        r["market_type"] = letters[bucket]
    valid = scored

TYPE_LABELS = {
    "A": "Highest Value / Strongest Market",
    "B": "Strong Market",
    "C": "Moderate-Strong Market",
    "D": "Moderate Market",
    "E": "Transitional / Softening Market",
    "F": "Distressed / Weakest Market",
}

out = []
for r in valid:
    out.append({
        "GEOID": r["GEOID"],
        "NAME": r["NAME"],
        "tract": r["tract"],
        "market_type": r["market_type"],
        "market_type_label": TYPE_LABELS[r["market_type"]],
        "composite_score": round(r["composite_score"], 3),
        "median_ppsf": r["median_ppsf"],
        "median_dom": r["median_dom"],
        "n_sales": r["n_sales"],
        "owner_occ_rate": r["owner_occ_rate"],
        "vacancy_rate": r["vacancy_rate"],
        "median_hh_income": r["median_hh_income"],
        "pre1960_share": r["pre1960_share"],
        "permit_count": r["permit_count"],
        "permits_per_1000_units": r["permits_per_1000_units"],
        "violation_count": r["violation_count"],
        "violations_per_1000_units": r["violations_per_1000_units"],
        "total_units_acs": r["total_units_acs"],
    })

json.dump({"method": METHOD, "block_groups": out}, open(f"{BASE}/mva_result.json", "w"), indent=1)
print("method used:", METHOD)
print("wrote mva_result.json with", len(out), "block groups")

from collections import Counter
print(Counter(r["market_type"] for r in out))
