"""IPL Tactical Intelligence API.

Thin by design: parse the request, call analytics, serialise the response.
No route computes anything -- every number comes from analytics (which reads
SQL). The /api/sql endpoint exposes the exact SQL behind each figure so a
reviewer can audit the numbers instead of trusting them.
"""
from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import analytics
import dataset
import agents

app = FastAPI(
    title="IPL Tactical Intelligence",
    version="2.0.0",
    description=(
        "Season squad analysis, role-adaptive player stability, XI building, "
        "head-to-head matchups and a bounded next-match outlook. Every figure "
        "is computed from data/raw/*.csv by the SQL files in backend/etl/sql."
    ),
)

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in FRONTEND_ORIGIN.split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Error envelope: one shape everywhere, already understood by the UI client.
# ---------------------------------------------------------------------------
@app.exception_handler(analytics.NotFound)
async def _not_found(request: Request, exc: analytics.NotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(dataset.DataError)
async def _data_error(request: Request, exc: dataset.DataError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(agents.AgentError)
async def _agent_error(request: Request, exc: agents.AgentError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# Response models (they double as the documented API contract in /docs)
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    source: str
    provenance: dict[str, Any]


class ComponentModel(BaseModel):
    key: str
    label: str
    weight: float
    score: float | None
    detail: str


class PlayerModel(BaseModel):
    player: str
    role: str
    stability_score: int
    confidence: str
    band: int
    sample_balls: int
    matches_played: int
    components: list[ComponentModel]
    trend: list[float]
    runs: int
    batting_balls: int
    strike_rate: float | None
    dismissals: int
    wickets: int
    bowling_balls: int
    economy: float | None


class SwotModel(BaseModel):
    strength: str
    weakness: str
    opportunity: str
    threat: str


class SquadResponse(BaseModel):
    team: str
    season: str
    stability_score: int
    score_method: str
    score_breakdown: dict[str, float]
    score_contributions: list[dict[str, Any]]
    role_counts: dict[str, int]
    swot: SwotModel
    notes: list[str]
    players: list[PlayerModel]


class OutlookResponse(BaseModel):
    team: str
    season: str
    matches: int
    wins: int
    decided_matches: int
    win_rate: float
    average_score: float
    average_conceded: float
    league_average: float
    attack_index: float
    defence_index: float
    performance_index: float
    next_match_win_probability: int
    method: str
    limitation: str


class MatchupResponse(BaseModel):
    season: str
    batter: str
    bowler: str
    matches: int
    balls: int
    runs: int
    dismissals: int
    strike_rate: float
    bowler_economy: float | None
    evidence: str
    evidence_note: str
    message: str


class XiSelection(BaseModel):
    player: str
    role: str
    stability_score: int


class XiBreakdown(BaseModel):
    score: int
    quality: int
    role_balance: int
    depth: int
    role_counts: dict[str, int]
    batting_depth: int
    bowling_depth: int
    selected: int
    method: str


class XiRequest(BaseModel):
    season: str = Field(..., examples=["2025"])
    team: str = Field(..., description="Team name exactly as returned by /api/teams")
    players: list[str] = Field(default_factory=list,
                               description="Exactly 11 player names from this squad")


class XiResponse(BaseModel):
    team: str
    season: str
    players: list[str]
    valid: bool
    violations: list[str]
    breakdown: XiBreakdown | None
    selection: list[XiSelection]
    role_splits_considered: int | None = None


class SqlResponse(BaseModel):
    query: str
    description: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    elapsed_ms: float


class AgentRequest(BaseModel):
    season: str
    team: str
    kind: str = Field("swot", pattern="^(swot|xi)$",
                      description="swot = squad narrative, xi = selection narrative")


class NarrativeSentence(BaseModel):
    text: str
    source: str


class AgentResponse(BaseModel):
    kind: str
    season: str
    team: str
    narrative: list[NarrativeSentence]
    insights: list[dict[str, Any]]
    groups: list[dict[str, str]]
    evidence: list[dict[str, str]]
    trace: list[dict[str, Any]]
    verifier: dict[str, Any]
    budget: dict[str, int]


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    source = dataset.validate_source()
    return HealthResponse(
        status="ok" if source["ok"] else "degraded",
        source=source["deliveries_path"].split("/")[-1].split("\\")[-1],
        provenance=dataset.warehouse().provenance,
    )


@app.get("/api/seasons", response_model=list[str])
def list_seasons() -> list[str]:
    return analytics.seasons()


@app.get("/api/teams", response_model=list[str])
def list_teams(season: str = Query(...)) -> list[str]:
    return analytics.teams(season)


@app.get("/api/batters", response_model=list[str])
def list_batters(season: str = Query(...), team: str | None = Query(None)) -> list[str]:
    return analytics.batters(season, team)


@app.get("/api/squad/{team}", response_model=SquadResponse)
def squad(team: str, season: str = Query(...)) -> SquadResponse:
    return analytics.squad(season, team)


@app.get("/api/matchup/bowlers", response_model=list[str])
def matchup_bowlers(batter: str = Query(..., min_length=1),
                    season: str = Query(...)) -> list[str]:
    return analytics.bowlers_for_batter(season, batter)


@app.get("/api/matchup", response_model=MatchupResponse)
def matchup(batter: str = Query(..., min_length=1),
            bowler: str = Query(..., min_length=1),
            season: str = Query(...)) -> MatchupResponse:
    return analytics.matchup(season, batter, bowler)


@app.get("/api/season-outlook/{team}", response_model=OutlookResponse)
def season_outlook(team: str, season: str = Query(...)) -> OutlookResponse:
    return analytics.outlook(season, team)


# ---------------------------------------------------------------------------
# XI builder
# ---------------------------------------------------------------------------
@app.post("/api/xi", response_model=XiResponse)
def score_selection(payload: XiRequest) -> XiResponse:
    return analytics.score_xi(payload.season, payload.team, payload.players)


@app.post("/api/xi/auto", response_model=XiResponse)
def best_xi(payload: XiRequest) -> XiResponse:
    return analytics.auto_xi(payload.season, payload.team)


# ---------------------------------------------------------------------------
# Transparency: the SQL behind a figure, and the published formulas
# ---------------------------------------------------------------------------
SQL_QUERIES: dict[str, tuple[str, str, list[str]]] = {
    "team-season": (
        "Team attack, defence and win rate for a season",
        "SELECT * FROM gold_team_season WHERE season = ? AND team = ?",
        ["season", "team"],
    ),
    "player-season": (
        "Per-player season aggregates that feed the stability score",
        "SELECT * FROM gold_player_season WHERE season = ? AND team = ? "
        "ORDER BY runs DESC",
        ["season", "team"],
    ),
    "role-baselines": (
        "League baselines the player's output is measured against",
        "SELECT * FROM gold_role_baselines WHERE season = ?",
        ["season"],
    ),
    "matchups": (
        "Head-to-head pairs for a batter in a season",
        "SELECT * FROM gold_matchups WHERE season = ? AND batter = ? "
        "ORDER BY balls DESC",
        ["season", "batter"],
    ),
    "league": (
        "Mean innings score per season, the denominator of every index",
        "SELECT * FROM gold_league ORDER BY season DESC",
        [],
    ),
}


@app.get("/api/sql/{query}", response_model=SqlResponse)
def run_named_query(query: str, season: str | None = Query(None),
                    team: str | None = Query(None),
                    batter: str | None = Query(None)) -> SqlResponse:
    """Read-only named queries. Arbitrary SQL is deliberately not accepted."""
    if query not in SQL_QUERIES:
        return JSONResponse(  # type: ignore[return-value]
            status_code=404,
            content={"detail": f"Unknown query. Available: {', '.join(SQL_QUERIES)}"},
        )
    description, sql, params_spec = SQL_QUERIES[query]
    values = {"season": season, "team": team, "batter": batter}
    if any(name in params_spec for name in ("season", "team", "batter")):
        missing = [name for name in params_spec if not values.get(name)]
        if missing:
            return JSONResponse(  # type: ignore[return-value]
                status_code=400,
                content={"detail": "Missing query parameter(s): " + ", ".join(missing)},
            )
    parameters = [values[name] for name in params_spec]
    started = time.perf_counter()
    rows = dataset.query(sql, parameters)
    elapsed = (time.perf_counter() - started) * 1000
    columns = list(rows[0].keys()) if rows else []
    return SqlResponse(
        query=query, description=description, sql=" ".join(sql.split()),
        columns=columns, rows=rows, row_count=len(rows),
        elapsed_ms=round(elapsed, 2),
    )


@app.post("/api/agent/report", response_model=AgentResponse)
def agent_report(payload: AgentRequest) -> AgentResponse:
    """Subagent narrative: tools gather, narrator writes, verifier audits.

    Runs offline with no model. See docs/AGENTS.md for the harness design.
    """
    return agents.report(payload.season, payload.team, payload.kind)


@app.get("/api/method")
def method() -> dict[str, Any]:
    """Every published threshold and weight, so the scoring is inspectable."""
    return {
        "player_stability": {
            "weights_by_role": analytics.ROLE_WEIGHTS,
            "interpretation": "0-100 where 50 equals the season baseline for "
                              "that component; it is an index, not a percentage.",
            "confidence_band": analytics.CONFIDENCE_BAND,
            "confidence_thresholds_balls": dict(analytics.CONFIDENCE_BALLS),
        },
        "role_rules": {
            "min_batting_balls": analytics.MIN_BATTING_BALLS,
            "min_bowling_balls_all_rounder": analytics.MIN_BOWLING_BALLS_AR,
            "min_bowling_balls": analytics.MIN_BOWLING_BALLS,
        },
        "team_stability": {
            "weights": analytics.TEAM_STABILITY_WEIGHTS,
            "quality_benchmark": analytics.QUALITY_BENCHMARK,
        },
        "outlook": {
            "weights": analytics.OUTLOOK_WEIGHTS,
            "anchor": analytics.OUTLOOK_ANCHOR,
            "bounds": analytics.OUTLOOK_BAND,
        },
        "xi": {"rules": analytics.XI_RULES, "weights": analytics.XI_WEIGHTS},
        "sql_files": sorted(p.name for p in dataset.SQL_DIR.glob("*.sql")),
        "named_queries": {name: spec[0] for name, spec in SQL_QUERIES.items()},
    }
