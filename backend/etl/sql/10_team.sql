-- ============================================================================
-- 10_team.sql  --  innings, league baseline and per-team season metrics
-- ----------------------------------------------------------------------------
-- Super overs (innings > 2) are excluded everywhere: they belong to tied
-- matches and would otherwise distort every average.
-- ============================================================================

CREATE OR REPLACE TABLE gold_innings AS
SELECT
    match_id,
    season,
    innings,
    batting_team,
    bowling_team,
    SUM(runs_total) AS runs_innings
FROM silver_deliveries
WHERE NOT is_super_over
GROUP BY match_id, season, innings, batting_team, bowling_team;

-- League baseline: the mean innings score for a season. Every attack/defence
-- index in the app is expressed relative to this number.
CREATE OR REPLACE TABLE gold_league AS
SELECT
    season,
    AVG(runs_innings)            AS league_avg_innings,
    COUNT(*)                     AS innings_count,
    COUNT(DISTINCT match_id)     AS matches
FROM gold_innings
GROUP BY season;

CREATE OR REPLACE TABLE gold_match_results AS
SELECT
    season,
    team,
    COUNT(*)                              AS matches,
    COUNT(*) FILTER (WHERE decided)       AS decided_matches,
    COUNT(*) FILTER (WHERE winner = team) AS wins,
    COUNT(*) FILTER (WHERE is_tie)        AS tied_matches,
    COUNT(*) FILTER (WHERE no_result)     AS no_result_matches
FROM (
    SELECT season, team1 AS team, winner, decided, is_tie, no_result FROM silver_matches
    UNION ALL
    SELECT season, team2 AS team, winner, decided, is_tie, no_result FROM silver_matches
)
GROUP BY season, team;

CREATE OR REPLACE TABLE gold_team_season AS
WITH scored AS (
    SELECT season, batting_team AS team, AVG(runs_innings) AS avg_scored
    FROM gold_innings GROUP BY season, batting_team
),
conceded AS (
    SELECT season, bowling_team AS team, AVG(runs_innings) AS avg_conceded
    FROM gold_innings GROUP BY season, bowling_team
)
SELECT
    r.season,
    r.team,
    r.matches,
    r.decided_matches,
    r.wins,
    r.tied_matches,
    r.no_result_matches,
    s.avg_scored,
    c.avg_conceded,
    l.league_avg_innings,
    l.innings_count,
    s.avg_scored / l.league_avg_innings                       AS attack_index,
    l.league_avg_innings / c.avg_conceded                     AS defence_index,
    CASE WHEN r.decided_matches > 0
         THEN CAST(r.wins AS DOUBLE) / r.decided_matches END AS win_rate
FROM gold_match_results r
JOIN scored   s ON s.season = r.season AND s.team = r.team
JOIN conceded c ON c.season = r.season AND c.team = r.team
JOIN gold_league l ON l.season = r.season;
