# Solar and wind outlook: an Open-Meteo medallion pipeline

A local data pipeline that pulls about 16 days of hourly forecasts for Melbourne, Sydney,
Brisbane, Adelaide, Perth and Auckland from the
[Open-Meteo API](https://open-meteo.com/en/docs), and reports on renewable energy potential.

See a finished report without running anything: download
[docs/sample_report/energy_outlook.html](docs/sample_report/energy_outlook.html) and open it
in a browser.

## The business problem

> **Over the next two weeks, where and when will solar and wind generate well, and on which
> days is renewable supply at risk?**

The audience is an energy planner or trader with solar and wind exposure across these six
cities. They would use the answer to plan storage and backup supply, schedule maintenance
in low-output windows, and decide where generation is worth watching.

| Question | Answered by | Report section |
|---|---|---|
| 1. Which city has the strongest solar yield? | `fct_energy_daily.pv_yield_kwh_kwp` (from GHI and GTI) | Solar yield potential |
| 2. Which city has the strongest wind, and how much does going from 100 m to 200 m add? | `fct_energy_daily.wind_cf_100m`, `wind_cf_200m`, power density | Wind potential at 100 m and 200 m |
| 3. On which days will solar and wind both be weak (dark, calm or stormy)? | `fct_supply_risk_daily.supply_risk_score`, `risk_band` | Renewable supply risk |
| 4. Do solar and wind cover different hours of the day? | `fct_energy_hourly`, by local hour | Average day |
| 5. How far ahead can each day be trusted? | `fct_energy_daily.forecast_confidence` | Confidence row under each grid |

The final answer is `gold.rpt_energy_outlook`: one row per city, compared over the same set of
complete days.

## What is ingested

Each run makes 12 calls to the Open-Meteo forecast endpoint: two per city.

| Call | Time zone | Window | What it returns |
|---|---|---|---|
| Hourly | UTC | yesterday plus 16 forecast days (408 hours) | 14 variables, below |
| Daily | the city's own | 16 days | 9 API-aggregated variables, below |

**Hourly variables**

| Group | Variables | Used for |
|---|---|---|
| Solar | `shortwave_radiation` (GHI), `global_tilted_irradiance` (GTI, per-city tilt, north-facing), `direct_normal_irradiance`, `diffuse_radiation` | PV yield |
| Wind | `wind_speed_100m`, `wind_speed_200m` | Capacity factor and power density at both heights |
| Wind, checks | `wind_speed_10m`, `wind_speed_80m`, `wind_speed_120m` | Checking the undocumented 100 m values |
| Wind, risk | `wind_gusts_10m`, `wind_direction_100m` | Gust hazard in the risk score |
| Atmosphere | `temperature_2m`, `surface_pressure`, `cloud_cover` | Air density, PV cell temperature |

**Daily variables:** `shortwave_radiation_sum` (to reconcile our hourly GHI totals),
`sunrise`, `sunset` (to check the clock), `sunshine_duration`, `daylight_duration`,
`temperature_2m_max`, `temperature_2m_min`, `wind_speed_10m_max`, `wind_gusts_10m_max`.

**Tables built from it** (row counts from one run, the recorded sample)

| Layer | Table | Grain | Rows |
|---|---|---|---|
| Reference | `reference.locations` | city: coordinates, time zone, panel tilt | 6 |
| Bronze | `bronze.raw_open_meteo` | run × call × city, raw JSON | 12 |
| Silver | `silver.silver_hourly_weather` | city × UTC hour | 2,448 |
| Silver | `silver.silver_daily_weather` | city × local date | 91 |
| Gold | `gold.dim_location` | city, plus the model grid cell used | 6 |
| Gold | `gold.fct_energy_hourly` | city × hour: PV yield, wind capacity factor, power density | 2,448 |
| Gold | `gold.fct_energy_daily` | city × local date, with completeness flags | 108 |
| Gold | `gold.fct_supply_risk_daily` | city × complete local date: score and band | 96 |
| Gold | `gold.rpt_energy_outlook` | city, over the shared window | 6 |

Bronze grows by 12 rows on each run. Silver and Gold keep only the newest forecast for each
hour.

## Run it

You need Python 3.12 (3.13 and 3.14 are untested). No API key, server or Docker.

```bash
# macOS / Linux
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pipeline run
```

```powershell
# Windows PowerShell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pipeline run
```

On Windows, clone into a short path (under about 90 characters) unless long paths are enabled;
a dbt dependency has very long file names and `pip install` fails otherwise.

With [uv](https://docs.astral.sh/uv/): `uv venv --python 3.12`, then
`uv pip install -r requirements.txt`. With make: `make setup run`.

Then open `reports/energy_outlook.html`. A full run takes about 20 seconds.

| Command (`python -m pipeline …`) | What it does |
|---|---|
| `run` | Extract, load, build and test with dbt, write the report |
| `sample` | The same, offline, from recorded API responses (output in `reports/sample/`) |
| `extract`, `load`, `build`, `report` | One step |
| `docs` | dbt docs with lineage, as one file: `dbt/target/static_index.html` |

Python tests: `python -m pytest -q` (no network needed).

## Architecture

```mermaid
flowchart LR
    API[Open-Meteo API] -->|httpx, retries, contract check| L[Landing: JSON per run]
    L --> B[(Bronze: raw payloads)]
    B -->|dbt| S[(Silver: typed, deduplicated)]
    S -->|dbt| G[(Gold: facts, dimension, risk)]
    G --> R[HTML report and CSVs]
```

| Layer | Objects | Rule |
|---|---|---|
| Landing | `data/landing/run_id=…/*.json` | Immutable. A run appears only if all 12 requests succeed. |
| Bronze | `raw_open_meteo` | Payload unchanged, plus run, URL, time and hash. Append-only; reloading adds nothing. |
| Silver | `silver_hourly_weather`, `silver_daily_weather` | Typed, one row per city and hour (or day). The newest forecast wins. UTC and local time. |
| Gold | `dim_location`, `fct_energy_hourly`, `fct_energy_daily`, `fct_supply_risk_daily`, `rpt_energy_outlook` | Energy metrics. Totals only for complete local days. |

Everything lives in one DuckDB file, `data/warehouse.duckdb`. Silver and Gold are rebuilt in
full on each run; at a few thousand rows that is simpler and safer than incremental models.

### Repository layout

```
config/pipeline.yml      API settings; variables with their expected units
pipeline/                client, extract, load, transform (dbt), report, CLI runner
dbt/seeds/locations.csv  The six cities; used by both ingestion and dim_location
dbt/models/silver|gold/  Models, with tests beside them in YAML
dbt/tests/               Custom data tests
tests/                   pytest suite and recorded API responses
docs/sample_report/      A finished report
docs/ai-evidence/        Screenshots of the AI conversations
```

## What the API does that the design handles

Each of these came from probing the live API or from a failing test.

| Finding | Response |
|---|---|
| An unknown variable returns HTTP 200, nulls and the unit `"undefined"` | Every response is checked for units, lengths, hourly spacing and all-null columns before it lands |
| With `timezone=Australia/Adelaide` (UTC+10:30), whole-hour values are stamped 30 minutes early | Hourly data is requested in UTC; Silver derives local time |
| 100 m and 200 m wind are returned but not in the published variable list. 100 m stays within 0.1 m/s of the 80/120 m midpoint | 80 m and 120 m are kept too, and a test checks 100 m against them |
| 200 m wind ends about a day before the other heights | Never imputed. 100 m and 200 m are compared on matched days only |
| Forecast days end on UTC boundaries, so the first and last local days are partial | `is_complete` compares hours present with hours expected (23 or 25 on DST days); partial days have null totals |
| Stray ±1 W/m² GHI at night | Small negatives are clamped to 0 and flagged in Silver; Bronze keeps the raw value |
| Radiation is the mean of the preceding hour | Hourly profiles plot it at the hour it starts |
| Azimuth 0 is south, 180 is north | Panels use 180 (north-facing), tilt near latitude |

## Metrics

| Metric | Definition |
|---|---|
| PV yield (kWh/kWp) | GTI/1000 × 0.86 × temperature correction (−0.35%/°C above 25 °C cell; NOCT 45 °C) |
| Wind power density (W/m²) | ½ρv³, with ρ from surface pressure and temperature |
| Wind capacity factor | Generic cubic power curve: cut-in 3, rated 12, cut-out 25 m/s, density-corrected |
| Supply risk (0–100) | 45 × solar shortfall against 5 kWh/kWp + 45 × wind shortfall against 0.35 CF + 10 × gust hazard (17–28 m/s). Low < 35, moderate < 60, high ≥ 60 |
| Forecast confidence | Lead time only: high to 6 days, medium to 10, low beyond |

All constants are `vars` in [dbt/dbt_project.yml](dbt/dbt_project.yml).

## Data quality

`dbt build` runs 43 data tests and 2 unit tests in dependency order, so a bad layer stops the
ones after it. Beyond keys, ranges and relationships:

- hourly GHI summed to days must match the API's own daily total within 2%
- no sunlight in hours that fall wholly outside sunrise to sunset
- unit tests pin the dedup rule, Adelaide's half-hour offset, the turbine curve and the PV
  formula, including that missing irradiance stays null and does not become zero

## Limits

- These are city-centre forecasts over two weeks. They compare near-term conditions and are
  not a site or long-term resource assessment.
- A run covers 15 or 16 complete local days, depending on the time of day in UTC.
- The turbine, the panel and the risk weights are generic choices, not calibrated to a fleet.
- Wind at each hour is an instantaneous value, treated as that hour's mean.
- The 200 m capacity factor uses the same turbine as 100 m, so it shows the resource gain
  from height, not a real machine.

## AI use

Built with Claude Code. [docs/AI_USAGE.md](docs/AI_USAGE.md) covers how the brief became
the code, what the AI found and fixed, and which assumptions are mine to defend. Screenshots
of the conversations are in [docs/ai-evidence/](docs/ai-evidence/).

Weather data by [Open-Meteo.com](https://open-meteo.com/), CC BY 4.0.
