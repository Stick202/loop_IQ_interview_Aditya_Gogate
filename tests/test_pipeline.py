"""Extract atomicity, load idempotency, and a full offline run on recorded responses."""
import json

import httpx
import pytest

from pipeline import config, __main__ as cli
from pipeline.client import ApiError, OpenMeteoClient
from pipeline.extract import extract, request_params
from pipeline.load import load


def test_hourly_is_requested_in_utc_and_daily_in_local_time():
    s = config.load_settings()
    adelaide = next(x for x in config.load_locations() if x.location_id == "adelaide")
    assert request_params(s, adelaide, "hourly")["timezone"] == "GMT"
    assert request_params(s, adelaide, "daily")["timezone"] == "Australia/Adelaide"


def test_panels_face_north():
    # Open-Meteo: 0 is south, 180 is north. Every city is in the southern hemisphere.
    assert all(x.latitude < 0 and x.azimuth == 180 for x in config.load_locations())


def test_failed_run_lands_nothing(tmp_path):
    recorded = {}
    for f in config.SAMPLE_LANDING.glob("run_id=*/*.json"):
        doc = json.loads(f.read_text(encoding="utf-8"))
        recorded[doc["endpoint"], doc["location_id"]] = doc["payload"]
    ids = {str(x.latitude): x.location_id for x in config.load_locations()}

    def handler(request):
        q = request.url.params
        loc = ids[q["latitude"]]
        if loc == "auckland":  # the last city fails after five good ones
            return httpx.Response(400, json={"reason": "nope"})
        return httpx.Response(200, json=recorded["hourly" if "hourly" in q else "daily", loc])

    client = OpenMeteoClient("https://example.test", transport=httpx.MockTransport(handler))
    with pytest.raises(ApiError):
        extract(client, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_load_is_idempotent(tmp_path):
    db = tmp_path / "w.duckdb"
    assert load(config.SAMPLE_LANDING, db) == 12
    assert load(config.SAMPLE_LANDING, db) == 0


def test_end_to_end_in_one_process_on_recorded_responses(tmp_path, monkeypatch):
    monkeypatch.setenv("LANDING_DIR", str(config.SAMPLE_LANDING))
    monkeypatch.setenv("WAREHOUSE_PATH", str(tmp_path / "w.duckdb"))
    monkeypatch.setenv("REPORTS_DIR", str(tmp_path / "reports"))
    for name in ("load", "build", "report"):
        cli.step(name)

    with config.connect(tmp_path / "w.duckdb", read_only=True) as con:
        rows, cities = con.execute(
            "select count(*), count(distinct location_id) from silver.silver_hourly_weather"
        ).fetchone()
        assert (rows, cities) == (6 * 17 * 24, 6)
        assert con.execute("select count(*) from gold.rpt_energy_outlook").fetchone()[0] == 6
        # partial edge days carry no totals
        assert con.execute(
            "select count(*) from gold.fct_energy_daily "
            "where not is_complete and pv_yield_kwh_kwp is not null").fetchone()[0] == 0
    html = (tmp_path / "reports" / "energy_outlook.html").read_text(encoding="utf-8")
    assert all(c in html for c in
               ("Melbourne", "Sydney", "Brisbane", "Adelaide", "Perth", "Auckland"))
