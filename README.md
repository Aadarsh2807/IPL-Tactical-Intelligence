# IPL Tactical Intelligence

![CI](https://github.com/Aadarsh2807/IPL-Tactical-Intelligence/actions/workflows/ci.yml/badge.svg)

**Season squad analysis, role-adaptive player stability, XI building and recorded head-to-head matchups — computed entirely from IPL ball-by-ball deliveries in SQL.**

> The claim this project has to survive is "every number came from the data". So every figure is auditable: `GET /api/sql/{name}` returns the exact SQL behind it, `GET /api/health` returns the dataset's provenance and its disclosed approximations, and a test mechanically proves no player or team name is written in application code.

---

## Designed for a reader, not a statistician

The API returns exact values (`attack_index: 0.968`). The interface never shows them that
way. A small translation layer, [frontend/src/lib/format.js](frontend/src/lib/format.js),
turns every figure into a sentence a newcomer can act on:

| Stored | Shown |
|---|---|
| `attack_index 0.968` | "3% below the league average" |
| `stability 55` | "Steady" |
| `role_balance 100` | "well balanced" |
| `strike_rate 142.9` | "strike rate 143" |
| `economy 10.0` | "10 an over" |
| `swot.strength` | "Bowling conceded 4% fewer runs than the league average of 187 (179 conceded)." |

Every view opens with an **"In plain English"** sentence that states the finding, so nobody has
to assemble the conclusion from tiles of numbers. Bars support the sentence; they never replace
it. The only decimals that survive to the screen are cricket figures (runs per over), where a
decimal is the actual unit.

## What it does

| View | Question answered | Evidence rule |
|---|---|---|
| **Squad** | How balanced was this team this season, and which players are actually stable? | Roles inferred from workload; every score carries its weights and a sample-size band |
| **XI builder** | Given the constraints of a real side, what eleven should play? | Deterministic solver over legal role splits; selections outside the squad are rejected |
| **Matchups** | What happened when this batter faced this bowler? | The bowler list only contains opponents who actually bowled to that batter that season |
| **Outlook** | What does a completed season suggest about the next match? | Bounded 20–80%, method printed, limitation printed |
| **Report** | Can an agent explain it without inventing a number? | Subagents gather from tools; the report is grouped into insights; a verifier redacts any untraceable figure, drawn as well as written |

---

## Architecture

```
data/raw/*.csv  (295,732 deliveries · 1,243 matches · 2007–2026)
        │
        │  backend/etl/sql/*.sql   ← the single source of truth for every number
        │  00_silver.sql   raw → normalised (bowling_team, bowler_wicket, season join…)
        │  10_team.sql     innings, league baseline, team metrics
        │  20_players.sql  player season, role baselines, per-match trend
        │  30_matchups.sql batter × bowler pairs
        ▼
data/warehouse.duckdb  (materialised once, rebuilt when inputs change)
        │
        ▼
backend/dataset.py ──► backend/analytics.py ──► backend/main.py ──► React UI
      (engine)              (scoring rules)         (thin routes)
                                  ▲
                            backend/agents.py   tool registry + verifier
```

**One number, one place.** SQL aggregates; Python applies documented formulas; routes only
serialise. No route computes anything.

### Read the code in 10 minutes

| Order | File | Lines | What to look at |
|---|---|---|---|
| 1 | [backend/etl/sql/00_silver.sql](backend/etl/sql/00_silver.sql) | ~100 | Every derived column, declared once, with the reasoning in comments |
| 2 | [backend/dataset.py](backend/dataset.py) | ~340 | Path resolution, validation, warehouse materialisation, provenance |
| 3 | [backend/analytics.py](backend/analytics.py) | ~800 | The thresholds at the top, then `stability_report` → `auto_xi` |
| 4 | [backend/main.py](backend/main.py) | ~390 | Thin routes; response models double as the OpenAPI contract |
| 5 | [backend/agents.py](backend/agents.py) | ~600 | `verify()` — 20 lines that decide whether prose may ship; then the insight layer that arranges it into a report |
| 6 | [frontend/src/lib/format.js](frontend/src/lib/format.js) | ~90 | The translation layer: index decimals → plain sentences |
| 7 | [frontend/src/lib/api.js](frontend/src/lib/api.js) | ~60 | One fetch client with cancellation |

---

## Tech stack (deliberately short)

**Backend — 4 runtime dependencies**

| Package | Why it earns its place |
|---|---|
| `fastapi` | Typed request/response models; `/docs` is a demo asset |
| `uvicorn` | ASGI server |
| `duckdb` | Executes the SQL layer in-process. Columnar OLAP over CSV/Parquet with no server, no JVM, no Spark |
| `pydantic` | Response validation (arrives with FastAPI) |

**Frontend — 2 runtime dependencies:** `react`, `react-dom`.

Deliberately **not** present: chart libraries (a sparkline is 10 lines of SVG), icon
libraries (each icon is one `<path>`), animation libraries (CSS transitions), a state
library (two `useState` calls), a router (five views, one switch statement), and a config
file for Tailwind v4 (it is CSS-first). Production bundle: **68 KB gzipped**.

**No ML model is used anywhere.** Every score is a published formula over audited
aggregates, which is why it can be explained, tested and reproduced.

---

## Run it

Requires Python 3.10+ and Node 18+. First check everything with:

```bash
python scripts/preflight.py          # add backend/.venv/Scripts/python.exe on Windows
```

### 1. Dataset

Place the two files in `data/raw/` (already populated in this checkout, gitignored because
the delivery file is 21 MB):

```text
data/raw/ipl_deliveries_clean.csv
data/raw/ipl_matches_clean.csv
```

Point somewhere else with `IPL_DATA_DIR`. See [docs/DATA.md](docs/DATA.md) for the schema
and every derived column.

### 2. Backend

```bash
cd backend
python -m venv .venv
# Windows:      .venv\Scripts\python -m pip install -r requirements.txt
# macOS/Linux:  .venv/bin/python    -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn main:app --reload --port 8000
```

First request builds `data/warehouse.duckdb` (~2 s). Every later boot is ~0.05 s, and API
responses are 1–80 ms. Interactive API docs: <http://localhost:8000/docs>.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5174
```

If your API runs on another port: `API_TARGET=http://localhost:8010 npm run dev`.

### 4. Tests

```bash
cd backend && .venv/Scripts/python -m pytest -q      # 54 tests, ~5 s
cd frontend && npm run lint && npm run build
```

---

## The two features

### 1. Role-adaptive player stability (0–100)

A score per player whose **weights change with the role the data says they played**, so the
same person is judged on different criteria as their role shifts.

- **Batter** — scoring vs season baseline (45%), per-match consistency (25%), form (15%), availability (15%)
- **Bowler** — economy + wicket impact (45%), consistency (25%), form (15%), availability (15%)
- **All-rounder** — batting output (30%) + bowling output (30%) + both consistency scores (10% each) + form (10%) + availability (10%)

A ratio of 1.0× to the season baseline scores exactly 50, so the scale means "how far from
the league's own standard", not a percentage. Every player returns its component scores,
their weights, the raw ratios they came from, and a **sample-size band** (±3 / ±8 / ±15) so
a three-match player is never presented as an 80.

### 2. XI builder

Select eleven players under enforced constraints (exactly 11, ≥5 batters, ≥4 bowlers, ≥1
all-rounder) and watch the score recompute live: 60% mean player stability, 25% role
balance, 15% depth. **Best XI** runs a deterministic solver that enumerates every legal role
split and keeps the highest-scoring one — no randomness, no model, so the same squad always
produces the same XI and the answer can be defended line by line.

Full formulas and thresholds: [docs/SCORING.md](docs/SCORING.md).

---

## The agentic layer

Agentic AI appears in exactly two places: the squad narrative and the selection narrative.

```
POST /api/agent/report
  Harness  planner → budget (≤6 calls) → trace
    ├ Analyst   tools: squad_overview, team_metrics, outlook
    ├ Coach     tools: best_xi, squad_overview
    ├ Verifier  regex-extracts every number in the draft and requires it to
    │           already exist in a tool result — pure code, no model
    └ Narrator  rule-based prose; only arranges what tools returned
  → { headline figure, insights[] grouped in 5 sections,
      narrative[], evidence[], trace[], verifier }
```

**The guardrail is the feature:** numbers are never generated, only arranged. A figure that
cannot be traced is replaced with `[unverified]` before it reaches the UI — proven by
`test_verifier_rejects_a_number_not_in_the_tool_output`, which feeds the verifier a poisoned
draft and asserts the lie is caught. It runs offline with no API key and no cost.

Subagents, harness and AI harnessing explained: [docs/AGENTS.md](docs/AGENTS.md).

---

## What is disclosed, not hidden

`/api/health` and the UI footer both show this, because a reviewer should never have to ask:

- **Legal balls are assumed.** The source CSV has no `extras_type` column, so every delivery
  row counts as one legal ball.
- **Bowler runs are approximate.** `runs_total` is charged to the bowler; byes and leg-byes
  cannot be separated from wides and no-balls in this schema, so economy runs slightly high.
- **Super overs are excluded** (175 deliveries, all in tied matches) so they cannot inflate
  averages.
- **Bowlers are credited only when the dismissal method is recorded**, and never for run
  outs, retired hurt, retired out or obstructing the field.
- **The dataset labels IPL 2008 as season `2007` and `2009` spans two calendar years.** The
  app uses the dataset's own `season` column, and deliveries inherit it from the match row,
  so aggregates stay internally consistent. This is a quirk of the source, not of the app.
- **No keeping dimension exists in the data**, so no wicket-keeper role is invented.

---

## Documentation

| Document | Contents |
|---|---|
| [docs/DATA.md](docs/DATA.md) | Source schema, every derived column, join and row-count evidence |
| [docs/SCORING.md](docs/SCORING.md) | Every threshold, weight and formula, with the reasoning |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, warehouse lifecycle, performance, extension points |
| [docs/AGENTS.md](docs/AGENTS.md) | Subagents, harness, verifier, and where an LLM would plug in |
| [docs/DEFENSE.md](docs/DEFENSE.md) | "Likely interviewer objection → where the answer lives" |

---

## Responsible interpretation

The outlook is an analytical historical estimate, bounded to 20–80%, not a betting
recommendation or a prediction. Roles and stability scores are heuristics over a single
season with no venue, opposition-strength or injury modelling. The project is built to make
its inputs visible and its limitations arguable, not to hide them behind a black box.
