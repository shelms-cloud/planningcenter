# Attrition & retention analysis

Pulls Celebration Church's Planning Center data (People, Check-Ins, Groups,
Services, Giving), applies the definitions below, and builds:

- `out/dashboard.html`: the shareable dashboard (aggregates only)
- `out/metrics.json`: every number on the dashboard, with numerators and denominators
- `out/private/at_risk.html` / `.csv` and `out/private/lapsed.csv`: names for
  pastoral follow-up. **Gitignored. Keep inside the pastoral team.**

## Run it

1. Create a Planning Center Personal Access Token at
   <https://api.planningcenteronline.com/oauth/applications> while logged in as a
   user with read access to People, Check-Ins, Groups, Services and Giving.
2. Expose it as `PCO_APP_ID` and `PCO_SECRET`, and allow
   `api.planningcenteronline.com` in the environment's network settings.
3. `./run.sh`. A first full pull takes roughly 20–40 minutes, mostly group
   attendance (one request per group meeting). Re-runs skip pages already
   downloaded; delete `data/raw` for a fresh pull.

`AS_OF=YYYY-MM-DD ./run.sh` pins "today" for a reproducible rerun.

## Definitions (all in `config.py`)

| Term | Rule |
|---|---|
| Attendance day | A distinct day with a check-in (any event, including volunteer), group attendance marked present, or confirmed serving on a Services plan |
| Regular attender | 6+ attendance days in a 91-day window (2+ a month over 3 months) |
| Lapsed | Regular in the 91 days ending one year before `AS_OF`, and no activity in the last 90 days: no check-in (their own, or a child in their household), group attendance, confirmed serving, People form submission (staff paperwork forms excluded), event registration or gift. Staff notes are shown as "last staff note" on the private lists, not counted as activity |
| Engaged | Group: attended a group meeting in the prior 6 months. Serving: confirmed on a plan or volunteer check-in in the prior 6 months. Giving: a gift in 2 of 3 baseline months |
| First-time guest | First attendance in the last 12 months, no earlier activity since `HISTORY_START`, People record created no more than 60 days before |
| At risk | Regular in the 3 months before the last 90 days, and attendance in the last 90 days down 50%+ |

Ministry area comes from Check-Ins event names via `EVENT_RULES` in
`config.py`. Review the mapping table on the dashboard's data-gaps panel and
adjust the rules if an event is misfiled.

## Running it through the Planning Center connector (Oct 2026 run)

The published numbers came from data pulled through the Planning Center
connector, because the session could not reach the API directly. Helper agents
copied each page into `data/connector/*.csv` following `data/connector/*TASK.md`,
and each batch's row count was checked against Planning Center's own total
(`data/connector/logs/done.txt`). Spot-checks against fresh API reads: 40 check-in rows,
7 check-in rows and 75 People fields, all matching. Then:

    AS_OF=2026-10-13 HISTORY_START=2025-07-14 NEWCOMER_LOOKBACK_DAYS=90 ACTIVE_PEOPLE_TOTAL=9541 \
      sh -c 'python3 build_connector.py && python3 analyze.py && python3 render.py'

Giving was not readable by the connector account, so it is excluded. Forms (`data/connector/forms`), Registrations attendees (`data/connector/registrations`) and People notes (`data/connector/notes`, no note text) were pulled the same way; `FORMS_TASK.md`, `REG_TASK.md` and `NOTES_TASK.md` describe each pull.

`yearly.py` compares fall-to-fall retention for 2023-24, 2024-25 and 2025-26 using check-ins from January 2023 (`data/connector/checkins_hist`) plus forms, registrations and children's check-ins, and writes `out/yearly.json`.

## Pipeline

`fetch_pco.py` (raw API pages → `data/raw`) → `build.py` (tidy CSVs →
`data/tidy`) → `analyze.py` (`out/metrics.json`, private CSVs) → `render.py`
(HTML). `narrative.json` holds the written findings and recommendations.

`tests/make_fixture.py` generates a synthetic dataset for testing the pipeline;
its output is fake and must never be presented.
