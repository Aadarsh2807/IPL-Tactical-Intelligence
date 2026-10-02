# Defence: likely objections and where each one is answered

The point of this page is that no answer requires confidence — every objection below maps to a
file, a test, or a disclosed limitation.

## Data

| Objection | Answer | Proof |
|---|---|---|
| "Your code asks for columns that don't exist." | The derivation layer declares all 16 of them explicitly, once, with reasoning in comments | [00_silver.sql](../backend/etl/sql/00_silver.sql), `test_source_files_exist_and_declare_expected_columns` |
| "Is the data complete?" | 295,732 deliveries → 1,243 matches, **0 orphaned rows**, 0 matches without deliveries | `test_every_delivery_joins_to_a_match`, `preflight.py` |
| "Could the numbers just be hardcoded?" | No player or team name may appear in application code; the test builds its forbidden list *from the dataset itself*, so deleting a name from a list cannot make it pass | `test_no_identity_is_written_in_application_code` |
| "Did you verify the maths independently?" | Season totals and a player's dismissals are recomputed with the Python standard library straight from the CSV and required to match SQL | `test_independent_recompute.py` |
| "Your economy figures must be wrong." | They are approximate, and the app says so: `runs_total` is charged to the bowler because byes/leg-byes cannot be separated in this schema. Exact-flagged if a richer source is added | `/api/health`, UI footer, `test_provenance_reports_its_assumptions` |
| "Your averages include super overs." | 175 super-over deliveries (all in tied matches) are flagged and excluded from every aggregate | `test_super_over_deliveries_are_counted_and_flagged` |
| "You credit bowlers for run outs." | Bowlers are credited only when the dismissal method is recorded and is not a run out, retired hurt, retired out or obstructing the field | `test_bowler_is_never_credited_for_a_non_bowler_dismissal` |
| "Why 18 seasons when the calendar shows 19?" | The dataset labels IPL 2008 as `2007` and folds 2010 into `2009`. The app uses the dataset's own `season` column; deliveries inherit it from their match row, so a match can never split across seasons | [DATA.md](DATA.md) |
| "Which teams is this biased toward?" | None — every team, including defunct franchises, is derived from the fixtures table. The only hand-written team names are brand colours for the UI, and that file is the single exemption the test allows | [teams.js](../frontend/src/theme/teams.js) |

## Scoring

| Objection | Answer | Proof |
|---|---|---|
| "Your stability score is a black box." | Every player returns component scores, their weights, the raw ratio behind them, and a confidence band | `test_scores_are_bounded_and_confidence_reflects_sample` |
| "Is it just runs + wickets?" | No — output vs a role-filtered baseline, per-match consistency, form, availability, with different weights per role | [SCORING.md](SCORING.md) |
| "How is a role decided?" | One SQL macro, `role_of`, tested case by case, so a threshold change cannot silently change a squad | `test_role_of_macro_classifies_by_workload` |
| "A player with three matches gets an 80." | Impossible: <4 matches makes consistency and form report *neutral with a reason*, and <80 balls is Low confidence with a ±15 band | `test_low_sample_players_are_marked_not_silent` |
| "Are these percentages?" | No. 50 = exactly the season baseline for that component. Stated in the UI and in `/api/method` | `GET /api/method` |
| "Is the win probability a betting number?" | Bounded 20–80%, method and limitation returned with it, win rate from decided matches only | `test_outlook_is_bounded_and_explains_itself` |

## Features

| Objection | Answer | Proof |
|---|---|---|
| "The best XI is just random." | Deterministic solver: enumerate legal role splits, score each, keep the best, tie-break on sorted names. Same squad → same XI, every time | `test_auto_xi_is_deterministic` |
| "What stops an illegal XI?" | Server-side validation: exactly 11, ≥5 batters, ≥4 bowlers, ≥1 all-rounder, no duplicates, no names outside the squad — each violation is returned with a reason | `test_invalid_selections_are_rejected_with_reasons` |
| "Matchups are invented." | The bowler dropdown only contains opponents with recorded deliveries; an unrecorded pair 404s instead of returning zeros | `test_matchup_flow` |

