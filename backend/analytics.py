"""Scoring rules: the only place numbers become meaning.

Every figure that reaches the UI is produced in exactly two layers:

  1. SQL (backend/etl/sql/*.sql) aggregates the raw dataset. It never rounds,
     scores or invents anything.
  2. This file applies documented, unit-testable formulas to those aggregates.

There is no model, no training and no hardcoded player or team name anywhere
in this module -- team and player identities always arrive from SQL.
"""
from __future__ import annotations

import statistics
from typing import Any, Iterable

import dataset

# ---------------------------------------------------------------------------
# Documented thresholds. Named here, referenced by tests and docs/SCORING.md.
# ---------------------------------------------------------------------------
MIN_BATTING_BALLS = 18          # a genuine innings, not one swing
MIN_BOWLING_BALLS_AR = 18       # a genuine spell for an all-rounder
MIN_BOWLING_BALLS = 36          # six overs: a real bowling allocation
QUALIFYING_BATTING_BALLS = 18   # peer group for batting baselines
QUALIFYING_BOWLING_BALLS = 36   # peer group for bowling baselines

CONFIDENCE_BALLS = ((200, "High"), (80, "Medium"))  # else "Low"
CONFIDENCE_BAND = {"High": 3, "Medium": 8, "Low": 15}  # +/- stability points

NEUTRAL_SCORE = 50.0            # returned when a sample cannot support a view
MIN_TREND_MATCHES = 4           # below this, form is reported as neutral

# Role-adaptive weights: the same player is scored on different criteria
# depending on the role the data says they played.
ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    "Batter": {
        "output": 0.45, "consistency": 0.25, "form": 0.15, "availability": 0.15,
    },
    "Bowler": {
        "output": 0.45, "consistency": 0.25, "form": 0.15, "availability": 0.15,
    },
    "All-rounder": {
        "bat_output": 0.30, "bowl_output": 0.30,
        "bat_consistency": 0.10, "bowl_consistency": 0.10,
        "form": 0.10, "availability": 0.10,
    },
}

TEAM_STABILITY_WEIGHTS = {
    "attack": 0.35, "defence": 0.35, "role_balance": 0.20, "coverage": 0.10,
}
# Reader-facing names for those four pillars. Kept beside the weights so the
# report never has to invent a label of its own.
PILLAR_LABELS = {
    "attack": "Batting",
    "defence": "Bowling",
    "role_balance": "Role balance",
    "coverage": "Season played",
}
QUALITY_BENCHMARK = 1.30        # a 1.30x league index scores full marks
MAX_COVERAGE_MATCHES = 14       # a full league stage

OUTLOOK_WEIGHTS = {"attack": 0.45, "defence": 0.35, "win_rate": 0.20}
OUTLOOK_ANCHOR = 0.90           # performance index that maps to a 50% estimate
OUTLOOK_BAND = (20, 80)         # bounded so history is never sold as certainty

XI_RULES = {"total": 11, "min_batters": 5, "min_bowlers": 4, "min_all_rounders": 1}
XI_WEIGHTS = {"quality": 0.60, "role_balance": 0.25, "depth": 0.15}
XI_DEPTH_BATTING = 6            # batters a balanced XI wants
XI_DEPTH_BOWLING = 4            # bowlers a balanced XI wants
# Reader-facing names for the three parts of the XI score.
XI_PART_LABELS = {
    "quality": "Player quality",
    "role_balance": "Role balance",
    "depth": "Squad depth",
}


class NotFound(ValueError):
    """Raised when a season, team or player does not exist in the data."""


def _round(value: float | None, digits: int = 1) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _score_ratio(ratio: float | None) -> float | None:
    """Map a ratio-to-baseline onto 0-100. 1.0x = league average = 50."""
    if ratio is None:
        return None
    return _round(100.0 * _clamp(ratio, 0.0, 2.0) / 2.0)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def seasons() -> list[str]:
    rows = dataset.query("SELECT DISTINCT season FROM silver_matches ORDER BY season DESC")
    return [row["season"] for row in rows]


