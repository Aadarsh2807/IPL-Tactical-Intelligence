"""Preflight: prove the environment and dataset are ready before starting anything.

Run it first. It answers the two questions a reviewer will ask immediately:
"does it actually start?" and "where did the numbers come from?".

    python scripts/preflight.py            # check only
    python scripts/preflight.py --rebuild  # force the warehouse to be rebuilt

Exit code 0 means the API is startable.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "backend"))

MIN_PYTHON = (3, 10)

failures: list[str] = []


def report(ok: bool, label: str, detail: str = "") -> None:
    mark = "[ok]" if ok else "[!!]"
    print(f"{mark} {label}{f' — {detail}' if detail else ''}")
    if not ok:
        failures.append(label)


def venv_python() -> Path:
    """Project virtualenv interpreter, if one exists (Windows or POSIX)."""
    venv = PROJECT_DIR / "backend" / ".venv"
    for candidate in (venv / "Scripts" / "python.exe", venv / "bin" / "python"):
        if candidate.is_file():
            return candidate
    return venv  # type: ignore[return-value]


def check_runtime() -> bool:
    version = sys.version_info
    report(version[:2] >= MIN_PYTHON, "python",
           f"{version.major}.{version.minor}.{version.micro}")
    try:
        import duckdb
        report(True, "duckdb", duckdb.__version__)
        return True
    except ImportError:
        interpreter = venv_python()
        hint = (f"duckdb is missing. Run this script with the project virtualenv: "
                f"{interpreter} scripts/preflight.py")
        report(False, "duckdb", hint)
        return False


def check_data() -> None:
    import dataset

    try:
        deliveries, matches = dataset.csv_paths()
    except dataset.DataError as error:
        report(False, "dataset files", str(error))
        return

    report(True, "deliveries file", f"{deliveries.name} "
           f"{deliveries.stat().st_size / 1_048_576:.1f} MB")
    report(True, "matches file", f"{matches.name}")

    source = dataset.validate_source()
    report(source["ok"], "source columns", "; ".join(source["problems"]) or
           f"{len(source['deliveries_columns'])} delivery / "
           f"{len(source['matches_columns'])} match columns")


def check_warehouse(rebuild: bool) -> None:
    import dataset

    started = time.perf_counter()
    try:
        if rebuild:
            provenance = dataset.warehouse().rebuild()
        else:
            provenance = dataset.warehouse().provenance
    except Exception as error:  # noqa: BLE001 - preflight must never traceback
        report(False, "warehouse build", f"{type(error).__name__}: {error}")
        return

    elapsed = time.perf_counter() - started
    report(provenance["deliveries_rows"] > 0, "silver deliveries",
           f"{provenance['deliveries_rows']:,} rows")
    report(provenance["matches_rows"] > 0, "silver matches",
           f"{provenance['matches_rows']:,} rows")
    report(True, "coverage",
           f"{provenance['seasons']} seasons, {provenance['teams']} teams, "
           f"{provenance['super_over_deliveries']} super-over deliveries excluded")
    report(True, "sql layer",
           f"{provenance['sql_files']} files, built in {elapsed:.2f}s "
           f"(rebuilt: {provenance['rebuilt_on_boot']})")
    report(True, "warehouse cache",
           f"{provenance['warehouse']} - {provenance['engine']}")

    orphaned = dataset.value(
        "SELECT COUNT(*) FROM silver_deliveries d "
        "LEFT JOIN silver_matches m USING (match_id) WHERE m.match_id IS NULL")
    report(orphaned == 0, "join coverage", f"{orphaned} orphaned deliveries")


def check_disclosure() -> None:
    import dataset

    provenance = dataset.warehouse().provenance
    print()
    print("Disclosed approximations (surfaced by /api/health and the UI footer):")
    for key in ("legal_balls", "bowler_runs", "super_overs", "dismissal_credit"):
        print(f"     - {key}: {provenance[key]}")  # noqa: E501


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true",
                        help="force the DuckDB warehouse to be rebuilt")
    args = parser.parse_args()

    print("IPL Tactical Intelligence - preflight\n")
    if not check_runtime():
        print(f"\nNOT READY: {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    check_data()
    check_warehouse(args.rebuild)
    check_disclosure()

    print()
    if failures:
        print(f"NOT READY: {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    print("READY. Start the API with:  cd backend && python -m uvicorn main:app --port 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
