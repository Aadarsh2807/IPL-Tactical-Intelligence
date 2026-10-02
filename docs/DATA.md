# Data: what is in the files, and what had to be derived

## Source files

Two CSVs, both read-only, both gitignored (`data/raw/`):

| File | Rows | Columns | Grain |
|---|---|---|---|
| `ipl_deliveries_clean.csv` | 295,732 | 14 | one delivery |
| `ipl_matches_clean.csv` | 1,243 | 13 | one match |

### `ipl_deliveries_clean.csv`

`match_id, innings, batting_team, over, ball, batter, bowler, non_striker, runs_batter, runs_extras, runs_total, wicket, wicket_player_out, wicket_kind`

### `ipl_matches_clean.csv`

`match_id, date, season, venue, city, team1, team2, toss_winner, toss_decision, winner, result_type, result_margin, player_of_match`

## Why an adapter exists

The previous version of this project required sixteen columns (`event_name`, `season`,
`bowling_team`, `runs_bowler`, `balls_faced`, `valid_ball`, `bowler_wicket`, `player_out`,
`win_outcome`, …) and **none of them exist in these files**. The app could not start on the
data it was shipped with.

The fix is an explicit derivation layer rather than a wish list. Every derived column is
declared exactly once, in [backend/etl/sql/00_silver.sql](../backend/etl/sql/00_silver.sql).

## Derivation table

| Silver column | Source | Rule | Why |
|---|---|---|---|
| `season`, `play_date`, `venue`, `city` | matches | `JOIN` on `match_id` | deliveries carry no season |
| `bowling_team` | matches | `CASE WHEN batting_team = team1 THEN team2 ELSE team1 END` | never inferred from innings order |
| `winner`, `result_type`, `decided` | matches | `result_type IN ('runs','wickets')` | ties and no-results are not wins for anyone |
| `is_super_over` | deliveries | `innings > 2` | 175 rows, all in tied matches |
| `legal_ball` | — | constant `1` | **assumed**: no `extras_type` column exists |
| `bowler_runs` | — | `runs_total` | **approximate**: byes/leg-byes cannot be separated from wides/no-balls |
| `bowler_wicket` | deliveries | `wicket = 1 AND wicket_kind NOT IN ('run out','retired hurt','retired out','obstructing the field') AND wicket_kind IS NOT NULL` | non-bowler dismissals never credit a bowler |
| `striker_dismissed` | deliveries | `wicket = 1 AND wicket_player_out = batter AND wicket_kind <> 'retired hurt'` | retired hurt is not a dismissal; run outs still count as outs for batting averages |

Both approximations are reported by `/api/health`, printed by `scripts/preflight.py`, shown in
the UI footer, and asserted by `test_provenance_reports_its_assumptions`.

## Join and integrity evidence

Verified by `backend/tests/`, not by hand:

| Check | Result |
|---|---|
| Deliveries whose `match_id` has no match row | **0** |
| Matches with no delivery rows | **0** |
| `runs_total = runs_batter + runs_extras` on every row | **0** violations |
| Rows where `bowling_team = batting_team` | **0** |
| `runs_total` in `silver_deliveries` vs summed `gold_innings` | equal |
| Season totals recomputed with the Python standard library | match SQL exactly |

## Dataset quirks that are *not* bugs in this app

- **Season labels are not calendar years.** The label `2007` covers calendar 2008, and the
  label `2009` spans calendar 2009 *and* 2010 (117 matches). This comes from the source.
  The app uses the dataset's own `season` column everywhere, and deliveries inherit it from
  their match row, so a match can never be split across two seasons. Counting calendar years
  instead of labels yields 19 groups rather than 18 — both numbers are defensible, and the
  app states which it uses.
- **`season 2010` does not exist as a label.** It is folded into `2009`.
- **25 matches have no `winner`** (16 ties, 9 no-results) and 9 have no `player_of_match`.
  These become `NULL`, never an empty string, so "no result" is never confused with a team.
- **`city` is empty for 51 matches** (venues without a city). Also `NULL`.
- **There is no keeping, no venue surface, no opposition strength and no injury data.**
  No keeper role is invented, and no model pretends to use information that does not exist.

## Role inference

A single SQL macro, `role_of(bat_balls, bowl_balls)`, is the only definition of "role":

| Role | Rule | Reasoning |
|---|---|---|
| All-rounder | both ≥ 18 balls | both disciplines used enough to matter |
| Bowler | ≥ 36 balls (six overs) | a real bowling allocation |
| Bowler | ≥ 18 balls bowled, < 18 batted | bowled without ever batting properly |
| Batter | everything else | includes keeper-batters, which the data cannot separate |

Thresholds are unit-tested in `test_role_of_macro_classifies_by_workload`, so a change to the
macro cannot silently change a squad.