def require_season(season: str) -> str:
    if season not in set(seasons()):
        raise NotFound(f"Season {season} is not present in the supplied IPL data")
    return season


def teams(season: str) -> list[str]:
    require_season(season)
    rows = dataset.query(
        """
        SELECT DISTINCT team FROM (
            SELECT team1 AS team, season FROM silver_matches
            UNION ALL
            SELECT team2 AS team, season FROM silver_matches
        ) WHERE season = ? ORDER BY team
        """,
        [season],
    )
    return [row["team"] for row in rows]


def require_team(season: str, team: str) -> str:
    if team not in teams(season):
        raise NotFound(f"{team} is not present in season {season}")
    return team


def batters(season: str, team: str | None = None) -> list[str]:
    require_season(season)
    if team:
        require_team(season, team)
        rows = dataset.query(
            "SELECT DISTINCT batter AS player FROM silver_deliveries "
            "WHERE season = ? AND batting_team = ? AND NOT is_super_over "
            "ORDER BY player",
            [season, team],
        )
    else:
        rows = dataset.query(
            "SELECT DISTINCT batter AS player FROM silver_deliveries "
            "WHERE season = ? AND NOT is_super_over ORDER BY player",
            [season],
        )
    return [row["player"] for row in rows]


def _team_row(season: str, team: str) -> dict[str, Any]:
    row = dataset.one(
        "SELECT * FROM gold_team_season WHERE season = ? AND team = ?",
        [season, team],
    )
    if not row:
        raise NotFound(f"{team} has no recorded deliveries in season {season}")
    return row


def _baseline(season: str) -> dict[str, Any] | None:
    return dataset.one("SELECT * FROM gold_role_baselines WHERE season = ?", [season])


def _squad_rows(season: str, team: str) -> list[dict[str, Any]]:
    return dataset.query(
        "SELECT * FROM gold_player_season WHERE season = ? AND team = ? "
        "ORDER BY runs DESC, wickets DESC, player ASC",
        [season, team],
    )


def _contributions(season: str, team: str) -> dict[tuple[str, str], list[dict]]:
    rows = dataset.query(
        "SELECT player, discipline, play_date, match_id, output, balls, wickets "
        "FROM gold_match_contrib WHERE season = ? AND team = ? "
        "ORDER BY player, discipline, play_date, match_id",
        [season, team],
    )
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        grouped.setdefault((row["player"], row["discipline"]), []).append(row)
    return grouped


# ---------------------------------------------------------------------------
# Component maths (shared by player stability)
# ---------------------------------------------------------------------------
def _batting_ratio(row: dict, baseline: dict | None) -> float | None:
    if not row["batting_balls"] or not baseline or not baseline.get("bat_runs_per_ball"):
        return None
    return (row["runs"] / row["batting_balls"]) / baseline["bat_runs_per_ball"]


def _bowling_ratio(row: dict, baseline: dict | None) -> float | None:
    if not row["bowling_balls"] or not baseline:
        return None
    parts: list[float] = []
    economy = row.get("economy")
    if economy and baseline.get("bowl_economy"):
        parts.append(0.6 * baseline["bowl_economy"] / economy)
    if baseline.get("bowl_wicket_rate"):
        wicket_rate = row["wickets"] / row["bowling_balls"]
        parts.append(0.4 * wicket_rate / baseline["bowl_wicket_rate"])
    return sum(parts) if parts else None


def _consistency(values: Iterable[float]) -> tuple[float, str]:
    """How repeatable the per-match output is. 100 = identical every match."""
    series = list(values)
    if len(series) < MIN_TREND_MATCHES:
        return NEUTRAL_SCORE, f"neutral: only {len(series)} matches"
    mean = statistics.fmean(series)
    spread = statistics.pstdev(series) / (abs(mean) + 1.0)
    return _round(100.0 * _clamp(1.0 - spread)), "ok"


