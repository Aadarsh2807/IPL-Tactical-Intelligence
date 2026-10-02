import { useState } from 'react'
import { post } from '../lib/api'
import { squadWord, xiWord } from '../lib/format'
import {
  Panel, Chip, EmptyState, ErrorState, Loading, Field, selectClass,
  LeadFigure, PillarBars, SectionTitle, InsightCard, PeopleStrip, NarrativeList,
} from './ui'

const KINDS = [
  { id: 'swot', label: 'Squad narrative', word: squadWord },
  { id: 'xi', label: 'Selection narrative', word: xiWord },
]

/**
 * The agent harness, made visible.
 *
 * A report is a page, not a list: one figure the reader can hold on to, an
 * inference under it, then the evidence grouped so it can be skimmed. The
 * audit trail — the verifier result, the raw sentences, every tool call — is
 * kept on the page rather than hidden, because that is the part that makes the
 * claims above it checkable.
 */
export default function ReportPanel({ season, team }) {
  const [kind, setKind] = useState('swot')
  const [report, setReport] = useState(null)
  const [state, setState] = useState({ loading: false, error: '' })
  const [showTrace, setShowTrace] = useState(false)
  const [showAudit, setShowAudit] = useState(false)

  async function run() {
    setState({ loading: true, error: '' })
    setReport(null)
    try {
      setReport(await post('/api/agent/report', { season, team, kind }))
      setState({ loading: false, error: '' })
    } catch (error) {
      setState({ loading: false, error: error.message })
    }
  }

  function switchKind(next) {
    setKind(next)
    setReport(null)
    setState({ loading: false, error: '' })
  }

  const verdict = report?.insights.find((insight) => insight.group === 'verdict')
  const wordFor = KINDS.find((option) => option.id === report?.kind)?.word ?? squadWord

  return (
    <div className="space-y-4">
      <Panel
        title="Harness"
        meta={`tools gather · narrator writes · verifier audits · ${report?.budget.max_tool_calls ?? 6} call cap`}
      >
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-52">
            <Field id="report-kind" label="Report">
              <select
                id="report-kind"
                value={kind}
                onChange={(event) => switchKind(event.target.value)}
                className={selectClass}
              >
                {KINDS.map((option) => (
                  <option key={option.id} value={option.id}>{option.label}</option>
                ))}
              </select>
            </Field>
          </div>
          <button
            type="button"
            onClick={run}
            disabled={state.loading || !season || !team}
            className="px-5 py-2 text-xs uppercase tracking-[0.16em] disabled:opacity-50"
            style={{ background: 'var(--accent)', color: 'var(--accent-ink)' }}
          >
            {state.loading ? 'Running…' : 'Run harness'}
          </button>
          <p className="kicker ml-auto self-center" style={{ color: 'var(--accent)' }}>
            {team} · {season}
          </p>
        </div>

        <p className="copy mt-4 border-t border-line pt-3">
          No language model runs here. The Analyst and Coach subagents call audited
          tools, the Narrator writes from those results, and the Verifier redacts any
          number it cannot trace back to a tool output — including the figures drawn
          in the bars and cards below, not just the ones in the sentences.
        </p>
      </Panel>

      {state.loading && <Loading rows={4} label="Running subagents" />}
      {state.error && <ErrorState message={state.error} onRetry={run} />}

      {!report && !state.loading && !state.error && (
        <EmptyState title="No run yet" hint="Press Run harness to generate a verified report." />
      )}

      {report && verdict && (
        <>
          {/* Masthead: the one number, the judgement, and how it was made up */}
          <section className="border border-line bg-panel">
            <div className="grid gap-px bg-line lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
              <div className="bg-panel p-6 lg:p-8">
                <p className="kicker" style={{ color: 'var(--accent)' }}>{verdict.kicker}</p>
                <div className="mt-4 flex flex-wrap items-end gap-x-8 gap-y-4">
                  <LeadFigure
                    value={verdict.stat}
                    suffix={verdict.stat_suffix}
                    word={wordFor(verdict.stat)}
                  />
                </div>
                <h2 className="display-title mt-6 max-w-[34ch]">{verdict.title}</h2>
                <p className="lede mt-3 max-w-[62ch]">{verdict.body}</p>
              </div>

              <div className="bg-panel-2 p-6 lg:p-8">
                <p className="kicker">How the figure was made up</p>
                <p className="mt-2 text-[11px] leading-relaxed text-ink-faint">
                  Each bar is the points that part of the score actually added. The faint
                  bar behind it is the most that part could contribute, so the empty space
                  is the room left to improve.
                </p>
                <div className="mt-5">
                  <PillarBars items={verdict.chart} />
                </div>
                <p className="mt-5 border-t border-line pt-3 text-[11px] leading-relaxed text-ink-faint">
                  These {verdict.chart.length} bars add back to the figure on the left
                  exactly, so nothing in the score is left unexplained.
                </p>
              </div>
            </div>

            <footer className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line px-6 py-3 lg:px-8">
              <Chip tone={report.verifier.ok ? 'good' : 'bad'}>
                {report.verifier.ok ? 'verified' : `${report.verifier.flagged.length} unverified`}
              </Chip>
              <span className="label">{report.verifier.checked_numbers} numbers traced</span>
              <span className="label">
                {report.budget.used} of {report.budget.max_tool_calls} tool calls used
              </span>
              <span className="label ml-auto">from {report.evidence.length} audited tools</span>
            </footer>
          </section>

          {report.groups.map((group) => {
            // The verdict is the masthead above, so it is not repeated here.
            if (group.key === 'verdict') return null
            const items = report.insights.filter((insight) => insight.group === group.key)
            if (!items.length) return null
            const lastIsAlone = items.length % 2 === 1
            return (
              <section key={group.key}>
                <SectionTitle
                  kicker={String(report.groups.indexOf(group) + 1).padStart(2, '0')}
                  title={group.title}
                  blurb={group.blurb}
                />
                <div className="grid gap-4 lg:grid-cols-2">
                  {items.map((insight, index) => (
                    <InsightCard
                      key={insight.key}
                      insight={insight}
                      wide={lastIsAlone && index === items.length - 1}
                    />
                  ))}
                </div>
                {group.key === 'people' && items[0]?.people.length > 0 && (
                  <div className="mt-4">
                    <PeopleStrip people={items[0].people} />
                  </div>
                )}
              </section>
            )
          })}

          {/* The audit trail: kept on the page, not tucked away */}
          <Panel title="Audit" meta={`${report.trace.length} tool calls recorded`} dense>
            <button
              type="button"
              onClick={() => setShowAudit(!showAudit)}
              aria-expanded={showAudit}
              className="flex w-full items-center justify-between gap-3 border-b border-line p-4 text-left text-xs uppercase tracking-[0.16em] text-ink-dim hover:text-ink"
            >
              <span>Sentence-by-sentence check</span>
              <span className="label">{showAudit ? 'Hide' : 'Show'}</span>
            </button>

            {showAudit && (
              <div className="p-4">
                <p className="copy">
                  {report.verifier.rule}. Every line below is the narrator's own output
                  with its source tool; anything the verifier could not trace would appear
                  as <span className="figure text-down">[unverified]</span> rather than as a
                  number.
                </p>
                <div className="mt-4">
                  <NarrativeList narrative={report.narrative} />
                </div>
                <p className="kicker mt-5">What this run was allowed to call</p>
                <ul className="mt-2 grid gap-1 sm:grid-cols-3">
                  {report.evidence.map((item) => (
                    <li key={item.source} className="border border-line px-3 py-2">
                      <p className="label" style={{ color: 'var(--accent)' }}>{item.agent}</p>
                      <p className="figure mt-1 text-xs">{item.source}</p>
                      <p className="mt-1 text-[11px] leading-relaxed text-ink-faint">
                        {item.description}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Panel>

          <Panel title="Tool trace" meta="replayable" dense>
            <button
              type="button"
              onClick={() => setShowTrace(!showTrace)}
              aria-expanded={showTrace}
              className="flex w-full items-center justify-between gap-3 border-b border-line p-4 text-left text-xs uppercase tracking-[0.16em] text-ink-dim hover:text-ink"
            >
              <span>Show agent trace</span>
              <span className="label">{showTrace ? 'Hide' : `${report.trace.length} calls`}</span>
            </button>

            {showTrace && (
              <>
                <ul className="divide-y divide-line">
                  {report.trace.map((step, index) => (
                    <li key={index} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3">
                      <span className="figure w-6 text-[11px] text-ink-faint">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <span
                        aria-hidden="true"
                        className="h-1.5 w-1.5 shrink-0 self-center"
                        style={{ background: 'var(--accent)' }}
                      />
                      <span className="kicker w-20">{step.agent}</span>
                      <span className="figure flex-1 text-[13px] text-ink">{step.tool}</span>
                      <span className="figure text-[11px] text-ink-faint">
                        {Object.entries(step.args).map(([key, value]) => `${key}=${value}`).join(' · ')}
                      </span>
                      <span className="figure ml-auto text-[11px] text-ink-dim">
                        {step.elapsed_ms} ms · {step.result_bytes} B
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="copy border-t border-line px-4 py-3">
                  The budget is the part most agent demos skip: an agent that can call tools
                  without limit will call them until it likes the answer. Here the cap is
                  {` ${report.budget.max_tool_calls} `}
                  calls, every one of them is attributed to an agent, and the Narrator
                  cannot see a tool the plan did not run.
                </p>
              </>
            )}
          </Panel>
        </>
      )}
    </div>
  )
}
