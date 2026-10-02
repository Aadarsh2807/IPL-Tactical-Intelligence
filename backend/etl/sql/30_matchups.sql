-- ============================================================================
-- 30_matchups.sql  --  batter x bowler head-to-head, one row per season pair
-- ----------------------------------------------------------------------------
-- Super overs excluded for consistency with every other aggregate.
-- ============================================================================

CREATE OR REPLACE TABLE gold_matchups AS
SELECT
    season,
    batter,
    bowler,
    COUNT(*)                                   AS balls,
    COUNT(DISTINCT match_id)                   AS matches,
    SUM(runs_batter)                           AS runs,
    SUM(CASE WHEN player_out = batter
             THEN bowler_wicket ELSE 0 END)    AS dismissals,
    SUM(legal_ball)                            AS legal_balls,
    SUM(bowler_runs)                           AS bowler_runs
FROM silver_deliveries
WHERE NOT is_super_over
GROUP BY season, batter, bowler;
