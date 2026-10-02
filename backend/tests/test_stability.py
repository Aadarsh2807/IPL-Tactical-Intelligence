"""Feature 1: the stability score must actually change with the role."""
from __future__ import annotations

import pytest

import analytics
import dataset


def test_role_weights_sum_to_one_and_differ_by_role():
    for role, weights in analytics.ROLE_WEIGHTS.items():
        assert abs(sum(weights.values()) - 1.0) < 1e-9, role
    assert analytics.ROLE_WEIGHTS["Batter"] != analytics.ROLE_WEIGHTS["All-rounder"]
    assert analytics.ROLE_WEIGHTS["Bowler"] != analytics.ROLE_WEIGHTS["All-rounder"]
    # an all-rounder is scored on both disciplines; a batter is not
    assert "bowl_output" in analytics.ROLE_WEIGHTS["All-rounder"]
    assert "bowl_output" not in analytics.ROLE_WEIGHTS["Batter"]


def test_role_of_macro_classifies_by_workload():
    """The SQL macro is the single source of truth for role assignment."""
    cases = [
        (200, 0, "Batter"),
        (0, 60, "Bowler"),
        (10, 20, "Bowler"),    # bowled properly, never batted
        (120, 120, "All-rounder"),
        (200, 5, "Batter"),    # part-time single over is not a bowling role
    ]
    for bat_balls, bowl_balls, expected in cases:
        got = dataset.value("SELECT role_of(?, ?)", [bat_balls, bowl_balls])
        assert got == expected, (bat_balls, bowl_balls, got)


def _sample_squad():
    season = analytics.seasons()[0]
    for team in analytics.teams(season):
        try:
            return season, team, analytics.stability_report(season, team)
        except analytics.NotFound:
            continue
    raise AssertionError("no squad available in the newest season")


def test_scores_are_bounded_and_confidence_reflects_sample():
    season, team, report = _sample_squad()
    assert report
    for player in report:
        assert 0 <= player["stability_score"] <= 100
        assert player["confidence"] in {"High", "Medium", "Low"}
        expected_band = {"High": 3, "Medium": 8, "Low": 15}[player["confidence"]]
        assert player["band"] == expected_band
        assert player["sample_balls"] > 0
        assert abs(sum(c["weight"] for c in player["components"]) - 1.0) < 0.01
        assert all(c["detail"] for c in player["components"])


def test_all_rounders_are_scored_on_both_disciplines():
    season, team, report = _sample_squad()
    all_rounders = [p for p in report if p["role"] == "All-rounder"]
    if not all_rounders:
        pytest.skip("sample squad has no all-rounder this season")
    for player in all_rounders:
        keys = {c["key"] for c in player["components"]}
        assert {"bat_output", "bowl_output"} <= keys


def test_report_is_deterministic():
    season, team, report = _sample_squad()
    assert report == analytics.stability_report(season, team)


def test_trend_series_comes_from_the_match_table():
    season, team, report = _sample_squad()
    player = report[0]
    discipline = "bowling" if player["role"] == "Bowler" else "batting"
    rows = dataset.query(
        "SELECT output FROM gold_match_contrib "
        "WHERE season = ? AND team = ? AND player = ? AND discipline = ? "
        "ORDER BY play_date, match_id",
        [season, team, player["player"], discipline],
    )
    assert len(player["trend"]) == len(rows)


def test_low_sample_players_are_marked_not_silent():
    """A three-match player must not be presented with high confidence."""
    season, team, report = _sample_squad()
    thin = [p for p in report if p["matches_played"] <= 3]
    if not thin:
        pytest.skip("all players have four or more matches")
    for player in thin:
        assert player["confidence"] == "Low"


def test_team_stability_weights_are_published_and_bounded(client):
    body = client.get("/api/method").json()
    weights = body["team_stability"]["weights"]
    assert abs(sum(weights.values()) - 1.0) < 1e-9
    season = client.get("/api/seasons").json()[0]
    team = client.get("/api/teams", params={"season": season}).json()[0]
    squad = client.get(f"/api/squad/{team}", params={"season": season}).json()
    assert 0 <= squad["stability_score"] <= 100
    assert set(squad["score_breakdown"]) == {
        "attack_index", "defence_index", "role_balance", "coverage"}


def test_score_contributions_add_back_to_the_score():
    """The report claims the four parts explain the score, so they must."""
    season, team, _ = _sample_squad()
    squad = analytics.squad(season, team)
    parts = squad["score_contributions"]
    assert len(parts) == len(analytics.TEAM_STABILITY_WEIGHTS)
    assert sum(part["points"] for part in parts) == squad["stability_score"]
    for part in parts:
        assert 0 <= part["points"] <= part["ceiling"]
        assert part["shortfall"] == part["ceiling"] - part["points"] >= 0
        assert part["label"] == analytics.PILLAR_LABELS[part["key"]]
    # Sorted biggest-first, which is the order the report reads them in.
    assert [p["points"] for p in parts] == sorted(
        (p["points"] for p in parts), reverse=True)
