"""Every endpoint, including the failure paths an interviewer will probe."""
from __future__ import annotations


def test_health_reports_provenance(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    provenance = body["provenance"]
    for key in ("engine", "deliveries_rows", "matches_rows", "legal_balls",
                "bowler_runs", "super_overs", "warehouse"):
        assert key in provenance
    assert provenance["deliveries_rows"] > 200_000


def test_seasons_are_sorted_newest_first(client):
    seasons = client.get("/api/seasons").json()
    assert seasons == sorted(seasons, reverse=True)
    assert len(seasons) >= 10


def test_teams_and_batters_follow_the_season(client):
    season = client.get("/api/seasons").json()[0]
    teams = client.get("/api/teams", params={"season": season}).json()
    assert teams and teams == sorted(teams)

    batters = client.get("/api/batters", params={"season": season}).json()
    assert batters and batters == sorted(batters)

    filtered = client.get("/api/batters",
                          params={"season": season, "team": teams[0]}).json()
    assert set(filtered) <= set(batters)


def test_squad_payload_is_complete(client):
    season = client.get("/api/seasons").json()[0]
    team = client.get("/api/teams", params={"season": season}).json()[0]
    body = client.get(f"/api/squad/{team}", params={"season": season}).json()

    assert body["team"] == team and body["season"] == season
    assert 0 <= body["stability_score"] <= 100
    assert set(body["swot"]) == {"strength", "weakness", "opportunity", "threat"}
    assert sum(body["role_counts"].values()) == len(body["players"])
    assert body["notes"]

    player = body["players"][0]
    assert 0 <= player["stability_score"] <= 100
    assert player["confidence"] in {"High", "Medium", "Low"}
    assert abs(sum(c["weight"] for c in player["components"]) - 1.0) < 0.01
    for component in player["components"]:
        assert component["score"] is None or 0 <= component["score"] <= 100
        assert component["detail"]


def test_matchup_flow(client):
    season = client.get("/api/seasons").json()[0]
    batters = client.get("/api/batters", params={"season": season}).json()
    bowlers = None
    for batter in batters:
        response = client.get("/api/matchup/bowlers",
                              params={"season": season, "batter": batter})
        if response.status_code == 200 and response.json():
            bowlers, chosen = response.json(), batter
            break
    assert bowlers, "expected at least one batter with recorded opponents"

    body = client.get("/api/matchup", params={
        "season": season, "batter": chosen, "bowler": bowlers[0]}).json()
    assert body["balls"] > 0
    assert body["evidence"] in {"High", "Medium", "Limited"}
    assert body["evidence_note"].endswith("matches")


def test_outlook_is_bounded_and_explains_itself(client):
    season = client.get("/api/seasons").json()[0]
    team = client.get("/api/teams", params={"season": season}).json()[0]
    body = client.get(f"/api/season-outlook/{team}", params={"season": season}).json()
    assert 20 <= body["next_match_win_probability"] <= 80
    assert "bounded" in body["method"]
    assert body["limitation"]
    assert body["decided_matches"] <= body["matches"]


def test_unknown_season_and_team_return_404(client):
    assert client.get("/api/teams", params={"season": "1899"}).status_code == 404
    response = client.get("/api/squad/Nobody", params={"season": "2025"})
    assert response.status_code == 404
    assert "detail" in response.json()


def test_named_sql_query_is_auditable(client):
    season = client.get("/api/seasons").json()[0]
    team = client.get("/api/teams", params={"season": season}).json()[0]
    body = client.get("/api/sql/team-season",
                      params={"season": season, "team": team}).json()
    assert "gold_team_season" in body["sql"]
    assert body["row_count"] == 1
    assert body["columns"] and body["elapsed_ms"] >= 0


def test_unknown_or_incomplete_sql_query_is_refused(client):
    assert client.get("/api/sql/drop-everything").status_code == 404
    assert client.get("/api/sql/team-season").status_code == 400


def test_method_endpoint_publishes_every_weight(client):
    body = client.get("/api/method").json()
    assert set(body["player_stability"]["weights_by_role"]) == {
        "Batter", "Bowler", "All-rounder"}
    for weights in body["player_stability"]["weights_by_role"].values():
        assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert body["sql_files"]
    assert "team-season" in body["named_queries"]


def test_docs_are_served(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/squad/{team}" in paths and "/api/xi/auto" in paths