def _form(series: list[float]) -> tuple[float, str]:
    """Second half vs first half of the season, scaled by the player's own
    match-to-match variation. 50 = unchanged, 100 = clearly improving.

    Scaling by the player's spread (rather than by the early mean) keeps the
    metric stable when a series passes through zero, which bowling output does.
    """
    if len(series) < MIN_TREND_MATCHES:
        return NEUTRAL_SCORE, f"neutral: only {len(series)} matches"
    split = len(series) // 2
    early, late = statistics.fmean(series[:split]), statistics.fmean(series[split:])
    spread = statistics.pstdev(series) + 1.0
    relative = (late - early) / spread
    return _round(50.0 + 50.0 * _clamp(relative, -1.0, 1.0)), "ok"


def _confidence(sample_balls: int) -> str:
    for threshold, label in CONFIDENCE_BALLS:
        if sample_balls >= threshold:
            return label
    return "Low"


def _availability(matches_played: int, team_matches: int) -> tuple[float, str]:
    if not team_matches:
        return NEUTRAL_SCORE, "no matches in season"
    share = _clamp(matches_played / team_matches, 0.0, 1.0)
    return _round(100.0 * share), f"{matches_played} of {team_matches} matches"


# ---------------------------------------------------------------------------
# Feature 1: role-adaptive player stability
# ---------------------------------------------------------------------------
def stability_report(season: str, team: str) -> list[dict[str, Any]]:
    require_team(season, team)
    squad = _squad_rows(season, team)
    if not squad:
        raise NotFound(f"{team} has no recorded players in season {season}")

    team_row = _team_row(season, team)
    baseline = _baseline(season)
    contributions = _contributions(season, team)

    report: list[dict[str, Any]] = []
    for row in squad:
        role = row["role"]
        weights = ROLE_WEIGHTS[role]
        batting_series = [c["output"] for c in contributions.get((row["player"], "batting"), [])]
        bowling_series = [c["output"] for c in contributions.get((row["player"], "bowling"), [])]

        bat_ratio, bowl_ratio = _batting_ratio(row, baseline), _bowling_ratio(row, baseline)
        bat_consistency, bat_note = _consistency(batting_series)
        bowl_consistency, bowl_note = _consistency(bowling_series)
        availability, availability_note = _availability(
            row["matches_played"], team_row["matches"])
        form_series = batting_series if role != "Bowler" else bowling_series
        form_score, form_note = _form(form_series)

        components: list[dict[str, Any]] = []
        if role == "Batter":
            primary_output, primary_consistency = _score_ratio(bat_ratio), bat_consistency
        elif role == "Bowler":
            primary_output, primary_consistency = _score_ratio(bowl_ratio), bowl_consistency
        else:
            primary_output, primary_consistency = None, None

        values: dict[str, float | None] = {
            "output": primary_output,
            "consistency": primary_consistency,
            "form": form_score,
            "availability": availability,
            "bat_output": _score_ratio(bat_ratio),
            "bowl_output": _score_ratio(bowl_ratio),
            "bat_consistency": bat_consistency,
            "bowl_consistency": bowl_consistency,
        }

        if role == "Batter":
            components = [
                {"key": "output", "label": "Scoring vs season baseline",
                 "weight": weights["output"], "score": values["output"],
                 "detail": f"{bat_ratio:.2f}x league scoring rate" if bat_ratio else "no qualifying batting"},
                {"key": "consistency", "label": "Per-match consistency",
                 "weight": weights["consistency"], "score": values["consistency"], "detail": bat_note},
                {"key": "form", "label": "Recent form", "weight": weights["form"],
                 "score": form_score, "detail": form_note},
                {"key": "availability", "label": "Availability", "weight": weights["availability"],
                 "score": availability, "detail": availability_note},
            ]
        elif role == "Bowler":
            components = [
                {"key": "output", "label": "Economy + wicket impact",
                 "weight": weights["output"], "score": values["output"],
                 "detail": f"{bowl_ratio:.2f}x league bowling impact" if bowl_ratio else "no qualifying bowling"},
                {"key": "consistency", "label": "Per-match consistency",
                 "weight": weights["consistency"], "score": values["consistency"], "detail": bowl_note},
                {"key": "form", "label": "Recent form", "weight": weights["form"],
                 "score": form_score, "detail": form_note},
                {"key": "availability", "label": "Availability", "weight": weights["availability"],
                 "score": availability, "detail": availability_note},
            ]
        else:  # All-rounder: both disciplines are scored separately and both count
            components = [
                {"key": "bat_output", "label": "Batting vs baseline",
                 "weight": weights["bat_output"], "score": values["bat_output"],
                 "detail": f"{bat_ratio:.2f}x league scoring rate" if bat_ratio else "no qualifying batting"},
                {"key": "bowl_output", "label": "Bowling vs baseline",
                 "weight": weights["bowl_output"], "score": values["bowl_output"],
                 "detail": f"{bowl_ratio:.2f}x league bowling impact" if bowl_ratio else "no qualifying bowling"},
                {"key": "bat_consistency", "label": "Batting consistency",
                 "weight": weights["bat_consistency"], "score": bat_consistency, "detail": bat_note},
                {"key": "bowl_consistency", "label": "Bowling consistency",
                 "weight": weights["bowl_consistency"], "score": bowl_consistency, "detail": bowl_note},
                {"key": "form", "label": "Recent form", "weight": weights["form"],
                 "score": form_score, "detail": form_note},
                {"key": "availability", "label": "Availability", "weight": weights["availability"],
                 "score": availability, "detail": availability_note},
            ]

        usable = [c for c in components if c["score"] is not None]
        score = sum(c["weight"] * c["score"] for c in usable)
        weight_total = sum(c["weight"] for c in usable)
        normalised = score / weight_total if weight_total else NEUTRAL_SCORE

        if role == "All-rounder":
            sample_balls = min(row["batting_balls"], row["bowling_balls"])
        elif role == "Bowler":
            sample_balls = row["bowling_balls"]
        else:
            sample_balls = row["batting_balls"]
        confidence = _confidence(sample_balls)

        primary = bowling_series if role == "Bowler" else batting_series
        report.append({
            "player": row["player"],
            "role": role,
            "stability_score": round(normalised),
            "confidence": confidence,
            "band": CONFIDENCE_BAND[confidence],
            "sample_balls": int(sample_balls),
            "matches_played": int(row["matches_played"]),
            "components": [
                {**c, "score": _round(c["score"]), "weight": round(c["weight"], 2)}
                for c in usable
            ],
            "trend": [round(float(value), 1) for value in primary],
            "runs": int(row["runs"]),
            "batting_balls": int(row["batting_balls"]),
            "strike_rate": _round(row["strike_rate"]),
            "dismissals": int(row["dismissals"]),
            "wickets": int(row["wickets"]),
            "bowling_balls": int(row["bowling_balls"]),
            "economy": _round(row["economy"]),
        })
    report.sort(key=lambda item: (-item["stability_score"], item["player"]))
    return report


