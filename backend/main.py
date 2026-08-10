"""IPL analysis API. Every result is calculated from data/IPL.csv."""
from functools import lru_cache
from pathlib import Path
import os

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="IPL Tactical Intelligence")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
REQUIRED = {"match_id", "date", "season", "event_name", "batting_team", "bowling_team", "batter", "bowler", "runs_batter", "runs_bowler", "runs_total", "balls_faced", "valid_ball", "bowler_wicket", "player_out", "win_outcome"}


def csv_path():
    options = [Path(os.environ["IPL_CSV_PATH"])] if os.getenv("IPL_CSV_PATH") else []
    options.append(Path(__file__).resolve().parent.parent / "data" / "IPL.csv")
    return next((p for p in options if p.is_file()), None) or (_ for _ in ()).throw(RuntimeError("Put IPL.csv in data/IPL.csv or set IPL_CSV_PATH."))


@lru_cache(maxsize=1)
def deliveries():
    data = pd.read_csv(csv_path(), low_memory=False)
    missing = REQUIRED - set(data.columns)
    if missing: raise RuntimeError(f"IPL.csv is missing: {', '.join(sorted(missing))}")
    data = data[data.event_name.eq("Indian Premier League")].copy()
    data["season"] = data["season"].astype(str)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    for c in ["runs_batter", "runs_bowler", "runs_total", "balls_faced", "valid_ball", "bowler_wicket"]:
        data[c] = pd.to_numeric(data[c], errors="coerce").fillna(0)
    return data.dropna(subset=["batter", "bowler", "batting_team", "bowling_team"])


def n(value, digits=2): return round(float(value), digits)
def scoped(season):
    data = deliveries()[deliveries().season.eq(str(season))]
    if data.empty: raise HTTPException(404, "That season is not present in the supplied IPL data")
    return data
def team_names(data): return sorted(set(data.batting_team) | set(data.bowling_team))


def player_table(data, team):
    bat_rows, bowl_rows = data[data.batting_team.eq(team)], data[data.bowling_team.eq(team)]
    batting = bat_rows.groupby("batter", as_index=False).agg(runs=("runs_batter", "sum"), batting_balls=("balls_faced", "sum")).rename(columns={"batter": "player"})
    dismissals = bat_rows.loc[bat_rows.player_out.eq(bat_rows.batter)].groupby("batter").size().rename("dismissals")
    batting = batting.merge(dismissals, left_on="player", right_index=True, how="left").fillna({"dismissals": 0})
    bowling = bowl_rows.groupby("bowler", as_index=False).agg(wickets=("bowler_wicket", "sum"), runs_conceded=("runs_bowler", "sum"), bowling_balls=("valid_ball", "sum")).rename(columns={"bowler": "player"})
    players = batting.merge(bowling, on="player", how="outer").fillna(0)
    players["strike_rate"] = (100 * players.runs / players.batting_balls.replace(0, pd.NA)).fillna(0)
    players["economy"] = (6 * players.runs_conceded / players.bowling_balls.replace(0, pd.NA)).fillna(0)
    players["role"] = "Batter"
    players.loc[(players.batting_balls >= 18) & (players.bowling_balls >= 18), "role"] = "All-rounder"
    players.loc[(players.bowling_balls >= 36) & (players.batting_balls < 18), "role"] = "Bowler"
    players["impact"] = players.runs + 20 * players.wickets
    return players.sort_values(["impact", "batting_balls", "bowling_balls"], ascending=False), bat_rows, bowl_rows


@app.get("/api/health")
def health(): return {"status": "ok", "deliveries": len(deliveries()), "source": csv_path().name}
@app.get("/api/seasons")
def seasons(): return sorted(deliveries().season.unique().tolist(), reverse=True)
@app.get("/api/teams")
def teams(season: str = Query(...)): return team_names(scoped(season))
@app.get("/api/batters")
def batters(season: str = Query(...), team: str | None = None):
    data = scoped(season)
    return sorted((data[data.batting_team.eq(team)] if team else data).batter.unique().tolist())


