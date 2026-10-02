import { useEffect, useMemo, useState } from 'react'
import { useResource, post, encode } from '../lib/api'
import { Panel, Chip, Loading, ErrorState, EmptyState, Sparkline, PlainStat } from './ui'
import { xiWord, stabilityWord, roleMixComment } from '../lib/format'

export default function XIBuilder({ season, team }) {
  const [selection, setSelection] = useState([])
  const [scored, setScored] = useState(null)
  const [best, setBest] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const { data: squad, loading, error: loadError } = useResource(
    season && team ? `/api/squad/${encode(team)}?season=${encode(season)}` : '',
  )

  const chosen = useMemo(
    () => squad?.players.filter((player) => selection.includes(player.player)) ?? [],
    [squad, selection],
  )

  // Live re-score of the current selection. Cancelled on every change so a
  // fast click sequence cannot land out of order.
  useEffect(() => {
    if (!squad || selection.length === 0) {
      setScored(null)
      return undefined
    }
    const controller = new AbortController()
    post('/api/xi', { season, team, players: selection }, { signal: controller.signal })
      .then(setScored)
      .catch((err) => { if (err.name !== 'AbortError') setError(err.message) })
    return () => controller.abort()
  }, [selection, squad, season, team])

  function toggle(player) {
    setError('')
    setSelection((current) => current.includes(player)
      ? current.filter((name) => name !== player)
      : current.length < 11 ? [...current, player] : current)
  }

  async function loadBestXI() {
    setBusy(true)
    setError('')
    try {
      const result = await post('/api/xi/auto', { season, team, players: [] })
      setBest(result)
      setSelection(result.players)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <Loading rows={5} label={`Loading ${team} ${season} squad`} />
  if (loadError) return <ErrorState message={loadError} />
  if (!squad) return <EmptyState title="No squad" hint="Pick a season and a team." />

  const breakdown = scored?.breakdown
  const delta = breakdown && best?.breakdown ? breakdown.score - best.breakdown.score : null
  const constraints = [
    { label: 'Exactly 11', met: selection.length === 11 },
    { label: 'At least 5 batters', met: (breakdown?.role_counts.Batter ?? 0) >= 5 },
    { label: 'At least 4 bowlers', met: (breakdown?.role_counts.Bowler ?? 0) >= 4 },
    { label: 'At least 1 all-rounder', met: (breakdown?.role_counts['All-rounder'] ?? 0) >= 1 },
  ]

  return (
    <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
      <Panel
        title="Squad"
        meta={`${selection.length}/11 selected`}
        dense
      >
        <div className="flex flex-wrap gap-2 border-b border-line p-3">
          <button type="button" onClick={loadBestXI} disabled={busy}
                  className="border border-line px-3 py-1.5 text-xs uppercase tracking-[0.14em] text-ink-dim hover:border-[var(--accent)] hover:text-ink disabled:opacity-50">
            {busy ? 'Solving…' : 'Best XI'}
          </button>
          <button type="button" onClick={() => setSelection([])}
                  className="border border-line px-3 py-1.5 text-xs uppercase tracking-[0.14em] text-ink-dim hover:border-line-strong hover:text-ink">
            Clear
          </button>
          <span className="label ml-auto self-center">solver enumerates role splits · no randomness</span>
        </div>

        <ul className="max-h-[560px] overflow-y-auto">
          {squad.players.map((player) => {
            const active = selection.includes(player.player)
            return (
              <li key={player.player}>
                <button
                  type="button"
                  onClick={() => toggle(player.player)}
                  aria-pressed={active}
                  className={`flex w-full items-center gap-3 border-b border-line px-3 py-2 text-left transition-colors ${
                    active ? 'bg-panel-2' : 'hover:bg-panel-2/60'
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className="h-3 w-3 shrink-0 border"
                    style={active
                      ? { background: 'var(--accent)', borderColor: 'var(--accent)' }
                      : { borderColor: '#2f3940' }}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm">{player.player}</span>
                    <span className="label">{player.role} · {player.matches_played}m · {player.sample_balls} balls</span>
                  </span>
                  <Sparkline values={player.trend} width={54} height={16} />
                  <span className="figure w-8 text-right text-sm">{player.stability_score}</span>
                </button>
              </li>
            )
          })}
        </ul>
      </Panel>

      <div className="space-y-4">
        <Panel title="XI scoreboard" meta={breakdown?.method ?? 'select up to 11 players'}>
          {breakdown ? (
            <>
              <div className="flex items-end gap-4">
                <p className="figure text-6xl leading-none" style={{ color: 'var(--accent)' }}>
                  {breakdown.score}
                </p>
                <div className="pb-1">
                  <p className="text-sm text-ink-dim">{xiWord(breakdown.score)}</p>
                  {delta !== null && (
                    <p className={`figure text-xs ${delta >= 0 ? 'text-up' : 'text-down'}`}>
                      {delta === 0
                        ? 'matches the solver\'s best XI'
                        : `${delta > 0 ? '+' : ''}${delta} vs the solver's best XI`}
                    </p>
                  )}
                </div>
              </div>

              <div className="mt-6 grid gap-4">
                <PlainStat
                  label="Player quality"
                  text={`${stabilityWord(breakdown.quality)} on average`}
                  tone={breakdown.quality >= 55 ? 'up' : breakdown.quality >= 45 ? 'flat' : 'down'}
                  value={breakdown.quality}
                />
                <PlainStat
                  label="Role mix"
                  text={roleMixComment(breakdown.role_counts)}
                  tone={['short on bowling', 'short on batting'].includes(roleMixComment(breakdown.role_counts)) ? 'down' : 'up'}
                  value={breakdown.role_balance}
                />
                <PlainStat
                  label="Squad depth"
                  text={`${breakdown.batting_depth} batters and ${breakdown.bowling_depth} bowlers with a full workload`}
                  value={breakdown.depth}
                />
              </div>

              <div className="mt-6 grid gap-px border border-line bg-line sm:grid-cols-2">
                {constraints.map((rule) => (
                  <div key={rule.label} className="flex items-center gap-2 bg-panel px-3 py-2">
                    <span aria-hidden="true" className={rule.met ? 'text-up' : 'text-down'}>
                      {rule.met ? '✓' : '✕'}
                    </span>
                    <span className="text-xs text-ink-dim">{rule.label}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <EmptyState
              title="No score yet"
              hint="Pick players, or press Best XI to let the solver propose a legal side."
            />
          )}

          {breakdown && (
            <p className="mt-5 border-t border-line pt-3 text-xs leading-relaxed text-ink-faint">
              Out of 100, where 50 is an average side. Scoring is mostly player reliability,
              then a legal mix of roles, then how much depth the eleven actually carries.
            </p>
          )}

          {scored && !scored.valid && (
            <ul className="mt-4 space-y-1 border-t border-line pt-3">
              {scored.violations.map((violation) => (
                <li key={violation} className="text-xs text-down">— {violation}</li>
              ))}
            </ul>
          )}
          {error && <p className="mt-3 text-xs text-down">{error}</p>}
        </Panel>

        <Panel title="Selection" meta={`${chosen.length} players`} dense>
          {chosen.length === 0 ? (
            <p className="p-4 text-sm text-ink-faint">Nothing selected yet.</p>
          ) : (
            <ul>
              {chosen.map((player) => (
                <li key={player.player} className="flex items-center gap-3 border-b border-line px-3 py-2">
                  <span className="flex-1 truncate text-sm">{player.player}</span>
                  <Chip>{player.role}</Chip>
                  <span className="figure w-8 text-right text-sm">{player.stability_score}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  )
}