def _role_counts(players: Iterable[dict]) -> dict[str, int]:
    counts = {"Batter": 0, "All-rounder": 0, "Bowler": 0}
    for player in players:
        counts[player["role"]] = counts.get(player["role"], 0) + 1
    return counts


def team_stability(season: str, team: str, players: list[dict]) -> dict[str, Any]:
    """Squad-level stability: team output against the season baseline."""
    row = _team_row(season, team)
    counts = _role_counts(players)
    batting_depth = sum(1 for p in players if p["batting_balls"] >= MIN_BATTING_BALLS)
    bowling_depth = sum(1 for p in players if p["bowling_balls"] >= MIN_BOWLING_BALLS)
    attack = row["attack_index"] or 0.0
    defence = row["defence_index"] or 0.0
    role_balance = (min(batting_depth / XI_DEPTH_BATTING, 1.0)
                    + min(bowling_depth / (XI_DEPTH_BOWLING + 1), 1.0)) / 2.0
    coverage = min((row["matches"] or 0) / MAX_COVERAGE_MATCHES, 1.0)

    # Each pillar expressed as a share of the 0-100 score, so a report can say
    # which one actually moved the number instead of just restating it.
    pillars = {
        "attack": TEAM_STABILITY_WEIGHTS["attack"] * min(attack / QUALITY_BENCHMARK, 1.0),
        "defence": TEAM_STABILITY_WEIGHTS["defence"] * min(defence / QUALITY_BENCHMARK, 1.0),
        "role_balance": TEAM_STABILITY_WEIGHTS["role_balance"] * role_balance,
        "coverage": TEAM_STABILITY_WEIGHTS["coverage"] * coverage,
    }
    score = round(100 * sum(pillars.values()))

    # Whole points, because "26 of 84" is readable and "26.0 of 84" is not.
    # Rounding drift goes to the largest pillar so the four parts always add
    # back to the score the reader is shown.
    contributions = {key: round(100 * value) for key, value in pillars.items()}
    lead = max(contributions, key=lambda key: contributions[key])
    contributions[lead] += score - sum(contributions.values())

    return {
        "score": score,
        "attack_index": _round(attack, 3),
        "defence_index": _round(defence, 3),
        "role_balance": _round(100 * role_balance),
        "coverage": _round(100 * coverage),
        "batting_depth": batting_depth,
        "bowling_depth": bowling_depth,
        "role_counts": counts,
        # Sorted biggest-first, with the published ceiling beside each pillar so
        # "maxed out" is a fact rather than a guess.
        "contributions": sorted(
            (
                {
                    "key": key,
                    "label": PILLAR_LABELS[key],
                    "points": points,
                    "ceiling": round(100 * TEAM_STABILITY_WEIGHTS[key]),
                    # How much this pillar left on the table. Always >= 0 once
                    # the rounding drift has been absorbed above.
                    "shortfall": max(0, round(100 * TEAM_STABILITY_WEIGHTS[key]) - points),
                }
                for key, points in contributions.items()
            ),
            key=lambda item: (-item["points"], item["key"]),
        ),
        "matches": int(row["matches"]),
        "method": "35% attack index, 35% defence index, 20% role balance, "
                  "10% match coverage; each quality index is measured against the "
                  f"season baseline and capped at {QUALITY_BENCHMARK * 100:.0f}% of it",
    }


