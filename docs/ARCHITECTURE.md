# Architecture

## Layers, and the rule between them

| Layer | Files | May do | May not do |
|---|---|---|---|
| Ingest / SQL | `backend/etl/sql/*.sql` | read the CSVs, normalise, aggregate | score, round, or know about HTTP |
| Data access | `backend/dataset.py` | locate files, validate, materialise, run parameterised SQL | contain analysis logic |
| Scoring | `backend/analytics.py` | apply published formulas to aggregates | run raw SQL strings of its own or import FastAPI |
| Agents | `backend/agents.py` | call tools, narrate, verify | invent a number |
| Transport | `backend/main.py` | parse, delegate, serialise | compute anything |
| Presentation | `frontend/src/**` | render what the API returned | calculate a metric |

The rule that makes this testable: **aggregation lives in SQL, scoring lives in Python, and
routes do neither.** Because `analytics.py` never imports FastAPI, every scoring rule is
unit-testable without a server, and because every view reads only API fields, the UI cannot
invent a metric.

## Request lifecycle (worked example)

`GET /api/squad/Chennai Super Kings?season=2025`

1. `main.squad()` parses and delegates to `analytics.squad(season, team)`.
2. `require_team()` checks the team appears in that season → `404` otherwise.
3. `stability_report()` runs four queries against materialised gold tables:
   `gold_player_season`, `gold_match_contrib`, `gold_role_baselines`, `gold_team_season`.
4. Python applies the role weights, consistency, form, availability and confidence band.
5. `team_stability()` applies the squad-level formula and `_swot()` writes evidence sentences.
6. The response is validated against `SquadResponse` and returned.
7. The UI renders the numbers and nothing else.

Total backend time: ~0.1 s.

## Warehouse lifecycle

The dataset is read-only, so re-parsing a 21 MB CSV per request would be the obvious waste.
Instead:

1. `dataset.csv_paths()` resolves `data/raw/` (or `IPL_DATA_DIR`).
2. `validate_source()` checks the required columns and fails with an actionable message.
3. A fingerprint of *every input* (both CSV paths + mtimes, all `.sql` files + mtimes) is
   compared with the one stored in `warehouse_meta`.
4. If it differs, the SQL layer is rebuilt into `warehouse.staging.duckdb` and swapped in
   atomically — a crash can never leave a half-built database.
5. The app opens `data/warehouse.duckdb` and queries real tables.

| Scenario | Cost |
|---|---|
| First boot (or after any input change) | ~2.1 s |
| Every later boot | ~0.05 s |
| Squad request | ~100 ms |
| Matchups request | ~80 ms |

The build is *lazy* — it happens on the first request, not at import — and `rebuilt_on_boot`
plus `warehouse_built_at` are reported by `/api/health`, so caching is observable rather than
claimed.

## Why DuckDB and not Spark

The requirement was SQL without a JVM, a cluster, or a second language. DuckDB gives:

- the SQL layer runs in-process, so there is no server to run;
- columnar execution over CSV without a load step;
- the exact aggregate shapes the app needs (`FILTER`, `FULL OUTER JOIN`, `NULLIF`, `TRY_CAST`).

Spark would add a ~350 MB dependency, a Java runtime, and a JVM startup, to aggregate 295k
rows that DuckDB answers in milliseconds. The SQL files are standard enough that a Spark
backend could be added as a second engine without touching the queries — but it would not be
justified at this data size, so it is not in the stack.

## Extension points

| Want to… | Do this |
|---|---|
| Add a league (BBL, SA20) | drop another CSV pair in `data/raw/`, extend `validate_source()`; the SQL is league-agnostic |
| Add a metric | one query, one Python function, one field in the Pydantic model |
| Make economy exact | fetch a ball-by-ball source with `extras_type`, join it in `00_silver.sql`, flip the provenance flag |
| Add a view | one component + one entry in `TABS` |
| Swap the narrator for an LLM | implement `narrate()`; the verifier and tools stay identical (see [AGENTS.md](AGENTS.md)) |
| Add a new agent | register a tool, grant it in `AGENT_TOOLS`, add it to a `PLAN` — the budget and trace apply automatically |

## Error handling

One envelope, `{"detail": "..."}`, from three mapped exceptions: `analytics.NotFound` → 404,
`agents.AgentError` → 400, `dataset.DataError` → 503. The frontend client reads `detail` for
every failure, so no view needs bespoke error parsing. In-flight requests are cancelled with
`AbortController` when the selection changes, so a fast season switch cannot paint the
previous season's data.

## Accessibility and states

Every control has a real label; focus rings use the team accent; colour is never the only
signal (constraints show ✓/✕ as well as colour; confidence is written out); skeletons,
empty states and error-with-retry exist for every view; `prefers-reduced-motion` disables the
breathing hairline.
