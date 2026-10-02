# The agentic layer

## Why there is AI here at all

Only two features genuinely benefit from an agent: **narrating** a squad report and
**coaching** an XI selection. Both are the same shape — gather several audited facts, then
explain them in prose. Everything else in this project is a deterministic formula, because a
formula can be tested, argued and reproduced, and a language model cannot.

So the AI surface is deliberately tiny, and the interesting part is not the model — it never
runs — but the **harness** around it.

## The three concepts, precisely

**Subagent** — a role-scoped worker with its own tool whitelist and a single output
contract. Access control is enforced in code, not in a prompt:

```python
AGENT_TOOLS = {
    "Analyst":  ("squad_overview", "team_metrics", "outlook"),
    "Coach":    ("best_xi", "squad_overview"),
    "Verifier": (),          # runs no tools: it audits text
}
```

Calling a tool you are not permitted produces `AgentError` — covered by
`test_an_agent_cannot_call_another_agents_tool`.

**Harness** — the scaffolding around a worker: which tools exist, what each may call, a call
budget (≤ 6), a recorded trace, and a final audit. The harness is what makes an agent
reproducible and safe; the model is an interchangeable part inside it.

**AI harnessing** — the discipline of treating that scaffolding as the product: interfaces,
budgets, validation, tracing and evaluation. A harness with no model is still worth
building, because the day a model is plugged in, everything that protects you is already
there.

## The harness

```
POST /api/agent/report  { season, team, kind: "swot" | "xi" }

  1. PLAN      kind → ordered (agent, tool) pairs. Anything unplanned cannot run.
  2. TOOLS     each call is executed, timed and appended to `trace`.
               Budget exceeded → AgentError. Unknown team → AgentError.
  3. NARRATE   rule-based prose assembled only from tool outputs. Each sentence
               records which tool produced its facts.
  4. INSIGHT   the same facts grouped into a readable report: one lead figure, an
               inference under it, then the evidence, the risks and the people.
  5. VERIFY    every number in the draft is regex-extracted and must already exist
               in the corpus of tool outputs. Anything untraceable is replaced with
               "[unverified]".
```

## Narrative and insight are different jobs

The `narrative` is the audit trail: flat, numbered, one tool source per sentence. It is
what a reviewer reads to check a claim, and it is deliberately boring.

The `insights` are the same facts arranged as a report, cut into published groups
(`INSIGHT_GROUPS`: verdict → drivers → exposure → people → method). Each insight carries a
kicker, a headline judgement, a body, its source tool, and optionally a lead figure, a bar
chart or a list of names. Headlines are *derived*, not written: the verdict names whichever
pillar actually contributed the most points, and changes when the top two are within three
points of each other.

The bar charts come from `analytics` (`score_contributions`, `contributions`), which splits
a score into whole points that add back to the total. That is why the report can say "bowling
added 28 of those points" and mean it.

### The audit covers the drawing, not just the writing

A chart is still a claim, so `_display_values()` feeds every painted figure — the lead stat,
the bar values, the names and their error bands — through the same `verify()` call as the
prose. A poisoned bar value is caught even though it appears in no sentence.

### Why the verifier is the whole point

```python
def verify(narrative, corpus, *, redact=True):
    allowed = {round(float(m), 2) for m in NUMBER_PATTERN.findall(corpus)}
    ...
```

A model asked to "write an insightful summary" will eventually produce a number that was not
in its inputs — usually by re-deriving one wrongly. Redacting untraceable figures means the
failure mode is a visibly empty sentence rather than a confident, wrong statistic. The
verifier is a pure function over two strings, which is why it is trivial to test:

| Test | Asserts |
|---|---|
| `test_verifier_rejects_a_number_not_in_the_tool_output` | a poisoned `999` is redacted while a traced `14` survives |
| `test_verifier_accepts_numbers_that_do_trace_to_the_corpus` | `84.20` matches `84.2` after rounding |
| `test_the_audit_covers_drawn_figures_not_only_prose` | a poisoned bar value is flagged even though it is in no sentence |
| `test_insights_are_grouped_and_every_group_is_published` | sections come from `INSIGHT_GROUPS`, not from the UI |
| `test_reports_hold_across_many_teams` | no team can accidentally trip the verifier (catches corpus gaps such as "out of 100") |
| `test_tool_budget_is_enforced` | the 7th call is refused |
| `test_an_agent_cannot_call_another_agents_tool` | access control is code, not prompt |

Current run: **62–73 numbers checked, 0 flagged** depending on report kind, with the
sentence-by-sentence audit and the full tool trace both visible in the UI.

## The Narrator is an interface, not a sentence

`narrate()` currently returns deterministic prose. That is a deliberate implementation of a
contract:

> *Produce sentences that cite tool facts. Every number will be checked.*

If a model is added later, only `narrate()` changes. The tools, budget, trace and verifier
stay exactly as they are — and the verifier protects the new narrator too, which is the
reason to build the harness first. No model path is included today, because untested code
would be the weakest part of the project.

## Costs and failure modes, stated plainly

- **Runs offline.** No API key, no network call, no cost, deterministic output.
- **Cannot lie numerically.** Prose can still be dull; numbers cannot be invented.
- **Needs a small, well-defined fact set.** That is why it is used in two places and not five.
- **The verifier is a whitelist, not a reasoner.** It proves a number came from a tool; it
  cannot prove the sentence interprets that number correctly. That limitation is stated here
  rather than implied away.
