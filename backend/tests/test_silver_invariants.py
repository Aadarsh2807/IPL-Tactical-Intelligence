"""Invariants of the normalised (silver) data.

These are the checks that stop a wrong number from ever reaching the UI:
they are written against the dataset itself, not against expected outputs.
"""
from __future__ import annotations

import dataset


def test_runs_total_equals_batter_plus_extras():
    bad = dataset.value(
        "SELECT COUNT(*) FROM silver_deliveries "
        "WHERE runs_total <> runs_batter + runs_extras"
    )
    assert bad == 0, "runs_total must be the sum of its parts on every row"


def test_bowler_is_never_credited_for_a_non_bowler_dismissal():
    bad = dataset.value(
        "SELECT COUNT(*) FROM silver_deliveries "
        "WHERE wicket_kind IN ('run out', 'retired hurt', 'retired out', "
        "'obstructing the field') AND bowler_wicket = 1"
    )
    assert bad == 0, "run outs and retired batters must not credit the bowler"


def test_every_bowler_wicket_is_an_actual_wicket():
    bad = dataset.value(
        "SELECT COUNT(*) FROM silver_deliveries WHERE bowler_wicket = 1 AND wicket = 0"
    )
    assert bad == 0


def test_retired_hurt_is_not_a_dismissal():
    bad = dataset.value(
        "SELECT COUNT(*) FROM silver_deliveries "
        "WHERE wicket_kind = 'retired hurt' AND striker_dismissed = 1"
    )
    assert bad == 0


def test_bowling_team_is_never_the_batting_team():
    bad = dataset.value(
        "SELECT COUNT(*) FROM silver_deliveries WHERE batting_team = bowling_team"
    )
    assert bad == 0, "bowling_team is derived from the fixture, never guessed"


def test_key_columns_are_never_null():
    bad = dataset.value(
        "SELECT COUNT(*) FROM silver_deliveries WHERE match_id IS NULL "
        "OR season IS NULL OR batter IS NULL OR bowler IS NULL "
        "OR batting_team IS NULL OR bowling_team IS NULL"
    )
    assert bad == 0


def test_innings_runs_reconcile_with_deliveries():
    """gold_innings is an aggregation of silver_deliveries, so it must balance."""
    from_deliveries = dataset.value(
        "SELECT SUM(runs_total) FROM silver_deliveries WHERE NOT is_super_over"
    )
    from_innings = dataset.value("SELECT SUM(runs_innings) FROM gold_innings")
    assert from_deliveries == from_innings


def test_baselines_exist_for_every_season_with_matches():
    missing = dataset.value(
        "SELECT COUNT(*) FROM silver_matches m "
        "LEFT JOIN gold_role_baselines b USING (season) WHERE b.season IS NULL"
    )
    assert missing == 0
