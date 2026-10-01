"""Build the offline US station catalog from the supplied CSV and GeoNames US.zip.

Usage: python scripts/build_station_catalog.py /path/to/US.zip
GeoNames postal locations are used as city-level estimates, not pump coordinates.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
US_STATES = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)


def normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_value.lower())


def main(postal_zip: Path) -> None:
    postal_points: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    with zipfile.ZipFile(postal_zip) as archive:
        lines = archive.read("US.txt").decode("utf-8").splitlines()
    for line in lines:
        columns = line.split("\t")
        if columns[4] in US_STATES:
            postal_points[(normalize(columns[2]), columns[4])].append(
                (float(columns[9]), float(columns[10]))
            )

    cities = {}
    for (name, state), points in postal_points.items():
        cities[f"{name},{state}"] = [
            round(statistics.median(point[0] for point in points), 5),
            round(statistics.median(point[1] for point in points), 5),
        ]

    stations = []
    missing = set()
    with (ROOT / "data/fuel-prices.csv").open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            state = row["State"].strip().upper()
            if state not in US_STATES:
                continue
            city = row["City"].strip()
            key = f"{normalize(city)},{state}"
            point = cities.get(key)
            if point is None:
                missing.add((city, state))
                continue
            stations.append(
                {
                    "id": row["OPIS Truckstop ID"].strip(),
                    "name": row["Truckstop Name"].strip(),
                    "address": row["Address"].strip(),
                    "city": city,
                    "state": state,
                    "price": row["Retail Price"].strip(),
                    "lat": point[0],
                    "lon": point[1],
                }
            )

    if missing:
        raise SystemExit(f"Missing GeoNames coordinates for {len(missing)} cities: {sorted(missing)[:10]}")
    (ROOT / "data/cities.json").write_text(json.dumps(cities, separators=(",", ":")))
    (ROOT / "data/stations.json").write_text(json.dumps(stations, separators=(",", ":")))
    print(f"Wrote {len(stations)} US fuel rows and {len(cities)} US city locations")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
