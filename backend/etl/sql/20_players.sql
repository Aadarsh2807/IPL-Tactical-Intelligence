-- ============================================================================
-- 20_players.sql  --  per-player season aggregates, role baselines, match trend
-- ----------------------------------------------------------------------------
-- This is the input to the role-adaptive stability score. Nothing here is
-- rounded or scored: SQL aggregates, Python applies the documented formulas.
-- ============================================================================

CREATE OR REPLACE TABLE gold_player_season AS
WITH batting AS (
    SELECT
        season,
        batting_team            AS team,
        batter                  AS player,
        SUM(runs_batter)        AS runs,
        SUM(legal_ball)         AS batting_balls,
        SUM(striker_dismissed)  AS dismissals
    FROM silver_deliveries
    WHERE NOT is_super_over
    GROUP BY season, batting_team, batter
),
bowling AS (
    SELECT
        season,
        bowling_team            AS team,
        bowler                  AS player,
        SUM(bowler_wicket)      AS wickets,
        SUM(bowler_runs)        AS runs_conceded,
        SUM(legal_ball)         AS bowling_balls
    FROM silver_deliveries
    WHERE NOT is_super_over
    GROUP BY season, bowling_team, bowler
),
appearances AS (
    SELECT season, team, player, COUNT(DISTINCT match_id) AS matches_played
    FROM (
        SELECT season, batting_team AS team, batter AS player, match_id
        FROM silver_deliveries WHERE NOT is_super_over
        UNION ALL
        SELECT season, bowling_team AS team, bowler AS player, match_id
        FROM silver_deliveries WHERE NOT is_super_over
    )
    GROUP BY season, team, player
),
combined AS (
    SELECT
        COALESCE(b.season,  w.season)   AS season,
        COALESCE(b.team,    w.team)     AS team,
        COALESCE(b.player,  w.player)   AS player,
        COALESCE(b.runs, 0)             AS runs,
        COALESCE(b.batting_balls, 0)    AS batting_balls,
        COALESCE(b.dismissals, 0)       AS dismissals,
        COALESCE(w.wickets, 0)          AS wickets,
        COALESCE(w.runs_conceded, 0)    AS runs_conceded,
        COALESCE(w.bowling_balls, 0)    AS bowling_balls
    FROM batting b
    FULL OUTER JOIN bowling w
      ON b.season = w.season AND b.team = w.team AND b.player = w.player
)
SELECT
    c.season,
    c.team,
    c.player,
    c.runs,
    c.batting_balls,
    c.dismissals,
    c.wickets,
    c.runs_conceded,
    c.bowling_balls,
    COALESCE(a.matches_played, 0)       AS matches_played,
    CASE WHEN c.batting_balls > 0
         THEN 100.0 * c.runs / c.batting_balls END   AS strike_rate,
    CASE WHEN c.bowling_balls > 0
         THEN 6.0 * c.runs_conceded / c.bowling_balls END AS economy,
    CASE WHEN c.dismissals > 0
         THEN CAST(c.runs AS DOUBLE) / c.dismissals END   AS batting_average,
    role_of(c.batting_balls, c.bowling_balls)       AS role
FROM combined c
LEFT JOIN appearances a
       ON a.season = c.season AND a.team = c.team AND a.player = c.player;

-- Season baselines, restricted to players who cleared the same role thresholds.
-- A player is compared with peers who faced a comparable workload, so a
-- pinch-hitter cannot define "average" for the league.
CREATE OR REPLACE TABLE gold_role_baselines AS
SELECT
    season,
    CAST(SUM(runs) FILTER (WHERE batting_balls >= 18) AS DOUBLE)
        / NULLIF(SUM(batting_balls) FILTER (WHERE batting_balls >= 18), 0)
                                                        AS bat_runs_per_ball,
    100.0 * SUM(runs) FILTER (WHERE batting_balls >= 18)
        / NULLIF(SUM(batting_balls) FILTER (WHERE batting_balls >= 18), 0)
                                                        AS bat_strike_rate,
    6.0 * SUM(runs_conceded) FILTER (WHERE bowling_balls >= 36)
        / NULLIF(SUM(bowling_balls) FILTER (WHERE bowling_balls >= 36), 0)
                                                        AS bowl_economy,
    CAST(SUM(wickets) FILTER (WHERE bowling_balls >= 36) AS DOUBLE)
        / NULLIF(SUM(bowling_balls) FILTER (WHERE bowling_balls >= 36), 0)
                                                        AS bowl_wicket_rate,
    COUNT(*) FILTER (WHERE batting_balls >= 18)         AS qualifying_batters,
    COUNT(*) FILTER (WHERE bowling_balls >= 36)         AS qualifying_bowlers
FROM gold_player_season
GROUP BY season;

-- Per-match contribution series. Drives the consistency component and the
-- sparkline in the UI. Bowling output = 20 x wickets - runs conceded, so a
-- wicket is worth roughly a boundary saved.
CREATE OR REPLACE TABLE gold_match_contrib AS
SELECT
    season,
    batting_team        AS team,
    batter              AS player,
    match_id,
    play_date,
    'batting'           AS discipline,
    CAST(SUM(runs_batter) AS DOUBLE)    AS output,
    SUM(legal_ball)                     AS balls,
    0                                    AS wickets,
    0                                    AS runs_conceded,
    SUM(striker_dismissed)              AS dismissals
FROM silver_deliveries
WHERE NOT is_super_over
GROUP BY season, batting_team, batter, match_id, play_date

UNION ALL

SELECT
    season,
    bowling_team        AS team,
    bowler              AS player,
    match_id,
    play_date,
    'bowling'           AS discipline,
    20.0 * SUM(bowler_wicket) - CAST(SUM(bowler_runs) AS DOUBLE) AS output,
    SUM(legal_ball)                     AS balls,
    SUM(bowler_wicket)                  AS wickets,
    SUM(bowler_runs)                    AS runs_conceded,
    0                                   AS dismissals
FROM silver_deliveries
WHERE NOT is_super_over
GROUP BY season, bowling_team, bowler, match_id, play_date;
