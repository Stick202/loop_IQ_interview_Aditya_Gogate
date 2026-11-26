"""Paths and settings. Every data path can be overridden by environment variable."""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DBT_DIR = ROOT / "dbt"
SAMPLE_LANDING = ROOT / "tests" / "fixtures" / "landing"


def landing_dir() -> Path:
    return Path(os.environ.get("LANDING_DIR", ROOT / "data" / "landing"))


def warehouse_path() -> Path:
    return Path(os.environ.get("WAREHOUSE_PATH", ROOT / "data" / "warehouse.duckdb"))


def reports_dir() -> Path:
    return Path(os.environ.get("REPORTS_DIR", ROOT / "reports"))


@dataclass(frozen=True)
class Location:
    location_id: str
    latitude: float
    longitude: float
    timezone: str
    tilt: float
    azimuth: float


def load_locations() -> list[Location]:
    with open(DBT_DIR / "seeds" / "locations.csv", newline="", encoding="utf-8") as f:
        return [
            Location(
                location_id=r["location_id"],
                latitude=float(r["latitude"]),
                longitude=float(r["longitude"]),
                timezone=r["timezone"],
                tilt=float(r["panel_tilt_deg"]),
                azimuth=float(r["panel_azimuth_deg"]),
            )
            for r in csv.DictReader(f)
        ]


def load_settings() -> dict:
    return yaml.safe_load((ROOT / "config" / "pipeline.yml").read_text(encoding="utf-8"))
