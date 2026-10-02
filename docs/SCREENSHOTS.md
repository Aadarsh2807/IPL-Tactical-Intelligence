# Screenshots

Every image here was captured from the running application by driving Chrome
over the DevTools protocol, so each one shows the app in a state a reader can
actually reach: a team selected, the agent harness run, the audit panels
opened. Nothing here is a mock-up.

The README links to the eight that matter most. The rest are the full set.

## Squad — stability and SWOT

| Score and pillars | The player table |
|---|---|
| ![](images/01-squad-stability.png) | ![](images/02-squad-players.png) |
| The headline figure, its four contributing pillars, and the plain-English sentence above them | 21 players with reliability, match-by-match sparklines and per-season figures |

| How the figure was built | A different team, same layout |
|---|---|
| ![](images/03-squad-how-built.png) | ![](images/04-squad-different-team.png) |
| The breakdown of how the score was composed | Delhi Capitals — the accent colour follows the team, nothing is hardcoded |

## XI builder

| Solved side | A player opened |
|---|---|
| ![](images/05-xi-builder.png) | ![](images/06-xi-filtered-bowlers.png) |
| The best legal XI under the enforced role constraints | One player's contribution to the solve |

## Matchups

| Before a pair is chosen | A recorded pair |
|---|---|
| ![](images/07-matchups-empty.png) | ![](images/08-matchups-pair.png) |
| The empty state, explaining the evidence rule | A real batter-vs-bowler pair, graded by sample size |

## Outlook

![](images/09-outlook.png)

*A bounded estimate with its method and its limitations printed on the page.*

## Report — the agent harness

| Before a run | Verified |
|---|---|
| ![](images/10-report-empty.png) | ![](images/11-report-masthead.png) |
| The harness panel, stating that no language model runs | `VERIFIED`, 73 numbers traced back to tool results |

| Insight groups | What drove the number |
|---|---|
| ![](images/12-report-insights.png) | ![](images/13-report-insights-2.png) |
| Drivers, strengths and weaknesses as editorial cards | Exposure and the method behind the score |

| Audit | Tool trace |
|---|---|
| ![](images/14-report-audit.png) | ![](images/15-report-trace.png) |
| Every sentence paired with the tool that produced it | Each tool call with its agent, arguments, duration and result size |

## Report — selection narrative

| Verified | Insights |
|---|---|
| ![](images/16-report-selection.png) | ![](images/17-report-selection-insights.png) |
| The same harness, scoring the selected eleven: 69 of 100 across three pillars | The constraints the solve had to satisfy, and who it drew from |

## Walkthrough

![Walkthrough of all five views](images/walkthrough.gif)
