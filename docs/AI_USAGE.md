# How AI was used on this assignment

**Tool:** Claude Code (model: Claude Opus 5.5), in the VS Code extension, working directly in
this repository on Windows 11.

**Split of work:** I set the business problem, the cities, the scope and the tech stack. The AI
probed the API, wrote the code, ran it, and fixed what the tests caught. I reviewed the result
and steered with follow-up requests.

Screenshots of the conversation are in [ai-evidence/](ai-evidence/).

---

## 1. What I asked for

The brief I gave, with the assignment PDF attached:

| Area | My instruction |
|---|---|
| Locations | Melbourne, Sydney, Brisbane, Adelaide, Perth and Auckland only |
| Data | About 16 days of hourly data, plus a handful of daily variables |
| Silver | Typed, deduplicated hourly rows |
| Gold | Daily facts, a location dimension, and a simple risk or comfort score |
| Output | An energy report: solar yield potential from GHI and GTI, and wind potential from 100 m and 200 m wind speed |
| Ingestion | Python with requests, or httpx with retries |
| Warehouse | DuckDB: a single file, no server, nothing beyond pip |
| Transformations | dbt-duckdb for Silver and Gold, with tests and docs |
| Orchestration | A simple Makefile or a small Python runner; Dagster or Prefect only as a bonus |

## 2. How each instruction was met

| Instruction | What was built | Where |
|---|---|---|
| Six cities | One seed file feeds both ingestion and `dim_location`. "Adeilade" and "Aukland" in my prompt were read as Adelaide and Auckland | `dbt/seeds/locations.csv` |
| ~16 days hourly | `forecast_days=16` plus one past day, so the first local day is complete in every time zone | `config/pipeline.yml` |
| Daily variables | 9 daily variables, including sunrise, sunset, sunshine duration and daily radiation totals | `config/pipeline.yml` |
| Silver: typed, deduplicated hourly | One row per city and UTC hour; the newest forecast wins; UTC and local timestamps | `dbt/models/silver/` |
| Gold: daily facts | `fct_energy_daily`, with flags for complete days | `dbt/models/gold/` |
| Gold: location dimension | `dim_location`: configured coordinates plus the model grid cell the API used | `dbt/models/gold/` |
| Gold: risk or comfort score | A renewable supply risk score (0–100). Chosen over comfort because it answers an energy question | `fct_supply_risk_daily.sql` |
| Solar from GHI and GTI | PV yield per kWp from GTI, with temperature losses; GHI kept for comparison | `fct_energy_hourly.sql` |
| Wind from 100 m and 200 m | Capacity factor and power density at both heights, compared on matched days | `fct_energy_hourly.sql`, `rpt_energy_outlook.sql` |
| Energy report | Self-contained HTML report plus CSV extracts | `pipeline/report.py`, `docs/sample_report/` |
| httpx with retries | Exponential backoff, honours `Retry-After`, no retry on 4xx | `pipeline/client.py` |
| DuckDB single file | `data/warehouse.duckdb` holds every layer | `pipeline/load.py` |
| dbt with tests and docs | 43 data tests, 2 unit tests, column docs, `python -m pipeline docs` for lineage | `dbt/` |
| Makefile or Python runner | Both: a Python runner as the main entry point, and a thin Makefile around it | `pipeline/__main__.py`, `Makefile` |
| Dagster or Prefect | Not added. The brief called it overkill, and the runner is enough at this size | – |

The business question that ties these together is written up in the
[README](../README.md#the-business-problem).

## 3. How the work went

### Step 1: Probe the API before writing code

The AI called the live API first and compared the responses with the documentation. This
changed the design:

| Finding | Design change |
|---|---|
| An unknown variable returns HTTP 200, all nulls and unit `"undefined"`; a status check alone misses it | A contract check on every response: units, array lengths, hourly spacing, no all-null columns |
| With `timezone=Australia/Adelaide` (UTC+10:30), values are stamped 30 minutes early | Hourly data is requested in UTC; local time is derived in Silver |
| 100 m and 200 m wind are returned but not in the documented variable list | 80 m and 120 m kept as a cross-check, a dbt test compares them, and the report labels both heights as model estimates |
| 200 m wind ends about a day early | No imputation; 100 m and 200 m are compared on the same days only |
| `end_date` cannot go past today + 15 days in UTC | A run gives 15 or 16 complete local days; partial days are flagged and get no totals |
| Azimuth 0 means south, 180 means north | Panels use 180 (north-facing, correct for the southern hemisphere) |

### Step 2: Build layer by layer and run each one

Ingestion was run against the live API before Silver was written, Silver before Gold, and Gold
before the report. Each step was checked against real data, not just compiled.

### Step 3: Problems caught and fixed

| Problem | How it was caught | Fix |
|---|---|---|
| Stray −1 W/m² radiation at night, in 4 cities at the same hour | dbt range test failed | Clamp values between −5 and 0 to 0 in Silver and flag the row; Bronze keeps the raw value |
| A crude "no sun at midnight" test | Same failure | Replaced with a test that uses each city's actual sunrise and sunset |
| A missing irradiance hour would count as zero yield (DuckDB's `greatest()` skips NULL) | AI's own code review | Explicit null handling, pinned by a unit test |
| The report read from Silver, which breaks the layering | AI's own code review | Retrieval time moved into Gold |
| A displayed risk of 35 labelled "low" (34.5 rounded for display only) | Reading the rendered report | Score rounded in Gold before banding |
| "Best wind" tile and wind table used different day counts | Reading the rendered report | Both use the same matched days |
| `python -m pipeline run` failed at the report step: dbt kept the DuckDB file open | Running the full command end to end | dbt moved to a subprocess |
| `pip install` failed in a deep Windows folder (260-character path limit) | Clean install from a copy of the repo | Warning added to the README |

### Step 4: Verify

- Hourly GHI summed per day matches the API's own daily totals to within 0.03%.
- A second live run added 12 Bronze rows, while Silver stayed at one row per city and hour.
- A fresh copy installed from `requirements.txt` passed `run`, `sample` and all 18 Python
  tests, with dbt passing all 53 nodes.
- The report was screenshotted in light mode, dark mode and at mobile width, then checked.

## 4. Decisions I should be able to defend

These were AI suggestions that I accepted. They are assumptions, not facts:

- **Risk weights:** solar 45, wind 45, gusts 10; bands at 35 and 60.
- **Turbine:** a generic power curve (cut-in 3, rated 12, cut-out 25 m/s), not a real model.
- **Panels:** fixed north-facing at a tilt near latitude, 86% system efficiency.
- **Confidence:** by lead time only (high to 6 days, medium to 10, low beyond).

All of these are `vars` in `dbt/dbt_project.yml`, so they can be changed without touching SQL.

## 5. What the AI did not do

- It did not commit or push; that is left to me.
- It did not take the conversation screenshots; I add those to `ai-evidence/`.
- It did not test the Makefile, because `make` is not installed on this machine.
