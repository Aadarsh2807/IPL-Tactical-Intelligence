-- ============================================================================
-- 00_silver.sql  --  raw CSV ingestion + normalised (silver) tables
-- ----------------------------------------------------------------------------
-- Every derived column is declared here, once, so it can be read top-to-bottom
-- and audited. Objects are TABLES, not views: the dataset is read-only, so
-- the loader materialises them once into data/warehouse.duckdb instead of
-- re-parsing a 22 MB CSV on every request.
-- Two placeholders are substituted at load time:
--     {{MATCHES_CSV}}      path to ipl_matches_clean.csv
--     {{DELIVERIES_CSV}}   path to ipl_deliveries_clean.csv
-- ============================================================================

-- Role inference. The single source of truth for "what is this player":
--   All-rounder  both disciplines used enough to matter (>= 18 balls each)
--   Bowler       bowled a real allocation (>= 36 balls = 6 overs), or bowled
--                meaningfully (>= 18) without ever batting properly (< 18)
--   Batter       everything else, including keeper-batters (the dataset has no
--                keeping dimension, so no keeper role is invented)
CREATE OR REPLACE MACRO role_of(bat_balls, bowl_balls) AS
CASE
    WHEN bat_balls >= 18 AND bowl_balls >= 18 THEN 'All-rounder'
    WHEN bowl_balls >= 36                      THEN 'Bowler'
    WHEN bowl_balls >= 18 AND bat_balls < 18   THEN 'Bowler'
    ELSE 'Batter'
END;

CREATE OR REPLACE TABLE raw_matches AS
SELECT * FROM read_csv('{{MATCHES_CSV}}', header = true, sample_size = -1);

CREATE OR REPLACE TABLE raw_deliveries AS
SELECT * FROM read_csv('{{DELIVERIES_CSV}}', header = true, sample_size = -1);

-- Match level: season, teams, result. Empty strings become NULL so that
-- "no winner recorded" is never confused with a team called "".
CREATE OR REPLACE TABLE silver_matches AS
SELECT
    CAST(match_id AS BIGINT)                       AS match_id,
    CAST("date" AS DATE)                           AS play_date,
    CAST(season AS VARCHAR)                        AS season,
    NULLIF(CAST(venue AS VARCHAR), '')             AS venue,
    NULLIF(CAST(city AS VARCHAR), '')              AS city,
    CAST(team1 AS VARCHAR)                         AS team1,
    CAST(team2 AS VARCHAR)                         AS team2,
    NULLIF(CAST(toss_winner AS VARCHAR), '')       AS toss_winner,
    NULLIF(CAST(toss_decision AS VARCHAR), '')     AS toss_decision,
    NULLIF(CAST(winner AS VARCHAR), '')            AS winner,
    CAST(result_type AS VARCHAR)                   AS result_type,
    TRY_CAST(result_margin AS DOUBLE)              AS result_margin,
    NULLIF(CAST(player_of_match AS VARCHAR), '')   AS player_of_match,
    CAST(result_type AS VARCHAR) IN ('runs', 'wickets') AS decided,
    CAST(result_type AS VARCHAR) = 'tie'           AS is_tie,
    CAST(result_type AS VARCHAR) = 'no result'     AS no_result
FROM raw_matches;

-- Delivery level. Key derivations:
--   bowling_team    the other side of the match (team1/team2), never guessed
--   is_super_over   innings > 2 exists in 16 tied matches; excluded downstream
--   legal_ball      ASSUMED 1: the source CSV has no extras_type column
--   bowler_runs     APPROXIMATE: runs_total; byes/leg-byes cannot be separated
--   bowler_wicket   bowler credited only when the dismissal method is recorded
--                   and is not a non-bowler dismissal
--   striker_dismissed  the batter was out, excluding retired hurt
CREATE OR REPLACE TABLE silver_deliveries AS
SELECT
    CAST(d.match_id AS BIGINT)                     AS match_id,
    m.season                                       AS season,
    m.play_date                                    AS play_date,
    CAST(d.innings AS INTEGER)                     AS innings,
    CAST(d.innings AS INTEGER) > 2                 AS is_super_over,
    CAST(d.over AS INTEGER)                        AS over_number,
    CAST(d.ball AS INTEGER)                        AS ball_number,
    CAST(d.batting_team AS VARCHAR)                AS batting_team,
    CASE WHEN CAST(d.batting_team AS VARCHAR) = m.team1
         THEN m.team2 ELSE m.team1 END             AS bowling_team,
    CAST(d.batter AS VARCHAR)                      AS batter,
    CAST(d.bowler AS VARCHAR)                      AS bowler,
    CAST(d.non_striker AS VARCHAR)                 AS non_striker,
    CAST(d.runs_batter AS INTEGER)                 AS runs_batter,
    CAST(d.runs_extras AS INTEGER)                 AS runs_extras,
    CAST(d.runs_total AS INTEGER)                  AS runs_total,
    CAST(d.wicket AS INTEGER)                      AS wicket,
    NULLIF(CAST(d.wicket_kind AS VARCHAR), '')     AS wicket_kind,
    NULLIF(CAST(d.wicket_player_out AS VARCHAR),'')AS player_out,
    1                                              AS legal_ball,
    CAST(d.runs_total AS INTEGER)                  AS bowler_runs,
    CASE
        WHEN CAST(d.wicket AS INTEGER) = 1
         AND NULLIF(CAST(d.wicket_kind AS VARCHAR), '') NOT IN
             ('run out', 'retired hurt', 'retired out', 'obstructing the field')
         AND NULLIF(CAST(d.wicket_kind AS VARCHAR), '') IS NOT NULL
        THEN 1 ELSE 0
    END                                            AS bowler_wicket,
    CASE
        WHEN CAST(d.wicket AS INTEGER) = 1
         AND NULLIF(CAST(d.wicket_player_out AS VARCHAR), '') = CAST(d.batter AS VARCHAR)
         AND COALESCE(NULLIF(CAST(d.wicket_kind AS VARCHAR), ''), '') <> 'retired hurt'
        THEN 1 ELSE 0
    END                                            AS striker_dismissed,
    m.winner                                       AS winner,
    m.result_type                                  AS result_type,
    m.decided                                      AS decided
FROM raw_deliveries d
JOIN silver_matches m ON m.match_id = CAST(d.match_id AS BIGINT);
