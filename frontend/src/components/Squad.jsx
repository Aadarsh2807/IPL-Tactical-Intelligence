import { Fragment, useMemo, useState } from 'react'
import { useResource, encode } from '../lib/api'
import { describeIndex, stabilityWord, stabilityTone, confidenceText, roleMixComment, squadWord, fmt, oneDp, plural } from '../lib/format'
import { Panel, PlainStat, Takeaway, Sparkline, Loading, ErrorState, EmptyState, Field, selectClass } from './ui'

const ROLE_FILTERS = ['All', 'Batter', 'All-rounder', 'Bowler']
const SORTS = {
  stability: { label: 'Most reliable', get: (p) => p.stability_score },
  runs: { label: 'Most runs', get: (p) => p.runs },
  wickets: { label: 'Most wickets', get: (p) => p.wickets },
  sample: { label: 'Largest sample', get: (p) => p.sample_balls },
}

export default function Squad({ season, team }) {
  const { data, error, loading } = useResource(
    season && team ? `/api/squad/${encode(team)}?season=${encode(season)}` : '',
  )
  const [role, setRole] = useState('All')
  const [sort, setSort] = useState('stability')
  const [open, setOpen] = useState(null)
  const [showMethod, setShowMethod] = useState(false)

  const players = useMemo(() => {
    if (!data) return []
    const sorter = SORTS[sort].get
    return data.players
      .filter((player) => role === 'All' || player.role === role)
      .sort((a, b) => sorter(b) - sorter(a) || a.player.localeCompare(b.player))
  }, [data, role, sort])

  if (loading) return <Loading rows={6} label={`Reading ${team} ${season} deliveries`} />
  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />
  if (!data) return <EmptyState title="No squad loaded" hint="Pick a season and a team." />

  const { score_breakdown: breakdown, score_method: method } = data
  const counts = data.role_counts
  const batting = describeIndex(breakdown.attack_index)
  const bowling = describeIndex(breakdown.defence_index)
  const mix = roleMixComment(counts)
  const stronger = (batting.delta ?? 0) >= (bowling.delta ?? 0) ? 'batting' : 'bowling'

  return (
    <div className="space-y-4">
      <Takeaway>
        In {season}, {team} were{' '}
        <span className={stronger === 'batting' ? 'text-up' : 'text-down'}>
          {batting.text.toLowerCase()}
        </span>{' '}
        with the bat and{' '}
        <span className={stronger === 'bowling' ? 'text-up' : 'text-down'}>
          {bowling.text.toLowerCase()}
        </span>{' '}
        with the ball. The squad is <strong>{mix}</strong> — {counts.Batter} batters,{' '}
        {counts['All-rounder']} all-rounders and {counts.Bowler} bowlers all contributed.
        Overall that is a <strong>{squadWord(data.stability_score).toLowerCase()}</strong>{' '}
        ({data.stability_score} out of 100).
      </Takeaway>

      <Panel title={`${team} · ${season}`} meta={`${data.players.length} players contributed`}>
        <div className="grid gap-6 md:grid-cols-[auto_1fr]">
          <div>
            <p className="figure text-7xl leading-none" style={{ color: 'var(--accent)' }}>
              {data.stability_score}
            </p>
            <p className="mt-1.5 text-sm text-ink-dim">{squadWord(data.stability_score)}</p>
            <p className="label mt-2">out of 100</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <PlainStat
              label="Scoring"
              text={batting.text}
              tone={batting.tone}
              value={Math.round((breakdown.attack_index / 1.3) * 100)}
            />
            <PlainStat
              label="Bowling"
              text={bowling.text}
              tone={bowling.tone}
              value={Math.round((breakdown.defence_index / 1.3) * 100)}
            />
            <PlainStat label="Role mix" text={mix} tone={mix === 'short on bowling' || mix === 'short on batting' ? 'down' : 'up'} />
            <PlainStat label="Season played" text={breakdown.coverage >= 100 ? 'Full season' : 'Part of the season'} tone="flat" value={breakdown.coverage} />
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowMethod(!showMethod)}
          className="mt-5 border-t border-line pt-3 text-left text-[11px] uppercase tracking-[0.14em] text-ink-faint hover:text-ink"
        >
          {showMethod ? 'Hide' : 'How is this number built?'}
        </button>
        {showMethod && (
          <p className="mt-2 text-xs leading-relaxed text-ink-faint">{method}</p>
        )}
      </Panel>

      <Panel title="Who you can rely on" meta="50 = an average player this season" dense>
        <div className="flex flex-wrap items-end gap-3 border-b border-line p-3">
          <Field id="role-filter" label="Show">
            <select id="role-filter" value={role} onChange={(e) => setRole(e.target.value)} className={selectClass}>
              {ROLE_FILTERS.map((name) => <option key={name}>{name}</option>)}
            </select>
          </Field>
          <Field id="sort-by" label="Order by">
            <select id="sort-by" value={sort} onChange={(e) => setSort(e.target.value)} className={selectClass}>
              {Object.entries(SORTS).map(([key, value]) => (
                <option key={key} value={key}>{value.label}</option>
              ))}
            </select>
          </Field>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-line text-left">
                <th className="label px-3 py-2">Player</th>
                <th className="label px-3 py-2">Reliability</th>
                <th className="label px-3 py-2">Match by match</th>
                <th className="label px-3 py-2">Season</th>
                <th className="label px-3 py-2 text-right">Details</th>
              </tr>
            </thead>
            <tbody>
              {players.map((player) => (
                <Fragment key={player.player}>
                  <tr className="border-b border-line hover:bg-panel-2">
                    <td className="px-3 py-2.5">
                      <p className="font-medium">{player.player}</p>
                      <p className="label">{player.role}</p>
                    </td>
                    <td className="px-3 py-2.5">
                      <p className="figure text-lg leading-none">{player.stability_score}</p>
                      <p className={`mt-1 text-xs ${stabilityTone(player.stability_score) === 'up'
                        ? 'text-up' : stabilityTone(player.stability_score) === 'down' ? 'text-down' : 'text-ink-faint'}`}>
                        {stabilityWord(player.stability_score)}
                      </p>
                    </td>
                    <td className="px-3 py-1"><Sparkline values={player.trend} /></td>
                    <td className="px-3 py-2.5 text-xs leading-relaxed text-ink-dim">
                      {plural(player.runs, 'run')}
                      {player.batting_balls > 0 && ` · strike rate ${fmt(player.strike_rate)}`}
                      {player.wickets > 0 && ` · ${plural(player.wickets, 'wicket')}`}
                      {player.bowling_balls > 0 && ` · ${oneDp(player.economy)} an over`}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => setOpen(open === player.player ? null : player.player)}
                        aria-expanded={open === player.player}
                        className="border border-line px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-ink-faint hover:border-[var(--accent)] hover:text-ink"
                      >
                        {open === player.player ? 'Hide' : 'Why'}
                      </button>
                    </td>
                  </tr>
                  {open === player.player && (
                    <tr className="border-b border-line bg-panel-2">
                      <td colSpan={5} className="px-3 py-4">
                        <div className="grid gap-4 md:grid-cols-2">
                          {player.components.map((component) => (
                            <div key={component.key}>
                              <div className="flex items-baseline justify-between gap-3">
                                <span className="text-xs text-ink-dim">{component.label}</span>
                                <span className="figure text-xs">
                                  {component.score ?? '—'} · {Math.round(component.weight * 100)}% of score
                                </span>
                              </div>
                              <div className="mt-1 h-[3px] w-full bg-line">
                                <div className="h-full" style={{
                                  width: `${component.score ?? 0}%`,
                                  background: 'var(--accent)',
                                }} />
                              </div>
                              <p className="mt-1 text-[11px] text-ink-faint">{component.detail}</p>
                            </div>
                          ))}
                        </div>
                        <p className="mt-3 border-t border-line pt-2 text-[11px] text-ink-faint">
                          Played {player.matches_played} of the season's matches ·{' '}
                          {confidenceText[player.confidence]} · read within ±{player.band} points
                        </p>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="What this season says" meta="every line comes from the deliveries">
        <div className="grid gap-px bg-line sm:grid-cols-2">
          {Object.entries(data.swot).map(([label, text]) => (
            <div key={label} className="bg-panel p-4">
              <p className="label" style={{ color: 'var(--accent)' }}>{label}</p>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-dim">{text}</p>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  )
}
