import { useEffect, useState } from 'react'
import { useResource, encode } from '../lib/api'
import { Panel, Metric, Meter, Chip, Loading, ErrorState, EmptyState, Field, Takeaway, selectClass } from './ui'
import { matchupSentence, fmt, oneDp } from '../lib/format'

const EVIDENCE_ORDER = { Limited: 0, Medium: 1, High: 2 }

export default function Matchups({ season }) {
  const [batter, setBatter] = useState('')
  const [bowler, setBowler] = useState('')

  const { data: batters } = useResource(`/api/batters?season=${encode(season)}`)
  const { data: bowlers } = useResource(
    batter ? `/api/matchup/bowlers?season=${encode(season)}&batter=${encode(batter)}` : '',
  )
  const { data, error, loading } = useResource(
    batter && bowler
      ? `/api/matchup?season=${encode(season)}&batter=${encode(batter)}&bowler=${encode(bowler)}`
      : '',
  )

  useEffect(() => {
    if (batters?.length && !batter) setBatter(batters[0])
  }, [batters, batter])
  useEffect(() => {
    if (bowlers?.length) setBowler(bowlers[0])
    else setBowler('')
  }, [bowlers])

  return (
    <div className="space-y-4">
      <Panel
        title="Head-to-head"
        meta={`${season} · league-wide recorded pairs`}
      >
        <div className="grid gap-3 md:grid-cols-2">
          <Field id="batter" label="Batter">
            <select id="batter" value={batter} onChange={(e) => setBatter(e.target.value)} className={selectClass}>
              {(batters ?? []).map((name) => <option key={name}>{name}</option>)}
            </select>
          </Field>
          <Field id="bowler" label="Bowler">
            <select id="bowler" value={bowler} onChange={(e) => setBowler(e.target.value)} className={selectClass}>
              {(bowlers ?? []).map((name) => <option key={name}>{name}</option>)}
            </select>
          </Field>
        </div>
        <p className="mt-3 text-xs text-ink-faint">
          The batter list is every batter with recorded deliveries in {season}, and the
          bowler list is only opponents who actually bowled to that batter — a matchup is
          never invented by intersecting two name lists.
        </p>
      </Panel>

      {error && <ErrorState message={error} />}
      {loading && <Loading rows={3} label="Reading recorded deliveries" />}

      {!loading && !data && (
        <EmptyState title="No pair selected" hint="Choose a batter whose season has recorded opponents." />
      )}

      {data && (
        <>
          <Takeaway>{matchupSentence(data)}</Takeaway>

          <Panel
            title={`${data.batter} vs ${data.bowler}`}
            meta={data.evidence_note}
          >
            <div className="flex flex-wrap items-center gap-2">
              <Chip tone="accent">{data.evidence} evidence</Chip>
              <span className="label">{data.matches} matches · {data.balls} balls</span>
            </div>

            <div className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
              <Metric label="Runs scored" value={fmt(data.runs)} />
              <Metric label="Times dismissed" value={fmt(data.dismissals)} />
              <Metric label="Runs per 100 balls" value={fmt(data.strike_rate)} />
              <Metric label="Runs this bowler gave away per over" value={oneDp(data.bowler_economy)} />
            </div>

            <div className="mt-6">
              <Meter
                label="How much we know about this matchup"
                value={Math.min(data.balls, 60)}
                max={60}
                suffix=" balls · 30+ counts as strong evidence"
              />
            </div>

            <p className="mt-4 border-t border-line pt-3 text-xs text-ink-faint">
              Evidence tier {EVIDENCE_ORDER[data.evidence]} of 3 is derived only from balls
              faced, so a small sample is never dressed up as a pattern.
            </p>
          </Panel>
        </>
      )}
    </div>
  )
}
