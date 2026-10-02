"""Recompute a headline number straight from the CSV with the standard
library and demand that SQL agrees.

This is the test that answers "did you hardcode or hand-wave the maths":
two independent implementations, one number, no framework in between.
"""
from __future__ import annotations

import csv
from collections import defaultdict

import dataset


def _season_rows(season: str):
    deliveries, matches = dataset.csv_paths()
    with matches.open(encoding="utf-8-sig", newline="") as handle:
        season_by_match = {
            row["match_id"]: row["season"] for row in csv.DictReader(handle)
        }
    with deliveries.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["innings"]) > 2:
                continue
            if season_by_match.get(row["match_id"]) == season:
                yield row


def test_season_run_total_matches_a_plain_python_recount():
    season = "2025"
    recount = defaultdict(int)
    matches_seen = set()
    for row in _season_rows(season):
        recount["runs"] += int(row["runs_batter"])
        recount["balls"] += 1
        matches_seen.add(row["match_id"])

    assert dataset.value(
        "SELECT SUM(runs_batter) FROM silver_deliveries "
        "WHERE season = ? AND NOT is_super_over", [season]) == recount["runs"]
    assert dataset.value(
        "SELECT COUNT(*) FROM silver_deliveries "
        "WHERE season = ? AND NOT is_super_over", [season]) == recount["balls"]
    assert dataset.value(
        "SELECT COUNT(DISTINCT match_id) FROM silver_deliveries "
        "WHERE season = ? AND NOT is_super_over", [season]) == len(matches_seen)


def test_a_players_dismissal_count_is_credited_consistently():
    """Batting dismissals counted per player in Python must match gold."""
    season = "2025"
    per_player: dict[str, int] = defaultdict(int)
    for row in _season_rows(season):
        if (row["wicket"] == "1"
                and row["wicket_player_out"] == row["batter"]
                and row["wicket_kind"] != "retired hurt"):
            per_player[row["batter"]] += 1

    top_name, top_count = max(per_player.items(), key=lambda kv: kv[1])
    sql_count = dataset.value(
        "SELECT SUM(dismissals) FROM gold_player_season "
        "WHERE season = ? AND player = ?", [season, top_name])
    assert sql_count == top_count, f"{top_name}: python {top_count} vs sql {sql_count}"
