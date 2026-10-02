# IPL Tactical Intelligence

![CI](https://github.com/Aadarsh2807/IPL-Tactical-Intelligence/actions/workflows/ci.yml/badge.svg)

**68 tests on every push** · **295,732 deliveries · 1,243 matches · 18 seasons** ·
**no pandas, no Spark, no ML model** · **4 backend dependencies**

**Five views over IPL ball-by-ball data — squad stability, XI selection, head-to-head
matchups, a bounded outlook, and a report written by an agent that is not allowed to
invent a number.**

![The squad view for Chennai Super Kings](docs/images/01-squad-stability.png)

*Chennai Super Kings, 2026. The API returns `attack_index: 0.968`. The page says "3% below
the league average". Bars support the sentence; they never replace it.*

![Walkthrough of all five views](docs/images/walkthrough.gif)

---

## What it does

| View | Question it answers | The rule that stops it lying |
|---|---|---|
| **Squad** | How balanced was this squad, and who is genuinely reliable? | Roles are inferred from workload, and every score carries its own weights plus a sample-size band |
| **XI builder** | Given a real side's constraints, which eleven should play? | A deterministic solver enumerates every legal role split — no randomness, so the same squad always yields the same XI |
| **Matchups** | What actually happened when this batter faced this bowler? | The bowler list only ever contains opponents who actually bowled to that batter that season |
| **Outlook** | What does a completed season suggest about the next game? | Bounded to 20–80%, with the method printed and the limitation printed |
| **Report** | Can an agent explain all of this without making something up? | Subagents gather from tools; a verifier redacts any figure it cannot trace — drawn as well as written |

---

## Every screen

| | |
|---|---|
| ![XI builder](docs/images/05-xi-builder.png) | ![Matchups](docs/images/08-matchups-pair.png) |
| **XI builder** — eleven solved under enforced role constraints | **Matchups** — a recorded head-to-head pair, graded by how much evidence backs it |
| ![Outlook](docs/images/09-outlook.png) | ![How the score is built](docs/images/03-squad-how-built.png) |
| **Outlook** — a bounded estimate with method and limits on screen | **How the figure was built** — the score taken apart into the parts that produced it |
| ![Report, verified](docs/images/11-report-masthead.png) | ![Audit trail](docs/images/14-report-audit.png) |
| **Report** — `VERIFIED`, 73 numbers traced to tool results | **Audit** — every sentence with the tool it came from |

---

## Run it

```bash
git clone https://github.com/Aadarsh2807/IPL-Tactical-Intelligence.git
cd IPL-Tactical-Intelligence

python scripts/fetch_data.py    # downloads the two CSVs, verifies them by checksum
python scripts/preflight.py     # prints READY, or exactly what is wrong

cd backend && python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # (.venv/bin/python on macOS/Linux)
.venv/Scripts/python -m uvicorn main:app --port 8000
```

Then, in a second terminal:

```bash
cd frontend && npm ci && npm run dev     # http://localhost:5174
```

First request builds a DuckDB warehouse (~2 s). Every boot after that is ~0.05 s and API
responses run 1–80 ms. Interactive API docs at <http://localhost:8000/docs>.

**About the dataset.** Two CC0 (public domain) CSVs from
[Kaggle](https://www.kaggle.com/datasets/chaitu20/ipl-dataset2008-2025), not committed
because the deliveries file is 21 MB. Since they are not in the repository, they are pinned
by **content rather than by link** — a URL can be edited or silently repointed, a checksum
cannot:

| File | MD5 |
|---|---|
| `ipl_deliveries_clean.csv` | `a81f1880e7b9b1f440f0005db00f6d4d` |
| `ipl_matches_clean.csv` | `c083503466c5c73501ff2987b74099e7` |

A mismatch is reported, not ignored, because every row count and quirk documented here
describes these exact files. Full schema: [docs/DATA.md](docs/DATA.md).

**Tests.**

```bash
cd backend  && .venv/Scripts/python -m pytest -q     # 68 tests, ~6 s
cd frontend && npm run lint && npm run build
```

---

## The two features worth explaining

### 1. Role-adaptive player stability (0–100)

A score whose **weights change with the role the data says the player actually filled**,
so the same person is judged on different criteria as their role shifts.

- **Batter** — scoring vs season baseline (45%), per-match consistency (25%), form (15%), availability (15%)
- **Bowler** — economy and wicket impact (45%), consistency (25%), form (15%), availability (15%)
- **All-rounder** — batting (30%) + bowling (30%) + both consistency scores (10% each) + form (10%) + availability (10%)

A ratio of exactly 1.0x to the season baseline scores 50, so the scale reads as *distance
from the league's own standard* rather than a percentage. Every player returns its
components, its weights, the raw ratios behind them, and a **sample-size band** (+/-3, +/-8,
+/-15) — so a three-match player is never presented as an 80.

### 2. XI builder

Select eleven under enforced constraints (exactly 11, at least 5 batters, at least 4
bowlers, at least 1 all-rounder) and watch it recompute live: 60% mean player stability,
25% role balance, 15% depth. **Best XI** runs the deterministic solver. No randomness and
no model, so the answer can be defended line by line.

Every threshold and formula: [docs/SCORING.md](docs/SCORING.md).

---

## The agentic layer

Agentic AI appears in exactly two places, and nowhere else.

```
POST /api/agent/report
  Harness  planner -> budget (6 tool calls max) -> trace
    |- Analyst   squad_overview, team_metrics, outlook
    |- Coach     best_xi, squad_overview
    |- Verifier  regex-extracts every number in the draft and requires it to
    |            already exist in a tool result - pure code, no model
    +- Narrator  rule-based prose; only arranges what the tools returned
  -> { headline figure, insights[] grouped in 5 sections,
       narrative[], evidence[], trace[], verifier }
```

**The guardrail is the feature.** Numbers are never generated, only arranged. A figure that
cannot be traced is replaced with `[unverified]` before it reaches the UI — including the
ones painted into bars and cards, not just the ones in sentences. Proven by
`test_verifier_rejects_a_number_not_in_the_tool_output`, which feeds the verifier a poisoned
draft and asserts the lie is caught.

No language model runs. No API key, no cost, fully offline.
Full write-up: [docs/AGENTS.md](docs/AGENTS.md).

---

## Designed for a reader, not a statistician

The API returns exact values. The interface never shows them that way. A small translation
layer, [frontend/src/lib/format.js](frontend/src/lib/format.js), turns every figure into a
sentence a newcomer can act on:

| Stored | Shown |
|---|---|
| `attack_index 0.968` | "3% below the league average" |
| `stability 55` | "Steady" |
| `role_balance 100` | "well balanced" |
| `strike_rate 142.9` | "strike rate 143" |
| `economy 10.0` | "10 an over" |
| `swot.strength` | "Bowling conceded 4% fewer runs than the league average of 187 (179 conceded)." |

Every view opens with an **"In plain English"** sentence stating the finding, so nobody has
to assemble a conclusion out of tiles of numbers. The only decimals that survive to the
screen are cricket figures, where a decimal *is* the unit.

A test enforces this: [test_no_jargon_in_ui.py](backend/tests/test_no_jargon_in_ui.py)
scans the component tree and fails if raw internal vocabulary — a tier index, a literal
`NaN` — reaches the copy. It caught exactly that bug once already.

---

## Architecture

```
data/raw/*.csv  (295,732 deliveries - 1,243 matches - 2007 to 2026)
        |
        |  backend/etl/sql/*.sql   <- the single source of truth for every number
        |  00_silver.sql   raw -> normalised (bowling_team, bowler_wicket, season join)
        |  10_team.sql     innings, league baseline, team metrics
        |  20_players.sql  player season, role baselines, per-match trend
        |  30_matchups.sql batter x bowler pairs
        v
data/warehouse.duckdb  (materialised once, rebuilt when the SQL fingerprint changes)
        |
        v
backend/dataset.py --> backend/analytics.py --> backend/main.py --> React UI
      (engine)              (scoring rules)        (thin routes)
                                  ^
                            backend/agents.py   tool registry + verifier
```

**One number, one place.** SQL aggregates; Python applies documented formulas; routes only
serialise. No route computes anything.

### Read the code in 10 minutes

| # | File | Lines | What to look at |
|---|---|---|---|
| 1 | [backend/etl/sql/00_silver.sql](backend/etl/sql/00_silver.sql) | ~100 | Every derived column, declared once, reasoning in the comments |
| 2 | [backend/dataset.py](backend/dataset.py) | ~390 | Path resolution, validation, warehouse lifecycle, provenance, dataset fingerprints |
| 3 | [backend/analytics.py](backend/analytics.py) | ~800 | The thresholds at the top, then `team_stability()` to `auto_xi()` |
| 4 | [backend/main.py](backend/main.py) | ~390 | Thin routes; the response models double as the OpenAPI contract |
| 5 | [backend/agents.py](backend/agents.py) | ~600 | `verify()` — twenty lines that decide whether prose may ship |
| 6 | [frontend/src/lib/format.js](frontend/src/lib/format.js) | ~110 | The translation layer: index decimals into plain sentences |
| 7 | [frontend/src/components/ReportPanel.jsx](frontend/src/components/ReportPanel.jsx) | ~270 | The editorial report layout |

---

## Tech stack, deliberately short

**Backend — 4 runtime dependencies**

| Package | Why it earns its place |
|---|---|
| `fastapi` | Typed request/response models; `/docs` is a demo asset |
| `uvicorn` | ASGI server |
| `duckdb` | Executes the SQL layer in-process. Columnar OLAP over CSV with no server, no JVM, no Spark |
| `pydantic` | Response validation (arrives with FastAPI) |

**Frontend — 2 runtime dependencies:** `react`, `react-dom`. Production bundle: **76 KB
gzipped** (71 KB JS + 5 KB CSS).

Deliberately **not** present: chart libraries (a sparkline is ten lines of SVG), icon
libraries (each icon is one `<path>`), animation libraries (CSS transitions), a state
library (two `useState` calls), a router (five views, one switch statement), and a config
file for Tailwind v4 (it is CSS-first).

**No ML model is used anywhere.** Every score is a published formula over audited
aggregates — which is precisely why it can be explained, tested and reproduced.

---

## What is disclosed, not hidden

`/api/health` and the UI footer both show this, because a reviewer should never have to ask:

- **Legal balls are assumed.** The source CSV has no `extras_type` column, so every delivery counts as one legal ball.
- **Bowler runs are approximate.** `runs_total` is charged to the bowler; byes and leg-byes cannot be separated from wides in this schema, so economy runs slightly high.
- **Super overs are excluded** (175 deliveries, all in tied matches) so they cannot inflate averages.
- **Bowlers are credited only when the dismissal method is recorded**, never for run outs, retired hurt, retired out or obstructing the field.
- **The dataset labels IPL 2008 as season `2007`, and `2009` spans two calendar years.** The app uses the dataset's own `season` column and deliveries inherit it from the match row, so a match can never split across seasons. A quirk of the source, not of the app.
- **No keeping dimension exists in the data**, so no wicket-keeper role is invented.
- **25 matches have no winner** (16 ties, 9 no-results) and become `NULL`, never an empty string.

---

## Documentation

| Document | Contents |
|---|---|
| [docs/DEFENSE.md](docs/DEFENSE.md) | "Likely interviewer objection, and where the answer lives" |
| [docs/DATA.md](docs/DATA.md) | Source schema, licence, every derived column, integrity evidence |
| [docs/SCORING.md](docs/SCORING.md) | Every threshold, weight and formula, with reasoning |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, warehouse lifecycle, performance, extension points |
| [docs/AGENTS.md](docs/AGENTS.md) | Subagents, harness, verifier, where an LLM would plug in |
| [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md) | Every screen in the app, with a note on what each one shows |

---

## Responsible interpretation

The outlook is a bounded analytical estimate (20–80%), not a betting recommendation or a
prediction. Roles and stability scores are heuristics over a single season, with no venue,
opposition-strength or injury modelling. The project is built to make its inputs visible
and its limitations arguable — not to hide them behind a black box.

MIT licensed.
