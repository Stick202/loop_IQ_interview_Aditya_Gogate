"""Gold -> self-contained HTML report plus CSV extracts. Reads Gold only."""
from __future__ import annotations

from pathlib import Path

import duckdb
from jinja2 import Environment, FileSystemLoader

from . import config

EXTRACTS = {
    "energy_outlook": "select * from gold.rpt_energy_outlook order by location_id",
    "energy_daily": "select * from gold.fct_energy_daily order by location_id, local_date",
    "supply_risk_daily": "select * from gold.fct_supply_risk_daily order by location_id, local_date",
    "energy_hourly": "select * from gold.fct_energy_hourly order by location_id, valid_at_utc",
    "dim_location": "select * from gold.dim_location order by location_id",
}

DAILY = """
select l.city, f.local_date, f.lead_days, f.forecast_confidence, f.ghi_kwh_m2, f.gti_kwh_m2,
       f.pv_yield_kwh_kwp, f.wind_cf_100m, f.wind_cf_200m, f.wind_power_density_100m_wm2,
       f.wind_power_density_200m_wm2, f.wind_gust_max_ms, f.sunshine_hours,
       r.supply_risk_score, r.risk_band
from gold.fct_energy_daily f
join gold.dim_location l using (location_id)
join gold.fct_supply_risk_daily r using (location_id, local_date)
join gold.rpt_energy_outlook o using (location_id)
where f.local_date between o.window_start and o.window_end
order by l.city, f.local_date
"""

# Radiation is the mean of the preceding hour, so it is plotted at the hour it starts.
PROFILE = """
with hours as (
    select h.location_id, h.valid_at_local, h.pv_yield_kwh_kwp, h.wind_cf_100m
    from gold.fct_energy_hourly h
    join gold.rpt_energy_outlook o using (location_id)
    where h.local_date between o.window_start and o.window_end
),
solar as (
    select location_id, hour(valid_at_local - interval 1 hour) as hr, avg(pv_yield_kwh_kwp) as v
    from hours group by all
),
wind as (
    select location_id, hour(valid_at_local) as hr, avg(wind_cf_100m) as v
    from hours group by all
)
select l.city, hr, s.v as solar, w.v as wind
from solar s join wind w using (location_id, hr) join gold.dim_location l using (location_id)
order by l.city, hr
"""


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    names = [c[0] for c in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def _profiles(rows: list[dict]) -> tuple[list[dict], float]:
    """SVG polyline points for each city's average day, on one shared scale."""
    top = max(max(r["solar"], r["wind"]) for r in rows)
    top = max(0.1, (int(top * 10) + 1) / 10)  # next 10% step
    left, right, upper, lower = 34, 290, 10, 120

    def points(city_rows, key):
        return " ".join(
            f"{left + r['hr'] * (right - left) / 23:.1f},"
            f"{lower - r[key] / top * (lower - upper):.1f}"
            for r in city_rows
        )

    panels = []
    for city in sorted({r["city"] for r in rows}):
        cr = [r for r in rows if r["city"] == city]
        panels.append({
            "city": city,
            "solar": points(cr, "solar"),
            "wind": points(cr, "wind"),
            "values": [[r["hr"], round(r["solar"], 4), round(r["wind"], 4)] for r in cr],
        })
    return panels, top


def build_context(con: duckdb.DuckDBPyConnection) -> dict:
    outlook = _rows(con, "select * from gold.rpt_energy_outlook order by city")
    if not outlook:
        raise RuntimeError("no day is complete for every city; nothing to report")
    daily = _rows(con, DAILY)
    issued = con.execute(
        "select max(retrieved_at_utc) from gold.fct_energy_hourly"
    ).fetchone()[0]
    panels, top = _profiles(_rows(con, PROFILE))

    dates = sorted({r["local_date"] for r in daily})
    grid: dict = {}
    for r in daily:
        grid.setdefault(r["city"], {})[r["local_date"]] = r
    # lead time can differ by city near midnight; take the shorter one
    confidence = {d: min((r["lead_days"], r["forecast_confidence"])
                         for r in daily if r["local_date"] == d)[1] for d in dates}

    peak = max(daily, key=lambda r: r["supply_risk_score"])
    matched = [o for o in outlook if o["days_200m"]]
    uplift = None
    if matched:
        low = sum(o["wind_cf_100m_matched"] for o in matched)
        uplift = sum(o["wind_cf_200m_matched"] for o in matched) / low - 1 if low else None

    return {
        "issued": issued,
        "start": dates[0], "end": dates[-1], "days": len(dates), "dates": dates,
        "days_200m": outlook[0]["days_200m"],
        "outlook": outlook,
        "by_solar": sorted(outlook, key=lambda o: -o["pv_yield_kwh_kwp_day"]),
        "by_wind": sorted(outlook, key=lambda o: -o["wind_cf_100m_matched"] if matched
                          else -o["wind_cf_100m"]),
        "by_risk": sorted(outlook, key=lambda o: -o["supply_risk_score_avg"]),
        "grid": grid, "confidence": confidence, "daily": daily,
        "max_pv": max(r["pv_yield_kwh_kwp"] for r in daily),
        "max_wind": max(r["wind_cf_100m"] for r in daily) or 1,
        "peak": peak, "uplift": uplift,
        "gti_below_ghi": all(o["gti_kwh_m2_day"] < o["ghi_kwh_m2_day"] for o in outlook),
        "panels": panels, "top": top,
        "vars": _dbt_vars(),
    }


def _dbt_vars() -> dict:
    import yaml
    return yaml.safe_load((config.DBT_DIR / "dbt_project.yml").read_text(encoding="utf-8"))["vars"]


def report() -> Path:
    out = config.reports_dir()
    out.mkdir(parents=True, exist_ok=True)
    with config.connect(read_only=True) as con:
        context = build_context(con)
        for name, sql in EXTRACTS.items():
            target = (out / f"{name}.csv").as_posix().replace("'", "''")
            con.execute(f"copy ({sql}) to '{target}' (header, delimiter ',')")
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=True, trim_blocks=True, lstrip_blocks=True,
    )
    path = out / "energy_outlook.html"
    path.write_text(env.get_template("report.html").render(**context), encoding="utf-8")
    return path
