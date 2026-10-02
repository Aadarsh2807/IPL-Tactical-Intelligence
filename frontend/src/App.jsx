import { useEffect, useState } from 'react'
import { useResource, encode } from './lib/api'
import { livery } from './theme/teams'
import Squad from './components/Squad'
import Matchups from './components/Matchups'
import Outlook from './components/Outlook'
import XIBuilder from './components/XIBuilder'
import ReportPanel from './components/ReportPanel'
import { Field, selectClass } from './components/ui'

const TABS = [
  { id: 'squad', label: 'Squad', hint: 'stability + SWOT' },
  { id: 'xi', label: 'XI builder', hint: 'select + solve' },
  { id: 'matchups', label: 'Matchups', hint: 'recorded pairs only' },
  { id: 'outlook', label: 'Outlook', hint: 'bounded estimate' },
  { id: 'report', label: 'Report', hint: 'agent harness' },
]

const ICONS = {
  squad: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  xi: 'M4 5h16M4 10h16M4 15h10M4 20h7',
  matchups: 'M12 3v18M3 12h18M12 7a5 5 0 100 10 5 5 0 100-10',
  outlook: 'M3 20h18M4 16l5-6 4 3 7-8',
  report: 'M6 3h8l4 4v14H6zM14 3v4h4',
}

function Icon({ name }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"
         stroke="currentColor" strokeWidth="1.5" strokeLinecap="square">
      <path d={ICONS[name]} />
    </svg>
  )
}

export default function App() {
  const [season, setSeason] = useState('')
  const [team, setTeam] = useState('')
  const [tab, setTab] = useState('squad')

  const { data: seasons } = useResource('/api/seasons')
  const { data: teams } = useResource(season ? `/api/teams?season=${encode(season)}` : '')
  const { data: health } = useResource('/api/health')

  useEffect(() => {
    if (seasons?.length && !season) setSeason(seasons[0])
  }, [seasons, season])
  useEffect(() => {
    if (teams?.length) setTeam((current) => (teams.includes(current) ? current : teams[0]))
  }, [teams])

  // The whole interface adopts the selected team's livery colour.
  const { accent, ink } = livery(team)

  return (
    <div
      className="glow-edges relative z-10 min-h-screen bg-pit text-ink"
      style={{ '--accent': accent, '--accent-ink': ink }}
    >
      {/* Timing strip: brand, context, and the two selectors that drive every view */}
      <header className="sticky top-0 z-20 border-b border-line bg-pit/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-end gap-x-8 gap-y-3 px-5 py-3">
          <div className="mr-auto">
            <p className="figure text-sm uppercase tracking-[0.28em]">IPL Tactical</p>
            <p className="label mt-0.5">ball-by-ball intelligence · evidence only</p>
          </div>

          <div className="w-28">
            <Field id="season" label="Season">
              <select id="season" value={season} onChange={(e) => setSeason(e.target.value)} className={selectClass}>
                {(seasons ?? []).map((year) => <option key={year}>{year}</option>)}
              </select>
            </Field>
          </div>
          <div className="w-56">
            <Field id="team" label="Team">
              <select id="team" value={team} onChange={(e) => setTeam(e.target.value)} className={selectClass}>
                {(teams ?? []).map((name) => <option key={name}>{name}</option>)}
              </select>
            </Field>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1400px] flex-col gap-6 px-5 py-6 lg:flex-row">
        {/* Feature rail */}
        <nav aria-label="Views" className="lg:w-52 lg:shrink-0">
          <ul className="flex gap-1 overflow-x-auto lg:flex-col">
            {TABS.map((item) => {
              const active = tab === item.id
              return (
                <li key={item.id} className="lg:w-full">
                  <button
                    type="button"
                    onClick={() => setTab(item.id)}
                    aria-current={active ? 'page' : undefined}
                    className={`flex w-full items-center gap-3 border px-3 py-2 text-left transition-colors ${
                      active ? 'bg-panel-2' : 'border-transparent hover:bg-panel'
                    }`}
                    style={active ? { borderColor: 'var(--accent)' } : undefined}
                  >
                    <span style={{ color: active ? 'var(--accent)' : '#636e78' }}>
                      <Icon name={item.id} />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm">{item.label}</span>
                      <span className="label">{item.hint}</span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </nav>

        <main className="min-w-0 flex-1">
          {season && team ? (
            <>
              {tab === 'squad' && <Squad season={season} team={team} />}
              {tab === 'xi' && <XIBuilder season={season} team={team} />}
              {tab === 'matchups' && <Matchups season={season} />}
              {tab === 'outlook' && <Outlook season={season} team={team} />}
              {tab === 'report' && <ReportPanel season={season} team={team} />}
            </>
          ) : (
            <p className="label">Loading dataset context…</p>
          )}
        </main>
      </div>

      {/* Provenance is shown, not buried: every figure above depends on it */}
      {health?.provenance && (
        <footer className="border-t border-line">
          <div className="mx-auto grid max-w-[1400px] gap-x-8 gap-y-1 px-5 py-4 text-[11px] text-ink-faint md:grid-cols-2 lg:grid-cols-4">
            <span>
              <span className="label">Engine</span> {health.provenance.engine} ·{' '}
              {health.provenance.deliveries_rows.toLocaleString()} deliveries ·{' '}
              {health.provenance.matches_rows.toLocaleString()} matches
            </span>
            <span>
              <span className="label">Legal balls</span> {health.provenance.legal_balls}
            </span>
            <span>
              <span className="label">Bowler runs</span> {health.provenance.bowler_runs}
            </span>
            <span>
              <span className="label">Scope</span> {health.provenance.super_overs}
            </span>
          </div>
        </footer>
      )}
    </div>
  )
}