def role_mix_comment(counts: dict[str, int]) -> str:
    """Plain-language verdict on a squad's shape. Mirrored in frontend/src/lib/format.js."""
    batters = counts.get("Batter", 0)
    all_rounders = counts.get("All-rounder", 0)
    bowlers = counts.get("Bowler", 0)
    if bowlers < 4:
        return "short on bowling"
    if batters < 5:
        return "short on batting"
    if batters >= 6 and bowlers >= 5 and all_rounders >= 1:
        return "well balanced"
    return "adequate"


def _swot(season: str, team: str, team_report: dict) -> dict[str, str]:
    """Evidence-led SWOT written for a human, not for a statistician.

    Every sentence is a measured value, but the values are rounded and expressed
    as percentages of the league average, because "bowling was 4% tighter than
    the league average" is answerable without knowing what an index is.
    """
    row = _team_row(season, team)
    league = row["league_avg_innings"]
    league_text = f"{league:.0f}"
    scored_delta = round(((row["attack_index"] or 0.0) - 1.0) * 100)
    conceded_delta = round(((row["defence_index"] or 0.0) - 1.0) * 100)

    def batting_text() -> str:
        if abs(scored_delta) < 2:
            return (f"Batting matched the {season} league average of {league_text} "
                    f"runs per innings.")
        word = "more" if scored_delta > 0 else "fewer"
        return (f"Batting scored {abs(scored_delta)}% {word} runs than the league "
                f"average of {league_text} runs per innings ({row['avg_scored']:.0f} "
                f"scored).")

    def bowling_text() -> str:
        if abs(conceded_delta) < 2:
            return (f"Bowling matched the {season} league average of {league_text} "
                    f"runs conceded per innings.")
        word = "fewer" if conceded_delta > 0 else "more"
        return (f"Bowling conceded {abs(conceded_delta)}% {word} runs than the league "
                f"average of {league_text} ({row['avg_conceded']:.0f} conceded).")

    best, worst = ((batting_text, bowling_text) if scored_delta >= conceded_delta
                   else (bowling_text, batting_text))
    if batting_text() == bowling_text():
        strength = batting_text() + " Neither side of the game stood out."
        weakness = ("Attack and defence both sat close to the league average, so results "
                    "came down to individual performances rather than team strength.")
    else:
        strength = best() + " This is the stronger of the two sides."
        weakness = worst() + " This is the side to watch."

    counts = team_report["role_counts"]
    decided = row["decided_matches"] or 0
    excluded = (row["no_result_matches"] or 0) + (row["tied_matches"] or 0)

    if decided < 10:
        threat = (f"Only {decided} of {row['matches']} matches had a result, so the "
                  f"win rate rests on a small sample — treat it as a rough guide.")
    elif excluded:
        threat = (f"{excluded} unfinished or tied matches are excluded (along with "
                  f"their super overs), so the evidence base is the {decided} matches "
                  f"that did produce a result.")
    else:
        threat = (f"All {row['matches']} matches had a result, so the evidence base is "
                  f"the full season.")

    return {
        "strength": strength,
        "weakness": weakness,
        "opportunity": (
            f"Squad depth is {role_mix_comment(counts)}: {counts['Batter']} batters, "
            f"{counts['All-rounder']} all-rounders and {counts['Bowler']} bowlers "
            f"scored or bowled in this season, with "
            f"{team_report['batting_depth']} of them batting at least "
            f"{MIN_BATTING_BALLS} balls and {team_report['bowling_depth']} bowling at "
            f"least {MIN_BOWLING_BALLS} balls."
        ),
        "threat": threat,
    }