@app.get("/api/squad/{team}")
def squad(team: str, season: str = Query(...)):
    data = scoped(season)
    if team not in team_names(data): raise HTTPException(404, "Team is not present in this season")
    players, bat_rows, bowl_rows = player_table(data, team)
    batting_depth, bowling_depth = int((players.batting_balls >= 18).sum()), int((players.bowling_balls >= 36).sum())
    roles = {r: int((players.role == r).sum()) for r in ["Batter", "All-rounder", "Bowler"]}
    appearances = max(bat_rows.match_id.nunique(), bowl_rows.match_id.nunique())
    # Seasonal league comparison creates evidence-led SWOT rather than stock phrases.
    team_for = bat_rows.groupby(["match_id", "innings"]).runs_total.sum().mean()
    team_against = bowl_rows.groupby(["match_id", "innings"]).runs_total.sum().mean()
    league_innings = data.groupby(["match_id", "innings"]).runs_total.sum().mean()
    attack = team_for / league_innings if league_innings else 0
    defence = league_innings / team_against if team_against else 0
    # Quality is normalized against a strong (1.30x league) benchmark, so a
    # full squad alone cannot automatically receive 100.
    role_balance = (min(batting_depth / 6, 1) + min(bowling_depth / 5, 1)) / 2
    stability = round(100 * (.35 * min(attack / 1.30, 1) + .35 * min(defence / 1.30, 1) + .20 * role_balance + .10 * min(appearances / 14, 1)))
    best = max(((attack, "batting"), (defence, "bowling")), key=lambda x: x[0])
    worst = min(((attack, "batting"), (defence, "bowling")), key=lambda x: x[0])
    swot = {
        "strength": f"{best[1].title()} index {best[0]:.2f} versus the {season} league baseline.",
        "weakness": f"{worst[1].title()} index {worst[0]:.2f} versus the {season} league baseline.",
        "opportunity": f"Role balance: {roles['Batter']} batters, {roles['All-rounder']} all-rounders and {roles['Bowler']} bowlers with a recorded seasonal contribution.",
        "threat": f"Season sample is {appearances} matches; use the report with caution when the sample is small.",
    }
    return {"team": team, "season": season, "stability_score": stability, "score_method": "35% batting quality, 35% bowling quality, 20% role balance, 10% match coverage", "role_counts": roles, "swot": swot, "notes": [f"{appearances} matches in the selected season.", "Only deliveries for the chosen team and season are included."], "players": [{"player": r.player, "role": r.role, "runs": int(r.runs), "batting_balls": int(r.batting_balls), "strike_rate": n(r.strike_rate), "wickets": int(r.wickets), "bowling_balls": int(r.bowling_balls), "economy": n(r.economy)} for r in players.itertuples(index=False)]}


@app.get("/api/matchup/bowlers")
def bowlers_for_batter(batter: str = Query(..., min_length=1), season: str = Query(...)):
    rows = scoped(season).loc[lambda x: x.batter.eq(batter)]
    if rows.empty: raise HTTPException(404, "Batter has no deliveries in this season")
    return sorted(rows.bowler.unique().tolist())
@app.get("/api/matchup")
def matchup(batter: str = Query(..., min_length=1), bowler: str = Query(..., min_length=1), season: str = Query(...)):
    rows = scoped(season).loc[lambda x: x.batter.eq(batter) & x.bowler.eq(bowler)]
    if rows.empty: raise HTTPException(404, "This pair has no recorded head-to-head deliveries in this season")
    balls, runs, valid = rows.balls_faced.sum(), rows.runs_batter.sum(), rows.valid_ball.sum()
    wickets = rows.loc[rows.player_out.eq(batter), "bowler_wicket"].sum()
    return {"season": season, "batter": batter, "bowler": bowler, "matches": int(rows.match_id.nunique()), "balls": int(balls), "runs": int(runs), "dismissals": int(wickets), "strike_rate": n(100 * runs / balls) if balls else 0, "runs_per_ball": n(runs / balls) if balls else 0, "bowler_economy": n(6 * rows.runs_bowler.sum() / valid) if valid else None, "evidence": "High" if balls >= 30 else "Medium" if balls >= 12 else "Limited", "message": f"Head-to-head evidence from {season} IPL deliveries."}


@app.get("/api/season-outlook/{team}")
def season_outlook(team: str, season: str = Query(...)):
    data = scoped(season)
    if team not in team_names(data): raise HTTPException(404, "Team is not present in this season")
    _, bat_rows, bowl_rows = player_table(data, team)
    scored = bat_rows.groupby(["match_id", "innings"]).runs_total.sum().mean()
    conceded = bowl_rows.groupby(["match_id", "innings"]).runs_total.sum().mean()
    league = data.groupby(["match_id", "innings"]).runs_total.sum().mean()
    matches = data.drop_duplicates("match_id")[["match_id", "win_outcome"]]
    played = data[(data.batting_team.eq(team)) | (data.bowling_team.eq(team))].match_id.unique()
    match_meta = matches[matches.match_id.isin(played)]
    completed = match_meta.win_outcome.notna() & ~match_meta.win_outcome.isin(["NA", "No result", "Tie"])
    decided = match_meta[completed]
    wins, decided_count = int(decided.win_outcome.eq(team).sum()), len(decided)
    win_rate = wins / decided_count if decided_count else .5
    attack, defence = scored / league if league else 0, league / conceded if conceded else 0
    performance_index = .45 * attack + .35 * defence + .20 * win_rate
    next_win_probability = max(20, min(80, round(50 + (performance_index - .90) * 100)))
    return {"team": team, "season": season, "matches": int(len(match_meta)), "wins": wins, "win_rate": n(100 * win_rate, 1), "average_score": n(scored, 1), "average_conceded": n(conceded, 1), "league_average": n(league, 1), "attack_index": n(attack), "defence_index": n(defence), "performance_index": n(performance_index), "next_match_win_probability": next_win_probability, "method": "45% seasonal scoring index, 35% seasonal defence index, 20% decided-match win rate; bounded to 20–80% to avoid false certainty."}
