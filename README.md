# IPL Tactical Intelligence

**A data-driven IPL analytics application for season-specific squad analysis, player matchups, and team performance outlooks.**

> Built to replace static sports dashboards with evidence that can be traced back to ball-by-ball match data.

## Why this project matters

Sports decisions are often presented with generic player lists and unverified recommendations. This application answers three practical questions using the supplied IPL delivery dataset:

1. **How balanced was a team in a selected season?**
2. **What actually happened when a batter faced a particular bowler that season?**
3. **What does a team's seasonal performance suggest about its next-match outlook?**

## Features

### 1. Season Squad Builder & SWOT Report

- Choose an IPL season and team.
- Lists only players who batted or bowled for that team in that season.
- Infers a player role from recorded batting and bowling contribution.
- Produces a dynamic stability score from batting quality, bowling quality, role balance and match coverage.
- Generates an evidence-led SWOT report using the selected team's performance against that season's league baseline.

### 2. Season Player-vs-Player Matchups

- Choose a season, batter and bowler.
- The bowler list contains only opponents who actually bowled to that batter in that season.
- Returns balls faced, runs, dismissals, strike rate, runs per ball, match count and an evidence label.

### 3. Season Performance Outlook

- Calculates a transparent next-match probability from seasonal scoring, defence and decided-match win rate.
- Shows the underlying matches, wins, average scored and average conceded values.
- Uses bounded estimates to avoid presenting a historical model as certainty.

## Data integrity

- All teams, players, roles, scores, SWOT statements and matchup options are derived from `data/IPL.csv` at runtime.
- No hardcoded squads, player names, fake recommendations or arbitrary fixed scores.
- The application filters the supplied dataset to `Indian Premier League` records before analysis.

## Tech stack

- **Frontend:** React, Vite, Tailwind CSS
- **Backend:** FastAPI, Pandas
- **Data:** IPL ball-by-ball delivery CSV

## Architecture

```text
React dashboard → FastAPI endpoints → Pandas aggregations → IPL delivery dataset
```

The frontend requests data through Vite's `/api` proxy. The backend computes all aggregations in memory from the supplied CSV and exposes season-scoped API endpoints.

## Run locally

### Backend

```powershell
cd backend
py -m pip install -r requirements.txt
py -m uvicorn main:app --reload --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the local Vite address, normally `http://localhost:5173`.

## Dataset setup

The CSV is intentionally excluded from Git because it exceeds GitHub's standard per-file size limit. Place a compatible dataset at:

```text
data/IPL.csv
```

Or set `IPL_CSV_PATH` to the location of your CSV before starting the backend.

## Responsible interpretation

The outlook is an analytical historical estimate, not a betting recommendation or guaranteed prediction. It is designed to make its input metrics visible and to surface limited samples clearly.

## Recruiter highlights

- Converts a messy, large ball-by-ball dataset into usable product features.
- Demonstrates backend API design, frontend state management and data aggregation.
- Prevents misleading results through constrained, evidence-only player selections.
- Communicates modelling assumptions instead of hiding them behind a black box.
