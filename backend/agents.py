"""The agentic layer: two subagents that narrate, one that verifies.

Nothing here is a model. The value of this module is the *harness*, which is
the part most projects skip:

  tools     -> every fact comes from an audited SQL-backed tool
  subagents -> Analyst gathers, Coach proposes, Verifier audits; each with a
               restricted tool list and a single output contract
  budget    -> at most MAX_TOOL_CALLS, every call recorded in the trace
  verifier  -> any number in the prose that cannot be traced to a tool result
               is redacted before it reaches the UI

A language model can be dropped in behind `narrate()` later without touching
the harness, because the contract is "produce sentences that cite tool facts"
and the verifier does not care who wrote them.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

import analytics

MAX_TOOL_CALLS = 6
NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")

# Published scale constants (also exposed at /api/method). They are part of the
# verified corpus because a sentence like "stability 84 out of 100" describes
# the index, not a measured value.
PUBLISHED_SCALE = (
    "index scale 0 to 100; outlook bounds 20 to 80; XI score 0 to 100; "
    "weights 0.35 0.35 0.20 0.10 0.45 0.30 0.25 0.15 0.60 0.40 0.10 0.55 0.90"
)


class AgentError(ValueError):
    """Raised when a tool call is impossible (bad season, bad team, budget)."""


# ---------------------------------------------------------------------------
# Tools: the only way an agent may touch data
# ---------------------------------------------------------------------------
def _squad_overview(season: str, team: str) -> dict:
    report = analytics.squad(season, team)
    return {
        "team": report["team"],
        "season": report["season"],
        "stability_score": report["stability_score"],
        "score_method": report["score_method"],
        "score_breakdown": report["score_breakdown"],
        "score_contributions": report["score_contributions"],
        "role_counts": report["role_counts"],
        "swot": report["swot"],
        "notes": report["notes"],
        "players_counted": len(report["players"]),
        "leading_players": [
            {"player": p["player"], "role": p["role"],
             "stability_score": p["stability_score"], "confidence": p["confidence"],
             "band": p["band"]}
            for p in report["players"][:5]
        ],
    }


def _team_metrics(season: str, team: str) -> dict:
    row = analytics.dataset.one(
        "SELECT * FROM gold_team_season WHERE season = ? AND team = ?", [season, team])
    if not row:
        raise analytics.NotFound(f"{team} has no recorded deliveries in season {season}")
    return {key: value for key, value in row.items()}


def _outlook(season: str, team: str) -> dict:
    return analytics.outlook(season, team)


def _best_xi(season: str, team: str) -> dict:
    xi = analytics.auto_xi(season, team)
    # The published XI rules travel with the result so any sentence about them
    # is checked against the same constants the solver used.
    return {**xi, "rules": analytics.XI_RULES}


TOOLS: dict[str, dict[str, Any]] = {
    "squad_overview": {
        "agent": "Analyst",
        "description": "Season squad, stability scores, role counts and SWOT facts",
        "callable": _squad_overview,
        "signature": "(season, team)",
    },
    "team_metrics": {
        "agent": "Analyst",
        "description": "Attack, defence, win rate and league baseline for a team-season",
        "callable": _team_metrics,
        "signature": "(season, team)",
    },
    "outlook": {
        "agent": "Analyst",
        "description": "Bounded next-match outlook with its published method",
        "callable": _outlook,
        "signature": "(season, team)",
    },
    "best_xi": {
        "agent": "Coach",
        "description": "Deterministic best XI under the role constraints",
        "callable": _best_xi,
        "signature": "(season, team)",
    },
}

# Which agent may call what. This is the access control, not a suggestion.
AGENT_TOOLS = {
    "Analyst": ("squad_overview", "team_metrics", "outlook"),
    "Coach": ("best_xi", "squad_overview"),
    "Verifier": (),
}

PLAN: dict[str, list[tuple[str, str]]] = {
    "swot": [("Analyst", "squad_overview"), ("Analyst", "team_metrics"),
             ("Analyst", "outlook")],
    "xi": [("Coach", "best_xi"), ("Coach", "squad_overview"),
           ("Analyst", "team_metrics")],
}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
def _run_tool(agent: str, tool: str, args: dict, trace: list[dict]) -> dict:
    if len(trace) >= MAX_TOOL_CALLS:
        raise AgentError(f"tool budget exhausted at {MAX_TOOL_CALLS} calls")
    if tool not in AGENT_TOOLS[agent]:
        raise AgentError(f"{agent} is not permitted to call {tool}")
    spec = TOOLS[tool]
    started = time.perf_counter()
    try:
        result = spec["callable"](**args)
    except analytics.NotFound as exc:
        raise AgentError(str(exc)) from exc
    elapsed = (time.perf_counter() - started) * 1000
    trace.append({
        "agent": agent,
        "tool": tool,
        "args": args,
        "elapsed_ms": round(elapsed, 2),
        "result_bytes": len(json.dumps(result, default=str)),
    })
    return result


def _corpus(results: dict[str, dict]) -> str:
    return json.dumps(results, default=str, sort_keys=True) + " " + PUBLISHED_SCALE


def _numbers(text: str) -> set[float]:
    return {round(float(match), 2) for match in NUMBER_PATTERN.findall(text)}


def verify(narrative: str, corpus: str, *, redact: bool = True) -> dict:
    """Reject any figure that does not appear in the tool output.

    Pure function on purpose: `test_agents.py` feeds it a poisoned draft and
    asserts the lie is caught.
    """
    allowed = _numbers(corpus)
    flagged: list[str] = []
    def _check(match: "re.Match[str]") -> str:
        token = match.group(0)
        if round(float(token), 2) in allowed:
            return token
        flagged.append(token)
        return "[unverified]" if redact else token

    checked = NUMBER_PATTERN.sub(_check, narrative)
    return {
        "ok": not flagged,
        "checked_numbers": len(NUMBER_PATTERN.findall(narrative)),
        "flagged": flagged,
        "text": checked,
    }


# ---------------------------------------------------------------------------
# Narrator: deterministic, rule-driven prose built only from tool facts
# ---------------------------------------------------------------------------
def _sentence(source: str, text: str) -> dict:
    return {"text": text, "source": source}


def _narrate_swot(results: dict[str, dict]) -> list[dict]:
    squad = results["squad_overview"]
    metrics = results["team_metrics"]
    outlook = results["outlook"]
    team, season = squad["team"], squad["season"]
    swot = squad["swot"]
    sentences = [
        _sentence("squad_overview", f"{team} in {season}: squad stability "
                                    f"{squad['stability_score']} out of 100, built from "
                                    f"{swot['strength']}"),
        _sentence("team_metrics", swot["weakness"]),
        _sentence("squad_overview", swot["opportunity"]),
        _sentence("squad_overview", swot["threat"]),
        _sentence("team_metrics",
                  f"How the number was built: {squad['score_method']}"),
        _sentence("outlook",
                  f"Looking forward: the bounded model estimates "
                  f"{outlook['next_match_win_probability']}% for the next match, from "
                  f"{outlook['decided_matches']} decided matches and "
                  f"{outlook['wins']} wins."),
        _sentence("outlook", outlook["limitation"]),
    ]
    leaders = ", ".join(
        f"{p['player']} ({p['role']}, {p['stability_score']}, {p['confidence'].lower()} confidence)"
        for p in squad["leading_players"][:3]
    )
    sentences.append(_sentence("squad_overview",
                               f"Most consistent contributors this season: {leaders}."))
    return sentences


def _narrate_xi(results: dict[str, dict]) -> list[dict]:
    xi = results["best_xi"]
    squad = results["squad_overview"]
    breakdown = xi["breakdown"]
    counts = breakdown["role_counts"]
    sentences = [
        _sentence("best_xi",
                  f"Recommended XI for {xi['team']} in {xi['season']}: "
                  f"{breakdown['selected']} players, composed of {counts['Batter']} batters, "
                  f"{counts['All-rounder']} all-rounders and {counts['Bowler']} bowlers."),
        _sentence("best_xi",
                  f"XI score {breakdown['score']} out of 100, from a mean player stability "
                  f"of {breakdown['quality']}, role balance {breakdown['role_balance']} and "
                  f"depth {breakdown['depth']}."),
        _sentence("best_xi", breakdown["method"]),
        _sentence("squad_overview",
                  f"The squad holds {squad['players_counted']} players with a recorded "
                  f"contribution and a squad stability score of {squad['stability_score']}."),
    ]
    picked = ", ".join(f"{p['player']} ({p['stability_score']})"
                       for p in xi["selection"][:6])
    sentences.append(_sentence("best_xi", f"Selection led by: {picked}."))
    sentences.append(_sentence("team_metrics",
                               f"Role constraints applied: {xi['role_splits_considered']} "
                               f"legal role splits were evaluated and the highest scoring "
                               f"one was kept."))
    return sentences


NARRATORS: dict[str, Callable[[dict], list[dict]]] = {
    "swot": _narrate_swot,
    "xi": _narrate_xi,
}


# ---------------------------------------------------------------------------
# Insight layer
# ---------------------------------------------------------------------------
# The narrative is the audit trail. The insights are the editorial layer on top
# of it: a lead figure, an inference, and the evidence that inference rests on.
# They are grouped so a reader can skim, and every one of them goes through the
# same verifier as the narrative -- an insight may only say what a tool result
# already proved.

INSIGHT_GROUPS = (
    {"key": "verdict", "title": "The verdict", "blurb": "One figure, one judgement"},
    {"key": "drivers", "title": "What drove the number",
     "blurb": "Which parts of the score did the work"},
    {"key": "exposure", "title": "Where it is exposed",
     "blurb": "The other side, and how little is known"},
    {"key": "people", "title": "Who carried it",
     "blurb": "The names behind the figure"},
    {"key": "method", "title": "How this was checked",
     "blurb": "The method, and the audit that followed"},
)


def _insight(key: str, group: str, kicker: str, title: str, body: str, source: str,
             *, tone: str = "flat", stat: int | None = None,
             stat_suffix: str = "", chart: list[dict] | None = None,
             people: list[dict] | None = None) -> dict:
    return {
        "key": key, "group": group, "kicker": kicker, "title": title,
        "body": body, "source": source, "tone": tone,
        "stat": stat, "stat_suffix": stat_suffix,
        "chart": chart or [], "people": people or [],
    }


def _list_phrases(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def _stop(text: str) -> str:
    """Close a sentence lifted from a published constant that has no full stop."""
    return text if text.rstrip()[-1:] in ".!?…" else f"{text.rstrip()}."


def _biggest_gap(pillars: list[dict]) -> dict:
    """The pillar that left the most on the table, i.e. the room to improve."""
    return max(pillars, key=lambda pillar: pillar["shortfall"])


def _lede_title(pillars: list[dict], pair: bool) -> str:
    """A headline that names the pillar which actually moved the score."""
    if pair:
        return (f"{pillars[0]['label']} and {pillars[1]['label'].lower()} "
                f"carried the score")
    key = pillars[0]["key"]
    return {
        "attack": "The batting carried the score",
        "defence": "The bowling carried the score",
        "role_balance": "Squad depth carried the score",
        "coverage": "Simply being there carried the score",
    }[key]


def _insights_swot(results: dict[str, dict]) -> list[dict]:
    squad = results["squad_overview"]
    outlook = results["outlook"]
    swot = squad["swot"]
    team, season = squad["team"], squad["season"]
    score = squad["stability_score"]
    pillars = squad["score_contributions"]
    top, runner, bottom = pillars[0], pillars[1], pillars[-1]
    counts = squad["role_counts"]
    win_rate = outlook["win_rate"]
    leaders = squad["leading_players"][:3]
    maxed = [p for p in pillars if p["shortfall"] == 0]
    open_pillar = _biggest_gap(pillars)

    # Which side of the game was actually better, in the words the reader gets.
    if top["key"] == "defence":
        engine = "The season was won with the ball"
    elif top["key"] == "attack":
        engine = "The season was won with the bat"
    elif top["key"] == "role_balance":
        engine = "The season was won by having the bodies to compete"
    else:
        engine = "The season was won by turning up"

    thin_lead = bool(leaders) and leaders[0]["confidence"] == "Low"
    if win_rate < 40:
        results_title = "A stable season that did not turn into wins"
    elif win_rate < 55:
        results_title = "A steady season with results close to even"
    else:
        results_title = "The results back up the stability number"
    results_body = (
        f"{team} won {outlook['wins']} of the {outlook['decided_matches']} matches that "
        f"produced a result — a {win_rate}% win rate — from a season that scores "
        f"{score} out of 100 on squad stability. Those are two different questions: one "
        f"asks how repeatable the contributions were, the other asks how many of them "
        f"became a win. The gap between them is the most useful thing on this page."
    )

    mix = analytics.role_mix_comment(counts)
    shape_title = (f"A squad {mix}" if "short on" in mix else f"A {mix} squad")

    if len(maxed) >= 2:
        ceiling_title = "Most of this score is already earned"
        ceiling_body = (
            f"{_list_phrases([p['label'].lower() for p in maxed]).capitalize()} sit at "
            f"their published ceiling, so they cannot add another point however well the "
            f"season goes. Everything still on the table sits in "
            f"{open_pillar['label'].lower()}, which is {open_pillar['shortfall']} points "
            f"short of what it could be. {swot['weakness']}"
        )
    elif maxed:
        ceiling_title = "One part of this score comes for free"
        ceiling_body = (
            f"{maxed[0]['label']} is already at its published ceiling, so it cannot add "
            f"another point however well the season goes. The rest is still up for "
            f"grabs, and the biggest opening is {open_pillar['label'].lower()} at "
            f"{open_pillar['shortfall']} points short of its ceiling. {swot['weakness']}"
        )
    else:
        ceiling_title = "Nothing here is maxed out yet"
        ceiling_body = (
            f"Not one of the four pillars has reached its published ceiling, so the "
            f"{score} is a reading of this season rather than a verdict on the squad. "
            f"The narrowest of them is {open_pillar['label'].lower()}, "
            f"{open_pillar['shortfall']} points short of what it could be. "
            f"{swot['weakness']}"
        )

    if open_pillar["shortfall"] == 0:
        ceiling_title = "The score is capped, not just earned"
        ceiling_body = (
            f"Every one of the four pillars sits at its published ceiling, so the {score} "
            f"is as high as this measure can go for one team in one season. Read it as a "
            f"sign of a complete season, not as a reason to widen the squad. "
            f"{swot['weakness']}"
        )

    people_body = (
        f"Ordered by stability, the squad's most repeatable contributors are "
        f"{_list_phrases([p['player'] for p in leaders])}. "
        + (f"The leader of that list is rated on a small enough sample that "
           f"{leaders[0]['stability_score']} should be read within "
           f"{leaders[0]['band']} points rather than as an exact value."
           if thin_lead else
           "Each rating carries a published error band, so the order is more reliable "
           "than any single number inside it.")
    )

    return [
        _insight("verdict", "verdict", f"{team} · {season} · squad stability",
                 _lede_title(pillars, top["points"] - runner["points"] <= 3),
                 f"Squad stability finished at {score} out of 100. {top['label']} added "
                 f"the most, {top['points']} of those points; {bottom['label'].lower()} "
                 f"added the "
                 f"fewest at {bottom['points']}. That gap is what decides where a squad "
                 f"like this one lands, and the honest summary is that {engine.lower()}. "
                 f"{swot['strength']}",
                 "squad_overview", tone="good" if score >= 60 else "flat",
                 stat=score, stat_suffix="/ 100", chart=pillars),

        _insight("ceiling", "drivers", "Where the points went",
                 ceiling_title, ceiling_body, "squad_overview"),

        _insight("engine", "drivers", "The read on the season",
                 f"{engine}, and it shows in the results", results_body,
                 "outlook", tone="down" if win_rate < 40 else "flat"),

        _insight("shape", "drivers", "Squad shape", shape_title,
                 f"{swot['opportunity']} A playing eleven needs a qualifying workload in "
                 f"both disciplines, so this group is the pool the season was actually "
                 f"drawn from — not the whole squad list.",
                 "squad_overview"),

        _insight("weak-side", "exposure", "The side to watch",
                 "The other half of the game", swot["weakness"],
                 "team_metrics", tone="down"),

        _insight("sample", "exposure", "How much is actually known",
                 "What this evidence cannot tell you",
                 f"{swot['threat']} {outlook['limitation']}",
                 "outlook"),

        _insight("people", "people", "Carried by",
                 "The biggest number here rests on the thinnest evidence"
                 if thin_lead else "The most repeatable contributors",
                 people_body, "squad_overview",
                 people=[{"name": p["player"], "role": p["role"],
                          "stat": p["stability_score"],
                          "caption": f"±{p['band']} · {p['confidence'].lower()} sample"}
                         for p in leaders]),

        _insight("method", "method", "Scoring", "How the figure was built",
                 f"{_stop(squad['score_method'])} Every quality index is a comparison "
                 f"with the same season, so {team} is never judged against themselves.",
                 "squad_overview"),
    ]


def _insights_xi(results: dict[str, dict]) -> list[dict]:
    xi = results["best_xi"]
    squad = results["squad_overview"]
    breakdown = xi["breakdown"]
    counts = breakdown["role_counts"]
    squad_counts = squad["role_counts"]
    score = breakdown["score"]
    team, season = xi["team"], xi["season"]
    parts = breakdown["contributions"]
    top, bottom = parts[0], parts[-1]
    open_part = _biggest_gap(parts)
    rules = xi["rules"]

    if top["points"] - parts[1]["points"] <= 3:
        driver = (f"{top['label']} and {parts[1]['label'].lower()} "
                  f"set the ceiling on it")
    elif top["key"] == "quality":
        driver = "The eleven is as good as its best players, nothing more"
    elif top["key"] == "role_balance":
        driver = "Getting a legal mix together was the hard part"
    else:
        driver = "Workload across both disciplines decided it"

    return [
        _insight("verdict", "verdict", f"{team} · {season} · selection",
                 driver,
                 f"The solver's best legal XI scores {score} out of 100: "
                 f"{counts['Batter']} batters, {counts['All-rounder']} all-rounders and "
                 f"{counts['Bowler']} bowlers, with a mean player stability of "
                 f"{breakdown['quality']} across the {breakdown['selected']} picked. "
                 f"{top['label']} did most of that work at {top['points']} points and "
                 f"{bottom['label'].lower()} the least at {bottom['points']}.",
                 "best_xi", tone="good" if score >= 70 else "flat",
                 stat=score, stat_suffix="/ 100", chart=parts),

        _insight("method", "method", "How the side was chosen",
                 f"{xi['role_splits_considered']} legal role splits, one winner",
                 f"{_stop(breakdown['method'])} Every legal split was scored the same way "
                 f"and the highest was kept, so the same squad always returns the same "
                 f"eleven — there is no randomness to argue with.",
                 "best_xi", tone="flat"),

        _insight("rules", "drivers", "The constraints", "What the rules cost",
                 f"A side is only legal at {rules['total']} players with at least "
                 f"{rules['min_batters']} batters, {rules['min_bowlers']} bowlers and "
                 f"{rules['min_all_rounders']} all-rounder. Those floors are why the "
                 f"solver cannot simply pick the highest-rated players available, and why "
                 f"{open_part['label'].lower()} is still {open_part['shortfall']} points "
                 f"short of its ceiling.",
                 "best_xi", tone="flat"),

        _insight("squad", "drivers", "Drawn from the squad", "Who was available",
                 f"The squad behind it holds {squad['players_counted']} players with a "
                 f"recorded contribution — {squad_counts['Batter']} batters, "
                 f"{squad_counts['All-rounder']} all-rounders and "
                 f"{squad_counts['Bowler']} bowlers — at a squad stability of "
                 f"{squad['stability_score']} out of 100. Only the highest-rated of them "
                 f"are named here; the rest are the season's cover, not rejects.",
                 "squad_overview",
                 people=[{"name": p["player"], "role": p["role"],
                          "stat": p["stability_score"], "caption": ""}
                         for p in xi["selection"][:6]]),

        _insight("weak-side", "exposure", "The side to watch",
                 "A single season is a thin read",
                 f"{squad['swot']['threat']} Every rating here comes from one season of "
                 f"the same squad, so treat the eleven as a shape worth starting from "
                 f"rather than a verdict on any individual.",
                 "team_metrics", tone="down"),
    ]


INSIGHT_BUILDERS: dict[str, Callable[[dict], list[dict]]] = {
    "swot": _insights_swot,
    "xi": _insights_xi,
}


def _display_values(insights: list[dict]) -> str:
    """Every figure the UI paints but does not spell out in a sentence.

    The verifier audits these too, so "every number on the page traces back to a
    tool result" is literally true and not just true of the prose.
    """
    values: list[str] = []
    for insight in insights:
        if insight["stat"] is not None:
            values.append(str(insight["stat"]))
        values += [str(part["points"]) for part in insight["chart"]]
        values += [f"{person['stat']} {person['caption']}" for person in insight["people"]]
    return " ".join(values)


def report(season: str, team: str, kind: str = "swot") -> dict:
    """Run the full harness: plan -> tools -> narrate -> verify."""
    if kind not in PLAN:
        raise AgentError(f"Unknown report kind '{kind}'. Available: {', '.join(PLAN)}")

    trace: list[dict] = []
    results: dict[str, dict] = {}
    for agent, tool in PLAN[kind]:
        results[tool] = _run_tool(agent, tool, {"season": season, "team": team}, trace)

    sentences = NARRATORS[kind](results)
    corpus = _corpus(results)
    narrative: list[dict] = []
    insights = INSIGHT_BUILDERS[kind](results)
    flagged: list[str] = []
    checked = 0

    def audit(text: str) -> str:
        nonlocal checked
        outcome = verify(text, corpus)
        checked += outcome["checked_numbers"]
        flagged.extend(outcome["flagged"])
        return outcome["text"]

    for sentence in sentences:
        narrative.append({"text": audit(sentence["text"]), "source": sentence["source"]})
    for insight in insights:
        insight["body"] = audit(insight["body"])
    audit(_display_values(insights))

    return {
        "kind": kind,
        "season": season,
        "team": team,
        "narrative": narrative,
        "insights": insights,
        "groups": list(INSIGHT_GROUPS),
        "evidence": [
            {"source": tool, "description": TOOLS[tool]["description"],
             "agent": agent}
            for agent, tool in PLAN[kind]
        ],
        "trace": trace,
        "verifier": {
            "ok": not flagged,
            "checked_numbers": checked,
            "flagged": flagged,
            "rule": "Every number must already exist in a tool result",
        },
        "budget": {"max_tool_calls": MAX_TOOL_CALLS, "used": len(trace)},
    }