def squad(season: str, team: str) -> dict[str, Any]:
    players = stability_report(season, team)
    team_report = team_stability(season, team, players)
    notes = [
        f"{team_report['matches']} matches in season {season}; "
        f"{len(players)} players with a recorded contribution.",
        "Only deliveries for the chosen team and season are included, "
        "and super overs are excluded from every aggregate.",
    ]
    return {
        "team": team,
        "season": season,
        "stability_score": team_report["score"],
        "score_method": team_report["method"],
        "score_breakdown": {
            "attack_index": team_report["attack_index"],
            "defence_index": team_report["defence_index"],
            "role_balance": team_report["role_balance"],
            "coverage": team_report["coverage"],
        },
        "score_contributions": team_report["contributions"],
        "role_counts": team_report["role_counts"],
        "swot": _swot(season, team, team_report),
        "notes": notes,
        "players": players,
    }


# ---------------------------------------------------------------------------
# Feature 3 (existing): season outlook
# ---------------------------------------------------------------------------
def outlook(season: str, team: str) -> dict[str, Any]:
    row = _team_row(season, team)
    attack = row["attack_index"] or 0.0
    defence = row["defence_index"] or 0.0
    decided = row["decided_matches"] or 0
    win_rate = row["win_rate"] if row["win_rate"] is not None else 0.5
    performance_index = (OUTLOOK_WEIGHTS["attack"] * attack
                         + OUTLOOK_WEIGHTS["defence"] * defence
                         + OUTLOOK_WEIGHTS["win_rate"] * win_rate)
    probability = max(OUTLOOK_BAND[0], min(OUTLOOK_BAND[1],
                     round(50 + (performance_index - OUTLOOK_ANCHOR) * 100)))
    return {
        "team": team,
        "season": season,
        "matches": int(row["matches"]),
        "wins": int(row["wins"]),
        "decided_matches": decided,
        "win_rate": _round(100 * win_rate),
        "average_score": _round(row["avg_scored"]),
        "average_conceded": _round(row["avg_conceded"]),
        "league_average": _round(row["league_avg_innings"]),
        "attack_index": _round(attack, 3),
        "defence_index": _round(defence, 3),
        "performance_index": _round(performance_index, 3),
        "next_match_win_probability": probability,
        "method": "45% seasonal scoring index, 35% seasonal defence index, 20% "
                  "decided-match win rate; bounded to 20-80% so a historical "
                  "model is never presented as certainty.",
        "limitation": ("Estimate is based on a small sample: "
                       f"{decided} decided matches." if decided < 10
                       else "Estimate reflects the completed season only and "
                            "ignores venue, opposition and team changes."),
    }


