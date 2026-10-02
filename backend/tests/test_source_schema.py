"""The source files must say what we claim they say.

Row counts are recomputed by reading the CSV directly with the standard
library, so this test would catch a silently truncated or swapped dataset.
"""
from __future__ import annotations

import csv
from pathlib import Path

import dataset


def _row_count(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.reader(handle)) - 1  # minus header


def test_source_files_exist_and_declare_expected_columns():
    report = dataset.validate_source()
    assert report["ok"], report["problems"]
    assert dataset.RAW_DELIVERIES_COLUMNS <= set(report["deliveries_columns"])
    assert dataset.RAW_MATCHES_COLUMNS <= set(report["matches_columns"])


def test_warehouse_row_counts_match_the_files_on_disk(provenance):
    deliveries, matches = dataset.csv_paths()
    assert provenance["deliveries_rows"] == _row_count(deliveries)
    assert provenance["matches_rows"] == _row_count(matches)


def test_super_over_deliveries_are_counted_and_flagged(provenance):
    """Innings > 2 exists only in tied matches; we must see exactly those rows."""
    assert provenance["super_over_deliveries"] >= 0
    flagged = dataset.value("SELECT COUNT(*) FROM silver_deliveries WHERE is_super_over")
    assert flagged == provenance["super_over_deliveries"]
    wrong = dataset.value(
        "SELECT COUNT(*) FROM silver_deliveries d "
        "JOIN silver_matches m USING (match_id) "
        "WHERE d.is_super_over AND m.result_type <> 'tie'"
    )
    assert wrong == 0, "super-over deliveries must only occur in tied matches"


def test_every_delivery_joins_to_a_match(provenance):
    """The old code demanded columns that did not exist; now the join is total."""
    orphaned = dataset.value(
        "SELECT COUNT(*) FROM silver_deliveries d "
        "LEFT JOIN silver_matches m USING (match_id) "
        "WHERE m.match_id IS NULL"
    )
    assert orphaned == 0
    assert dataset.value("SELECT COUNT(*) FROM silver_deliveries") == provenance["deliveries_rows"]


def test_provenance_reports_its_assumptions(provenance):
    """Honesty check: the two known approximations must always be disclosed."""
    assert provenance["legal_balls"].startswith("assumed")
    assert provenance["bowler_runs"].startswith("approximate")
    assert "super_overs" in provenance
    assert provenance["engine"].startswith("duckdb")
