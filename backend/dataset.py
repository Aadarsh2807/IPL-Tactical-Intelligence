"""Data layer.

One SQL directory is the single source of truth for every number in the app.
This module wires that SQL to DuckDB, validates the source files before
anything runs, and reports provenance so no result is ever anonymous.

No pandas, no Spark: DuckDB executes the same .sql files a reader can audit.
"""
from __future__ import annotations

import csv
import hashlib
import threading
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import duckdb

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
SQL_DIR = BACKEND_DIR / "etl" / "sql"

DELIVERIES_FILENAME = "ipl_deliveries_clean.csv"
MATCHES_FILENAME = "ipl_matches_clean.csv"

# Columns the raw files must have. Nothing beyond these is required, and
# every column the old code expected but the data does not have is derived
# in 00_silver.sql instead of being demanded from the source.
RAW_DELIVERIES_COLUMNS = {
    "match_id", "innings", "batting_team", "over", "ball", "batter", "bowler",
    "non_striker", "runs_batter", "runs_extras", "runs_total", "wicket",
    "wicket_player_out", "wicket_kind",
}
RAW_MATCHES_COLUMNS = {
    "match_id", "date", "season", "venue", "city", "team1", "team2",
    "toss_winner", "toss_decision", "winner", "result_type", "result_margin",
    "player_of_match",
}

NON_BOWLER_DISMISSALS = ("run out", "retired hurt", "retired out",
                         "obstructing the field")

# The dataset is a Kaggle download and is not committed, so it is pinned by
# content rather than by link: a URL can be edited or silently repointed,
# an MD5 cannot. These are the exact files every published figure was
# computed from. A different dataset is not an error, but the row counts,
# season labels and quirks documented in docs/DATA.md then do not apply,
# so a mismatch is reported rather than ignored.
DATASET_FINGERPRINTS = {
    DELIVERIES_FILENAME: "a81f1880e7b9b1f440f0005db00f6d4d",
    MATCHES_FILENAME: "c083503466c5c73501ff2987b74099e7",
}


def file_md5(path: Path) -> str:
    """MD5 of a file, read in chunks so a 21 MB CSV is never held in memory."""
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_fingerprints() -> list[dict]:
    """Compare each dataset file against its recorded MD5.

    Returns one result per file. ``matches`` is False when the checksum
    differs or the file is absent; ``expected`` is None when the file has
    no recorded fingerprint, which is treated as a match.
    """
    results: list[dict] = []
    for filename, expected in DATASET_FINGERPRINTS.items():
        path = data_dir() / filename
        if not path.is_file():
            results.append({"file": filename, "expected": expected,
                            "actual": None, "matches": False,
                            "detail": "file not found"})
            continue
        actual = file_md5(path)
        results.append({
            "file": filename,
            "expected": expected,
            "actual": actual,
            "matches": actual == expected,
            "detail": "checksum matches" if actual == expected
                      else "different dataset: the documented row counts, "
                           "season labels and quirks do not apply",
        })
    return results


class DataError(RuntimeError):
    """Raised when the dataset is missing, incomplete or unreadable."""


def data_dir() -> Path:
    import os
    return Path(os.environ.get("IPL_DATA_DIR") or PROJECT_DIR / "data" / "raw")


def warehouse_file() -> Path:
    """Materialised database. Lives beside the raw data, never in git."""
    return data_dir().parent / "warehouse.duckdb"


def csv_paths() -> tuple[Path, Path]:
    """Return (deliveries, matches) paths, failing with an actionable message."""
    directory = data_dir()
    deliveries = directory / DELIVERIES_FILENAME
    matches = directory / MATCHES_FILENAME
    missing = [str(p) for p in (deliveries, matches) if not p.is_file()]
    if missing:
        raise DataError(
            "Missing dataset file(s): "
            + ", ".join(missing)
            + f". Put {DELIVERIES_FILENAME} and {MATCHES_FILENAME} in "
            f"{directory} (or set IPL_DATA_DIR). See README 'Dataset setup'."
        )
    return deliveries, matches


