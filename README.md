# Apex Predictor — The Road to the World Championship

Formula 1 Drivers' Championship win confidence: who **can** still win (exact
mathematics), who is **most likely** to win (a calibrated ranking model +
Monte Carlo), and what **needs to happen** (What-If scenarios and pathways).
Updates itself after every Sprint and Grand Prix and switches to a permanent
champion state, with fireworks, the moment a title is mathematically clinched.

Current state (data through the 2026 Brazilian GP, Round 20): **Andrea Kimi
Antonelli clinched the 2026 title at Round 19** (Mexico City) — 390 points,
+111 over Max Verstappen with 75 points left.

## Architecture

```
Jolpica / OpenF1 ──► ingestion (cache, rate limits, retries, validation vs official standings)
                       │  corrections/<year>.json  (explicit FIA overrides)
                       ▼
           Engine D  grid/registry  — permanent ids, numbers & teams as time-dependent data,
                       │             change log, review queue, confirmed vs assumed entries
                       ▼
           Engine A  championship/  — scoring by versioned ruleset, FIA countback,
                       │             exact elimination + CP-SAT "every car finishes" check
                       ▼
           Engine B  models/        — hierarchical Plackett–Luce (driver skill + car + circuit fit),
                       │             long/short memory blend, incident filter, reliability model
                       ▼
           Engine C  simulation/    — full finishing orders per session, team shocks, correlated
                       │             DNFs, countback, conditional scenarios
                       ▼
           pipeline/run.py          — history replay (leakage-free), counterfactual explanations,
                       │             backtest + tuning, versioned snapshot (never overwritten)
                       ▼
           data/snapshots/latest.json ──► frontend (static React app) + FastAPI
```

Mathematics always overrides statistics: a clinched champion is exactly 100%,
eliminated drivers exactly 0%. A statistical 99.9% is never shown as a clinch.

## Repository

```
backend/apex/
  rules.py              versioned points/shortened-race/countback rules (1991 → today)
  domain.py             normalized season model
  ingestion/            jolpica.py, openf1.py, normalize.py (seed + corrections)
  championship/         scoring.py, tie_breaks.py, elimination.py (Engine A)
  models/               performance.py (Engine B), reliability.py
  simulation/           monte_carlo.py (Engine C)
  grid/                 registry.py, sync.py (Engine D)
  pipeline/             run.py (update job), backtest.py, explain.py
  api/main.py           FastAPI: snapshot, drivers, eligibility, POST /api/scenario
backend/tests/          pytest suite (scoring, elimination, simulation, grid, pipeline, API)
frontend/               React + TypeScript (Vite). Dashboard, champion celebration,
                        drivers, What-If simulator (browser Monte Carlo), pathways,
                        history replay, methodology.
data/seed/2026/         results, sprints, qualifying, calendar (pulled from Jolpica)
data/circuits.json      circuit types and priors
data/snapshots/         published, versioned prediction snapshots
database/migrations/    PostgreSQL / Supabase schema for when you move off JSON snapshots
.github/workflows/      CI + scheduled update job
```

## Run it

```bash
# backend
cd backend && pip install -r requirements.txt
python -m pytest -q
python -m apex.pipeline.run --season 2026 --source jolpica      # live data
python -m apex.pipeline.run --season 2026 --source seed --force # bundled data, offline
uvicorn apex.api.main:app --reload

# frontend
cd frontend && npm install
npm run dev               # reads ../data/snapshots/latest.json
npm run build             # static site for Vercel
npm run build:artifact    # one self-contained HTML file
npm test
```

## Automation

`.github/workflows/update-predictions.yml` polls every 20 minutes over race
weekends and daily otherwise. The job hashes the source data and exits
immediately when nothing changed; otherwise it rebuilds, validates against the
official standings (a mismatch keeps the last good snapshot live), and commits
a new versioned snapshot, which redeploys the frontend. A full 200k-simulation
run with history replay and tuning takes about two minutes.

New seasons need no code: the calendar, grid and points rules are discovered
from data and `rules.ruleset_for(year)`. When the FIA changes scoring, add a
`RuleSet` and have a human verify it before it activates.

## Model quality (2026, rolling next-race backtest, R4–R20)

See the Methodology page for the live numbers. The model beats both a uniform
baseline and a standings-weighted baseline on win Brier, podium Brier, podium
log loss and winner log loss. Settings are tuned on the same season they are
scored on; once archived seasons are loaded, tune on earlier years only.

## Known gaps / next steps

- Load 2025 and earlier archives for a preseason prior and out-of-season tuning.
- Postgres persistence (schema provided) instead of JSON snapshots.
- Weather, tyre, strategy and grid-penalty models from OpenF1 data (V4).
- Verify data licences and branding before a public commercial launch. Team
  colours are used as identifiers only; no logos or photography.
