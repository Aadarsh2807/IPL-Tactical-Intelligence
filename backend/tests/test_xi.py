"""Feature 2: the XI builder must always produce a legal, explainable side."""
from __future__ import annotations

import pytest

import analytics


def _squad_with_xi():
    season = analytics.seasons()[0]
    for team in analytics.teams(season):
        try:
            return season, team, analytics.auto_xi(season, team)
        except analytics.NotFound:
            continue
    raise AssertionError("no team in the newest season can field a legal XI")


def test_auto_xi_is_eleven_distinct_players_from_the_squad():
    season, team, xi = _squad_with_xi()
    names = xi["players"]
    assert len(names) == 11
    assert len(set(names)) == 11
    squad_names = {p["player"] for p in analytics.stability_report(season, team)}
    assert set(names) <= squad_names


def test_auto_xi_respects_role_constraints():
    _, _, xi = _squad_with_xi()
    counts = xi["breakdown"]["role_counts"]
    assert counts["Batter"] >= analytics.XI_RULES["min_batters"]
    assert counts["Bowler"] >= analytics.XI_RULES["min_bowlers"]
    assert counts["All-rounder"] >= analytics.XI_RULES["min_all_rounders"]
    assert sum(counts.values()) == 11


def test_auto_xi_is_deterministic():
    season, team, first = _squad_with_xi()
    assert analytics.auto_xi(season, team) == first


def test_scoring_the_auto_xi_agrees_with_the_solver():
    season, team, xi = _squad_with_xi()
    rescored = analytics.score_xi(season, team, xi["players"])
    assert rescored["valid"], rescored["violations"]
    assert rescored["breakdown"]["score"] == xi["breakdown"]["score"]


def test_xi_contributions_add_back_to_the_score():
    """The report draws the XI score as three parts; they must reconcile."""
    season, team, xi = _squad_with_xi()
    parts = xi["breakdown"]["contributions"]
    assert len(parts) == len(analytics.XI_WEIGHTS)
    assert sum(part["points"] for part in parts) == xi["breakdown"]["score"]
    for part in parts:
        assert 0 <= part["points"] <= part["ceiling"]
        assert part["shortfall"] == part["ceiling"] - part["points"] >= 0
        assert part["label"] == analytics.XI_PART_LABELS[part["key"]]


def test_breakdown_weights_are_published_and_complete():
    _, _, xi = _squad_with_xi()
    breakdown = xi["breakdown"]
    assert abs(sum(analytics.XI_WEIGHTS.values()) - 1.0) < 1e-9
    assert breakdown["selected"] == 11
    assert breakdown["method"]


def test_invalid_selections_are_rejected_with_reasons():
    season, team, xi = _squad_with_xi()
    too_few = analytics.score_xi(season, team, xi["players"][:5])
    assert not too_few["valid"]
    assert any("exactly 11" in violation for violation in too_few["violations"])
    assert too_few["breakdown"] is None

    unknown = analytics.score_xi(season, team,
                                 ["Not A Real Player"] + xi["players"][1:11])
    assert not unknown["valid"]
    assert any("Not in this squad" in violation for violation in unknown["violations"])

    duplicated = analytics.score_xi(season, team,
                                    [xi["players"][0]] + xi["players"][0:10])
    assert not duplicated["valid"]
    assert any("Duplicate" in violation for violation in duplicated["violations"])


def test_unknown_season_is_reported_not_guessed():
    with pytest.raises(analytics.NotFound):
        analytics.auto_xi("1899", "Nobody")