# ---------------------------------------------------------------------------
# Matchups
# ---------------------------------------------------------------------------
def bowlers_for_batter(season: str, batter: str) -> list[str]:
    require_season(season)
    rows = dataset.query(
        "SELECT DISTINCT bowler FROM gold_matchups "
        "WHERE season = ? AND batter = ? ORDER BY bowler",
        [season, batter],
    )
    if not rows:
        raise NotFound(f"{batter} has no recorded deliveries in season {season}")
    return [row["bowler"] for row in rows]


def matchup(season: str, batter: str, bowler: str) -> dict[str, Any]:
    require_season(season)
    row = dataset.one(
        "SELECT * FROM gold_matchups WHERE season = ? AND batter = ? AND bowler = ?",
        [season, batter, bowler],
    )
    if not row:
        raise NotFound("This pair has no recorded head-to-head deliveries in that season")
    balls = row["balls"]
    runs = row["runs"]
    legal = row["legal_balls"]
    evidence = "High" if balls >= 30 else "Medium" if balls >= 12 else "Limited"
    return {
        "season": season,
        "batter": batter,
        "bowler": bowler,
        "matches": int(row["matches"]),
        "balls": int(balls),
        "runs": int(runs),
        "dismissals": int(row["dismissals"]),
        "strike_rate": _round(100 * runs / balls) if balls else 0.0,
        "bowler_economy": _round(6 * row["bowler_runs"] / legal) if legal else None,
        "evidence": evidence,
        "evidence_note": f"{balls} balls across {row['matches']} matches",
        "message": f"Head-to-head evidence from {season} IPL deliveries.",
    }


# ---------------------------------------------------------------------------
# Feature 2: XI builder
# ---------------------------------------------------------------------------
def _validate_xi(names: list[str], squad_players: list[dict]) -> list[str]:
    available = {p["player"] for p in squad_players}
    violations: list[str] = []
    unknown = sorted(set(names) - available)
    if unknown:
        violations.append("Not in this squad: " + ", ".join(unknown))
    if len(set(names)) != len(names):
        violations.append("Duplicate players in selection")
    if len(names) != XI_RULES["total"]:
        violations.append(f"Select exactly {XI_RULES['total']} players "
                          f"(currently {len(names)})")
    return violations


def xi_breakdown(selected: list[dict], team_row: dict) -> dict[str, Any]:
    """Score a selection. Quality = mean stability; balance and depth follow."""
    counts = _role_counts(selected)
    quality = statistics.fmean(p["stability_score"] for p in selected)
    n = len(selected)
    role_balance = (
        min(counts["Batter"] / XI_RULES["min_batters"], 1.0)
        + min(counts["Bowler"] / XI_RULES["min_bowlers"], 1.0)
        + min(counts["All-rounder"] / XI_RULES["min_all_rounders"], 1.0)
    ) / 3.0
    batting_depth = sum(1 for p in selected if p["batting_balls"] >= MIN_BATTING_BALLS)
    bowling_depth = sum(1 for p in selected if p["bowling_balls"] >= MIN_BOWLING_BALLS)
    depth = (min(batting_depth / XI_DEPTH_BATTING, 1.0)
             + min(bowling_depth / XI_DEPTH_BOWLING, 1.0)) / 2.0

    # Same shape as the squad score: the three parts, as whole points that add
    # back to the total, so a report can say what the selection is made of.
    parts = {
        "quality": XI_WEIGHTS["quality"] * quality,
        "role_balance": XI_WEIGHTS["role_balance"] * 100 * role_balance,
        "depth": XI_WEIGHTS["depth"] * 100 * depth,
    }
    score = round(sum(parts.values()))
    contributions = {key: round(value) for key, value in parts.items()}
    lead = max(contributions, key=lambda key: contributions[key])
    contributions[lead] += score - sum(contributions.values())

    return {
        "score": score,
        "quality": round(quality),
        "role_balance": round(100 * role_balance),
        "depth": round(100 * depth),
        "contributions": sorted(
            (
                {
                    "key": key,
                    "label": XI_PART_LABELS[key],
                    "points": points,
                    "ceiling": round(100 * XI_WEIGHTS[key]),
                    "shortfall": max(0, round(100 * XI_WEIGHTS[key]) - points),
                }
                for key, points in contributions.items()
            ),
            key=lambda item: (-item["points"], item["key"]),
        ),
        "role_counts": counts,
        "batting_depth": batting_depth,
        "bowling_depth": bowling_depth,
        "selected": n,
        "method": "60% mean player stability, 25% role balance (>=5 batters, "
                  ">=4 bowlers, >=1 all-rounder), 15% depth (players with a "
                  "qualifying workload in each discipline)",
    }


