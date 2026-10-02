"""Mechanically prove that no player or team identity is hardcoded.

Team and player names are read from the dataset at test time, so the test
cannot be satisfied by removing a name from a list: the list is the data.
Presentation-only code (frontend livery colours) is exempt and named here.
"""
from __future__ import annotations

from pathlib import Path

import dataset

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_SRC = PROJECT_DIR / "frontend" / "src"

# Presentation only: maps a team name to its real brand colour. Never used in
# a calculation, so it is the single allowed place identities are written down.
ALLOWED_FILES = {FRONTEND_SRC / "theme" / "teams.js"}


def _identities() -> set[str]:
    teams = {row["team"] for row in dataset.query(
        "SELECT DISTINCT team FROM (SELECT team1 AS team FROM silver_matches "
        "UNION SELECT team2 FROM silver_matches)")}
    players = {row["player"] for row in dataset.query(
        "SELECT DISTINCT player FROM gold_player_season")}
    return {name for name in teams | players if len(name) >= 4}


def _application_files() -> list[Path]:
    files = [
        path for path in BACKEND_DIR.rglob("*.py")
        if ".venv" not in path.parts and "tests" not in path.parts
    ]
    if FRONTEND_SRC.exists():
        files += [path for path in FRONTEND_SRC.rglob("*")
                  if path.suffix in {".js", ".jsx"}]
    return [path for path in files if path not in ALLOWED_FILES]


def test_no_identity_is_written_in_application_code():
    identities = _identities()
    assert len(identities) > 500, "expected the dataset to supply identities"

    offenders: dict[str, list[str]] = {}
    for path in _application_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in identities:
            if name in text:
                offenders.setdefault(str(path.relative_to(PROJECT_DIR)), []).append(name)

    assert not offenders, f"hardcoded identities found: {offenders}"


def test_every_api_squad_name_comes_from_the_data(client):
    """The API must be able to name a team we never mention in the code."""
    season = client.get("/api/seasons").json()[0]
    teams = client.get("/api/teams", params={"season": season}).json()
    assert teams, "expected teams for the newest season"
    for team in teams:
        assert team in {
            row["team"] for row in dataset.query(
                "SELECT DISTINCT team FROM (SELECT team1 AS team FROM silver_matches "
                "UNION SELECT team2 FROM silver_matches)")
        }
