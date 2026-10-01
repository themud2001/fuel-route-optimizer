"""Small read-only indexes generated from the assessment CSV."""

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def normalize(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_value.lower())


@lru_cache(maxsize=1)
def cities() -> dict:
    return json.loads((DATA_DIR / "cities.json").read_text())


@lru_cache(maxsize=1)
def stations() -> list[dict]:
    return json.loads((DATA_DIR / "stations.json").read_text())


def resolve_city(value: str) -> tuple[float, float]:
    parts = value.rsplit(",", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise ValueError("Use a city and two-letter state, such as 'Chicago, IL'.")
    key = f"{normalize(parts[0])},{parts[1].strip().upper()}"
    point = cities().get(key)
    if point is None:
        raise ValueError(f"US city not found: {value!r}.")
    return (float(point[1]), float(point[0]))  # longitude, latitude