def score_xi(season: str, team: str, names: list[str]) -> dict[str, Any]:
    require_team(season, team)
    squad_players = stability_report(season, team)
    by_name = {p["player"]: p for p in squad_players}
    violations = _validate_xi(names, squad_players)
    selected = [by_name[name] for name in names if name in by_name]
    breakdown = None
    if not violations:
        breakdown = xi_breakdown(selected, _team_row(season, team))
    return {
        "team": team,
        "season": season,
        "players": list(names),
        "valid": not violations,
        "violations": violations,
        "breakdown": breakdown,
        "selection": [
            {"player": p["player"], "role": p["role"],
             "stability_score": p["stability_score"]}
            for p in selected
        ],
    }


def auto_xi(season: str, team: str) -> dict[str, Any]:
    """Deterministic best XI: enumerate legal role splits, take the best.

    No randomness and no model -- the same squad always yields the same XI,
    which is what makes it auditable in an interview.
    """
    require_team(season, team)
    squad_players = stability_report(season, team)
    by_role: dict[str, list[dict]] = {}
    for player in sorted(squad_players, key=lambda p: (-p["stability_score"], p["player"])):
        by_role.setdefault(player["role"], []).append(player)

    required = XI_RULES
    best: tuple | None = None
    considered = 0
    for batters in range(required["min_batters"], XI_RULES["total"] + 1):
        for all_rounders in range(required["min_all_rounders"], XI_RULES["total"] + 1):
            bowlers = XI_RULES["total"] - batters - all_rounders
            if bowlers < required["min_bowlers"]:
                continue
            if len(by_role.get("Batter", [])) < batters:
                continue
            if len(by_role.get("All-rounder", [])) < all_rounders:
                continue
            if len(by_role.get("Bowler", [])) < bowlers:
                continue
            picked = (by_role["Batter"][:batters]
                      + by_role["All-rounder"][:all_rounders]
                      + by_role["Bowler"][:bowlers])
            breakdown = xi_breakdown(picked, _team_row(season, team))
            considered += 1
            key = (-breakdown["score"], sorted(p["player"] for p in picked))
            if best is None or key < best[0]:
                best = (key, picked, breakdown)

    if best is None:
        raise NotFound(
            f"{team} has no legal XI in {season}: a selection needs at least "
            f"{required['min_batters']} batters, {required['min_bowlers']} bowlers "
            f"and {required['min_all_rounders']} all-rounder in the squad."
        )

    _, picked, breakdown = best
    picked = sorted(picked, key=lambda p: (p["role"], -p["stability_score"], p["player"]))
    return {
        "team": team,
        "season": season,
        "players": [p["player"] for p in picked],
        "valid": True,
        "violations": [],
        "breakdown": breakdown,
        "role_splits_considered": considered,
        "selection": [
            {"player": p["player"], "role": p["role"],
             "stability_score": p["stability_score"]}
            for p in picked
        ],
    }
