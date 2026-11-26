"""API -> landing zone: one immutable JSON file per (run, endpoint, location)."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .client import OpenMeteoClient, check_contract

log = logging.getLogger(__name__)


def request_params(settings: dict, loc: config.Location, endpoint: str) -> dict:
    api = settings["api"]
    params = {
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "timeformat": "unixtime",
        "wind_speed_unit": "ms",
        "forecast_days": api["forecast_days"],
        endpoint: ",".join(settings[endpoint]),
    }
    if endpoint == "hourly":
        # Always UTC. With a half-hour zone (Adelaide) the API stamps whole-hour
        # values 30 minutes early, so local time is derived in Silver instead.
        params |= {
            "timezone": "GMT",
            "past_days": api["past_days"],
            "tilt": loc.tilt,
            "azimuth": loc.azimuth,
        }
    else:
        params["timezone"] = loc.timezone  # daily aggregates need local-day boundaries
    return params


def extract(client: OpenMeteoClient | None = None, landing: Path | None = None) -> str:
    """Fetch every location. A run is published only if every request succeeds."""
    settings = config.load_settings()
    api = settings["api"]
    landing = landing or config.landing_dir()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    final = landing / f"run_id={run_id}"
    partial = landing / f"_partial_{run_id}"
    partial.mkdir(parents=True)

    client = client or OpenMeteoClient(
        api["base_url"], api["timeout_seconds"], api["max_attempts"], api["backoff_seconds"]
    )
    try:
        with client:
            for loc in config.load_locations():
                for endpoint in ("hourly", "daily"):
                    payload, url, status = client.get(request_params(settings, loc, endpoint))
                    check_contract(payload, endpoint, settings[endpoint])
                    doc = {
                        "run_id": run_id,
                        "endpoint": endpoint,
                        "location_id": loc.location_id,
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "request_url": url,
                        "http_status": status,
                        "payload": payload,
                    }
                    (partial / f"{endpoint}_{loc.location_id}.json").write_text(
                        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
                    )
                log.info("fetched %s", loc.location_id)
        partial.rename(final)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return run_id
