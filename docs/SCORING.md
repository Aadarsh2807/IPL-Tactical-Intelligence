# Scoring: every threshold, weight and formula

All of it lives in [backend/analytics.py](../backend/analytics.py) as named constants at the
top of the file, is published at `GET /api/method`, and is unit-tested. Nothing below is
hidden in a route.

## Shared primitives

| Helper | Definition |
|---|---|
| `_score_ratio(r)` | `100 × clamp(r, 0, 2) / 2` — so **1.0× the baseline scores exactly 50** |
| `_consistency(series)` | `100 × clamp(1 − pstdev / (|mean| + 1))`; returns a neutral 50 with a note when fewer than 4 matches |
| `_form(series)` | `50 + 50 × clamp((late_mean − early_mean) / (pstdev + 1))`, comparing the second half of the season to the first |
| `_availability(m, t)` | `100 × clamp(matches_played / team_matches)` |
| `_confidence(balls)` | High ≥ 200 balls, Medium ≥ 80, otherwise Low |

The scale is an **index, not a percentage**: 50 means "exactly the league's own standard for
that component". This is stated in the UI and in the API.

## 1. Player stability (role-adaptive)

Per-match output, from `gold_match_contrib`:
- batting: `runs scored in that match`
- bowling: `20 × wickets − runs conceded` (a wicket ≈ a boundary saved)

| Component | Batter | Bowler | All-rounder |
|---|---|---|---|
| Batting output | **45%** | — | **30%** |
| Bowling output | — | **45%** | **30%** |
| Batting consistency | — | — | **10%** |
| Bowling consistency | **25%** | **25%** | **10%** |
| Form | **15%** | **15%** | **10%** |
| Availability | **15%** | **15%** | **10%** |

Weights sum to 1.00 for every role (asserted in `test_role_weights_sum_to_one_and_differ_by_role`).

**Output ratios**
- batting: `(player runs / player balls) ÷ (baseline runs / baseline balls)`
- bowling: `0.6 × (baseline economy ÷ player economy) + 0.4 × (player wicket rate ÷ baseline wicket rate)`

**Baselines** are season-wide and restricted to players who cleared the same workload bar
(≥18 batting balls, ≥36 bowling balls), so a pinch-hitter cannot define "average" for the
league.

**All-rounders are gated**: the role itself requires ≥18 balls in both disciplines, so nobody
scores well on one skill alone.

**Confidence band** is reported, not hidden: High ±3, Medium ±8, Low ±15 points. A player
with three matches is shown as `Low` and their consistency/form components read
"neutral: only 3 matches" instead of a fabricated number.

## 2. Squad stability

| Input | Weight | Cap |
|---|---|---|
| Attack index (avg runs per innings ÷ league avg) | 35% | 1.30× |
| Defence index (league avg ÷ avg conceded) | 35% | 1.30× |
| Role balance | 20% | batting depth/6 and bowling depth/5, halved |
| Match coverage | 10% | 14 matches |

The 1.30× benchmark is deliberate: a full squad alone cannot reach 100, because half the score
comes from role balance and coverage rather than output.

## 3. XI score

| Input | Weight | Definition |
|---|---|---|
| Quality | 60% | mean player stability of the eleven |
| Role balance | 25% | `min(batters/5,1) + min(bowlers/4,1) + min(all-rounders/1,1)`, divided by 3 |
| Depth | 15% | players clearing 18 batting balls and 36 bowling balls, each capped |

Constraints enforced before scoring: exactly 11, ≥5 batters, ≥4 bowlers, ≥1 all-rounder.

**Best XI solver** (`auto_xi`): enumerate every legal `(batters, all-rounders, bowlers)` split,
take the highest-scoring players within each role for each split, score all splits, keep the
best. Ties break on the sorted player-name tuple, so the output is fully deterministic.
There is no randomness and no model — the answer can be defended line by line.

## 4. Season outlook

```
performance_index = 0.45 × attack + 0.35 × defence + 0.20 × win_rate
probability      = clamp(50 + (performance_index − 0.90) × 100, 20, 80)
```

The bounds are the point: a historical model is never presented as certainty. `win_rate` uses
decided matches only, and the response always carries a `limitation` string.

## 5. Matchups

Straight aggregates with an evidence tier derived from balls faced:
High ≥ 30 balls, Medium ≥ 12, otherwise Limited. The bowler list is restricted to opponents
with recorded head-to-head deliveries, so an empty pairing returns 404 rather than a zero row.

## Known soft spots

Stated so they can be argued rather than discovered:

1. **Role thresholds are heuristics.** 18/18/36 balls are defensible but not canonical cricket
   definitions. They are isolated in one SQL macro and one constant block.
2. **No keeper is identified**, so a keeper-batter is scored as a batter.
3. **Form and consistency need ≥4 matches**; below that they report neutral with a reason.
4. **Single season only.** Nothing is normalised for era except within the selected season.
5. **Economy is approximate** because extras are not split by type — see [DATA.md](DATA.md).