def read_header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def validate_source() -> dict:
    """Structural check of the raw files. Used by /api/health, preflight, tests."""
    deliveries, matches = csv_paths()
    problems: list[str] = []

    delivery_header = set(read_header(deliveries))
    match_header = set(read_header(matches))
    missing_deliveries = sorted(RAW_DELIVERIES_COLUMNS - delivery_header)
    missing_matches = sorted(RAW_MATCHES_COLUMNS - match_header)
    if missing_deliveries:
        problems.append(f"{DELIVERIES_FILENAME} is missing: {', '.join(missing_deliveries)}")
    if missing_matches:
        problems.append(f"{MATCHES_FILENAME} is missing: {', '.join(missing_matches)}")

    return {
        "ok": not problems,
        "problems": problems,
        "deliveries_path": str(deliveries),
        "matches_path": str(matches),
        "deliveries_columns": sorted(delivery_header),
        "matches_columns": sorted(match_header),
    }


def _split_statements(script: str) -> list[str]:
    """Split a SQL script on ';', ignoring semicolons inside strings and
    ignoring ';' characters that appear inside ``--`` line comments."""
    statements: list[str] = []
    buffer: list[str] = []
    in_string = False
    index = 0
    length = len(script)
    while index < length:
        char = script[index]
        if in_string:
            if char == "'":
                if index + 1 < length and script[index + 1] == "'":
                    buffer.append("''")
                    index += 2
                    continue
                in_string = False
            buffer.append(char)
        elif char == "'":
            in_string = True
            buffer.append(char)
        elif char == "-" and index + 1 < length and script[index + 1] == "-":
            # line comment: drop it entirely, it never ends a statement
            while index < length and script[index] != "\n":
                index += 1
            continue
        elif char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
        else:
            buffer.append(char)
        index += 1
    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def _quote(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


class Warehouse:
    """Materialises the SQL layer once, then serves parameterised queries.

    The dataset is read-only, so the tables live in data/warehouse.duckdb and
    are rebuilt automatically whenever a source CSV or a .sql file changes.
    Startup is therefore ~0.3s warm instead of re-parsing 22 MB every boot.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connection = None
        self._provenance: dict = {}

    # -- lifecycle ---------------------------------------------------------
    @staticmethod
    def _inputs(deliveries: Path, matches: Path) -> list[Path]:
        return [deliveries, matches, *sorted(SQL_DIR.glob("*.sql"))]

    @staticmethod
    def _fingerprint(inputs: list[Path]) -> str:
        return "|".join(
            f"{path.resolve()}@{path.stat().st_mtime_ns}" for path in inputs
        )

    @staticmethod
    def _execute_scripts(connection, deliveries: Path, matches: Path) -> None:
        for sql_file in sorted(SQL_DIR.glob("*.sql")):
            text = sql_file.read_text(encoding="utf-8")
            text = text.replace("{{MATCHES_CSV}}", _quote(matches))
            text = text.replace("{{DELIVERIES_CSV}}", _quote(deliveries))
            for statement in _split_statements(text):
                connection.execute(statement)

    def _materialise(self, warehouse_path: Path, deliveries: Path,
                     matches: Path, fingerprint: str) -> None:
        """Build into a staging file, then swap it in (never a half-built db)."""
        warehouse_path.parent.mkdir(parents=True, exist_ok=True)
        staging = warehouse_path.with_name("warehouse.staging.duckdb")
        if staging.exists():
            staging.unlink()
        connection = duckdb.connect(database=str(staging))
        try:
            self._execute_scripts(connection, deliveries, matches)
            connection.execute(
                "CREATE OR REPLACE TABLE warehouse_meta "
                "(fingerprint VARCHAR, built_at TIMESTAMP)",
            )
            connection.execute(
                "INSERT INTO warehouse_meta VALUES (?, current_timestamp)",
                [fingerprint],
            )
        finally:
            connection.close()
        if warehouse_path.exists():
            warehouse_path.unlink()
        staging.rename(warehouse_path)

    def _build(self):
        deliveries, matches = csv_paths()
        source = validate_source()
        if not source["ok"]:
            raise DataError("; ".join(source["problems"]))

        inputs = self._inputs(deliveries, matches)
        fingerprint = self._fingerprint(inputs)
        warehouse_path = warehouse_file()

        needs_build = True
        built_at = None
        if warehouse_path.is_file():
            try:
                probe = duckdb.connect(database=str(warehouse_path), read_only=True)
                try:
                    row = probe.execute(
                        "SELECT fingerprint, built_at FROM warehouse_meta").fetchone()
                finally:
                    probe.close()
                if row and row[0] == fingerprint:
                    needs_build = False
                    built_at = row[1]
            except duckdb.Error:
                needs_build = True  # corrupt or foreign file: rebuild

        if needs_build:
            self._materialise(warehouse_path, deliveries, matches, fingerprint)

        connection = duckdb.connect(database=str(warehouse_path))
        if built_at is None:
            built_at = connection.execute(
                "SELECT built_at FROM warehouse_meta").fetchone()[0]

        counts = {
            "deliveries_rows": self._scalar_on(connection, "SELECT COUNT(*) FROM raw_deliveries"),
            "matches_rows": self._scalar_on(connection, "SELECT COUNT(*) FROM raw_matches"),
            "super_over_deliveries": self._scalar_on(
                connection, "SELECT COUNT(*) FROM silver_deliveries WHERE is_super_over"),
            "seasons": self._scalar_on(connection, "SELECT COUNT(DISTINCT season) FROM silver_matches"),
            "teams": self._scalar_on(
                connection,
                "SELECT COUNT(DISTINCT team) FROM (SELECT team1 AS team FROM silver_matches "
                "UNION SELECT team2 FROM silver_matches)"),
        }
        provenance = {
            "engine": f"duckdb {duckdb.__version__}",
            "source": "raw-csv",
            "warehouse": warehouse_path.name,
            "warehouse_built_at": _jsonable(built_at),
            "rebuilt_on_boot": needs_build,
            "sql_files": len(sorted(SQL_DIR.glob('*.sql'))),
            "legal_balls": "assumed (source CSV has no extras_type column)",
            "bowler_runs": "approximate (runs_total; byes and leg-byes not separable)",
            "super_overs": "innings > 2 excluded from every aggregate",
            "dismissal_credit": "bowler credited except for: "
                                + ", ".join(NON_BOWLER_DISMISSALS),
            **counts,
        }
        return connection, provenance

    @staticmethod
    def _scalar_on(connection, sql: str, parameters=()):
        return connection.execute(sql, parameters).fetchone()[0]

    @property
    def connection(self):
        with self._lock:
            if self._connection is None:
                self._connection, self._provenance = self._build()
            return self._connection

    @property
    def provenance(self) -> dict:
        self.connection  # force load
        with self._lock:
            return dict(self._provenance)

    def rebuild(self) -> dict:
        """Force a fresh materialisation from the source files."""
        self.reset()
        path = warehouse_file()
        if path.exists():
            path.unlink()
        return self.provenance

    def reset(self) -> None:
        """Drop the cached connection (used by tests)."""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
            self._connection = None
            self._provenance = {}

    # -- querying ----------------------------------------------------------
    def query(self, sql: str, parameters=()) -> list[dict]:
        with self._lock:
            if self._connection is None:
                self._connection, self._provenance = self._build()
            cursor = self._connection.execute(sql, parameters)
            columns = [name[0] for name in cursor.description]
            return [
                {name: _jsonable(value) for name, value in zip(columns, row)}
                for row in cursor.fetchall()
            ]

    def one(self, sql: str, parameters=()) -> dict | None:
        rows = self.query(sql, parameters)
        return rows[0] if rows else None

    def value(self, sql: str, parameters=()):
        row = self.one(sql, parameters)
        return next(iter(row.values())) if row else None


@lru_cache(maxsize=1)
def warehouse() -> Warehouse:
    return Warehouse()


def query(sql: str, parameters=()) -> list[dict]:
    return warehouse().query(sql, parameters)


def one(sql: str, parameters=()) -> dict | None:
    return warehouse().one(sql, parameters)


def value(sql: str, parameters=()):
    return warehouse().value(sql, parameters)