| "A non-analyst cannot read 0.968." | True, so the UI never shows it. A single translation layer converts every index into a sentence — "3% below the league average", "well balanced", "Steady" — and every view opens with an "In plain English" finding. Only cricket units (runs per over) keep a decimal. | [format.js](../frontend/src/lib/format.js) |

## Engineering

| Objection | Answer | Proof |
|---|---|---|
| "There are no tests." | 60 tests across 8 files: schema, invariants, independent recomputation, no-hardcoding, API surface, scoring, XI, harness | `cd backend && python -m pytest -q` |
| "Why DuckDB instead of Spark/pandas?" | 21 MB of CSV is answered in 1–80 ms by an in-process columnar engine. Adding Spark would mean a 350 MB dependency, a JVM, and startup cost for no gain. The SQL is portable enough to add one later | [ARCHITECTURE.md](ARCHITECTURE.md) |
| "Why no database?" | Read-only analytical serving. The warehouse is a single file, rebuilt automatically when inputs change, with the rebuild visible in `/api/health` | `GET /api/health` |
| "Isn't that cached data?" | Yes — deliberately, and observably: `rebuilt_on_boot` and `warehouse_built_at` are reported, and the fingerprint covers every CSV and every `.sql` file | `preflight.py --rebuild` |
| "Unpinned dependencies?" | All five backend dependencies are pinned exactly | [requirements.txt](../backend/requirements.txt) |
| "Security?" | CORS scoped to one origin (not `*`), Pydantic validation on every request and response, no arbitrary-SQL endpoint, no secrets, errors carry a message and nothing more | [main.py](../backend/main.py) |
| "Race conditions?" | One fetch client, and every selection change aborts the previous request | [api.js](../frontend/src/lib/api.js) |
| "Dead dependencies?" | Removed: framer-motion, recharts, lucide-react, autoprefixer, postcss config, tailwind config, `App.css`, three unused assets. Frontend is React + React DOM; bundle is 68 KB gzipped | `package.json`, `npm run build` |
| "Can I check your work?" | `GET /api/sql/{name}` returns the exact SQL and rows behind each figure. Arbitrary SQL is deliberately refused — that is a security decision, not a missing feature | `test_named_sql_query_is_auditable`, `test_unknown_or_incomplete_sql_query_is_refused` |
| "Why no database / no ML / no auth?" | Out of scope for a read-only analytical tool, and each would add surface without improving the claim being made | [README](../README.md) |

## Agentic layer

| Objection | Answer | Proof |
|---|---|---|
| "Where's the AI?" | Two places, both narration: the squad report and the selection narrative. The harness — tools, budget, trace, verifier — is the real deliverable | [AGENTS.md](AGENTS.md) |
| "The report is just a list of numbers." | It leads with one figure, splits it into the pillars that produced it, and states what is exposed. The bars are audited too, not only the sentences | `test_the_audit_covers_drawn_figures_not_only_prose` |
| "Does it hallucinate?" | It cannot: numbers are only arranged, never generated, and any untraceable figure is replaced with `[unverified]` before it reaches the UI | `test_verifier_rejects_a_number_not_in_the_tool_output` |
| "Isn't a deterministic narrator just templates?" | Yes, and that is the honest version: it makes the guarantee testable today. The `narrate()` contract is where a model would go, with the verifier unchanged — and no untested model path is shipped | [AGENTS.md](AGENTS.md) |
| "What is a subagent, then?" | A role-scoped worker with a tool whitelist enforced in code and one output contract | `test_an_agent_cannot_call_another_agents_tool` |

## The honest short list

Five things a sharp reviewer can legitimately criticise, each already stated in the product:

1. Economy is approximate (no extras split in the source schema).
2. Roles are heuristics at 18/18/36 balls, not canonical cricket definitions.
3. No wicket-keeper is detected, because the data has no keeping dimension.
4. Form and consistency need ≥4 matches, and report neutral below that.
5. The verifier proves a number *came from* a tool, not that the sentence reads it correctly.
