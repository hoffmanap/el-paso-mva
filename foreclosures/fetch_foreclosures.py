"""
Snapshot El Paso County's upcoming-foreclosure-sale map feed.

The county's Foreclosures Search form (apps.epcountytx.gov/publicrecords/
Foreclosures) is gated by a Cloudflare Turnstile CAPTCHA and its results
table only exposes legal descriptions (Subdivision/Lot/Block/Unit/Tract) --
no address, no parcel ID, no coordinates.

The companion "Foreclosure Map" page at the same site, however, server-
renders a JS array (`var m = [...]`) with every record scheduled for the
*next* posted sale date(s), and it is NOT behind Turnstile. Each record
includes PropertyId (the EPCAD parcel ID -- a direct join key to your
parcel data), a geocoded lat/lon, street/city/zip, and the sale date.

Texas law requires a Notice of Trustee's Sale to be posted >= 21 days
before the first-Tuesday sale date, so this feed is effectively "the next
1-2 months of scheduled sales," re-populated on a rolling basis. It is NOT
a historical archive -- run this on a schedule (monthly is plenty, since
sales are posted weeks ahead and stay listed until their date passes) and
append to a running file to build real history over time.

Usage:
    python3 fetch_foreclosures.py --out foreclosures_history.csv
Running it repeatedly is safe: records are de-duplicated by ForeclosureId.
"""
import argparse
import csv
import json
import os
import re
import urllib.request

MAP_URL = "https://apps.epcountytx.gov/publicrecords/Foreclosures/Map"
FIELDS = ["ForeclosureId", "InstrumentNumber", "PropertyId", "Street",
          "City", "ZipCode", "SaleDate", "Latitude", "Longitude",
          "snapshot_date"]


def fetch_current():
    req = urllib.request.Request(MAP_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    m = re.search(r"var m = (\[.*?\]);", html, re.S)
    if not m:
        raise RuntimeError("Could not find the `var m = [...]` data array in the page -- "
                            "the county may have changed the page structure.")
    return json.loads(m.group(1))


def load_existing(path):
    if not os.path.exists(path):
        return {}
    with open(path, newline="") as f:
        return {row["ForeclosureId"]: row for row in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="foreclosures_history.csv")
    args = ap.parse_args()

    import datetime
    today = datetime.date.today().isoformat()

    existing = load_existing(args.out)
    records = fetch_current()
    new_count = 0
    for r in records:
        fid = str(r["ForeclosureId"])
        if fid not in existing:
            new_count += 1
        row = {k: r.get(k, "") for k in FIELDS if k != "snapshot_date"}
        row["ForeclosureId"] = fid
        row["snapshot_date"] = today
        existing[fid] = row  # overwrite -- keeps the most recent snapshot_date seen

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in existing.values():
            w.writerow(row)

    print(f"Fetched {len(records)} currently-posted sales ({new_count} new). "
          f"Archive now holds {len(existing)} unique ForeclosureId records at {args.out}.")


if __name__ == "__main__":
    main()
