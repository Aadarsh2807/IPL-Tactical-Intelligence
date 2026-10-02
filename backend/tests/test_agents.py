"""The harness proves the claim: no number reaches the UI untraced."""
from __future__ import annotations

import json

import pytest

import agents
import analytics


def _sample_team():
    season = analytics.seasons()[0]
    for team in analytics.teams(season):
        try:
            analytics.squad(season, team)
            return season, team
        except analytics.NotFound:
            continue
    raise AssertionError("no squad available")


def test_swot_report_is_verified():
    season, team = _sample_team()
    out = agents.report(season, team, "swot")
    assert out["verifier"]["ok"], out["verifier"]
    assert out["verifier"]["flagged"] == []
    assert out["verifier"]["checked_numbers"] > 10
    assert len(out["narrative"]) >= 5
    assert {s["source"] for s in out["narrative"]} <= set(agents.TOOLS)


def test_insights_are_grouped_and_every_group_is_published():
    """The report is a page, so the sections it is cut into must be declared."""
    season, team = _sample_team()
    out = agents.report(season, team, "swot")
    published = [group["key"] for group in out["groups"]]
    assert published == [group["key"] for group in agents.INSIGHT_GROUPS]
    assert {insight["group"] for insight in out["insights"]} <= set(published)
    # Every group except the optional "people" one actually has something to say.
    assert len(out["insights"]) >= 6
    for insight in out["insights"]:
        assert insight["title"] and insight["kicker"] and insight["body"]
        assert insight["source"] in agents.TOOLS
        assert insight["tone"] in {"good", "flat", "down"}


def test_insight_bodies_are_through_the_verifier():
    season, team = _sample_team()
    out = agents.report(season, team, "xi")
    assert out["verifier"]["ok"], out["verifier"]
    assert all("[unverified]" not in i["body"] for i in out["insights"])


def test_the_audit_covers_drawn_figures_not_only_prose():
    """A bar chart is still a claim, so its numbers go through the same check."""
    season, team = _sample_team()
    out = agents.report(season, team, "swot")
    painted = agents._display_values(out["insights"])
    assert painted, "display values must not be silently empty"

    # Poison one drawn figure the way a bad chart would: it must be caught, and
    # it must be the only thing caught once the real corpus is in play.
    poisoned = json.loads(json.dumps(out["insights"]))
    verdict = next(i for i in poisoned if i["group"] == "verdict")
    verdict["chart"][0]["points"] = 999
    corpus = agents._corpus({
        tool: agents.TOOLS[tool]["callable"](season, team)
        for _agent, tool in agents.PLAN["swot"]
    })
    assert agents.verify(agents._display_values(poisoned), corpus)["flagged"] == ["999"]


def test_budget_and_trace_are_untouched_by_the_insight_layer():
    season, team = _sample_team()
    out = agents.report(season, team, "swot")
    assert len(out["trace"]) == out["budget"]["used"] <= agents.MAX_TOOL_CALLS


def test_xi_report_is_verified():
    season, team = _sample_team()
    out = agents.report(season, team, "xi")
    assert out["verifier"]["ok"], out["verifier"]
    assert out["budget"]["used"] <= out["budget"]["max_tool_calls"]
    assert any(s["source"] == "best_xi" for s in out["narrative"])


def test_every_tool_call_is_traced():
    season, team = _sample_team()
    out = agents.report(season, team, "swot")
    assert len(out["trace"]) == out["budget"]["used"]
    for step in out["trace"]:
        assert step["agent"] in agents.AGENT_TOOLS
        assert step["tool"] in agents.TOOLS
        assert step["elapsed_ms"] >= 0


def test_reports_hold_across_many_teams():
    """No team should ever trip the verifier -- otherwise the corpus is wrong."""
    season = analytics.seasons()[0]
    checked = 0
    for team in analytics.teams(season)[:6]:
        try:
            out = agents.report(season, team, "swot")
        except agents.AgentError:
            continue
        assert out["verifier"]["ok"], (team, out["verifier"])
        checked += 1
    assert checked >= 3


def test_verifier_rejects_a_number_not_in_the_tool_output():
    corpus = json.dumps({"stability": 84, "matches": 14})
    outcome = agents.verify("The squad scored 999 runs across 14 matches.", corpus)
    assert not outcome["ok"]
    assert outcome["flagged"] == ["999"]
    assert "[unverified]" in outcome["text"]
    assert "999" not in outcome["text"]          # the lie is redacted
    assert "14" in outcome["text"]               # the traced fact survives


def test_verifier_accepts_numbers_that_do_trace_to_the_corpus():
    corpus = json.dumps({"stability": 84.2, "matches": 14})
    outcome = agents.verify("Stability 84.20 over 14 matches.", corpus)
    assert outcome["ok"], outcome
    assert outcome["text"] == "Stability 84.20 over 14 matches."


def test_verifier_can_report_without_redacting():
    outcome = agents.verify("Scored 999", json.dumps({"runs": 10}), redact=False)
    assert not outcome["ok"] and outcome["text"] == "Scored 999"


def test_tool_budget_is_enforced():
    season, team = _sample_team()
    trace: list[dict] = []
    with pytest.raises(agents.AgentError, match="budget"):
        for _ in range(agents.MAX_TOOL_CALLS + 1):
            agents._run_tool("Analyst", "team_metrics",
                             {"season": season, "team": team}, trace)
    assert len(trace) == agents.MAX_TOOL_CALLS


def test_an_agent_cannot_call_another_agents_tool():
    with pytest.raises(agents.AgentError, match="not permitted"):
        agents._run_tool("Analyst", "best_xi", {"season": "2025", "team": "Nobody"}, [])


def test_unknown_report_kind_is_refused():
    with pytest.raises(agents.AgentError, match="Unknown report kind"):
        agents.report("2025", "Nobody", kind="betting-tips")


def test_agent_endpoint_serves_the_harness(client):
    season = client.get("/api/seasons").json()[0]
    team = client.get("/api/teams", params={"season": season}).json()[0]
    response = client.post("/api/agent/report",
                           json={"season": season, "team": team, "kind": "swot"})
    assert response.status_code == 200
    body = response.json()
    assert body["verifier"]["ok"] is True
    assert body["narrative"][0]["source"]
    assert body["evidence"][0]["description"]

    bad = client.post("/api/agent/report",
                      json={"season": season, "team": team, "kind": "lottery"})
    assert bad.status_code == 422  # pattern on `kind` rejects it before the harness
