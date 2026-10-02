import { useResource, encode } from '../lib/api'
import { describeIndex, outlookWord, fmt } from '../lib/format'
import { Panel, PlainStat, Takeaway, Loading, ErrorState, EmptyState } from './ui'

export default function Outlook({ season, team }) {
  const { data, error, loading } = useResource(
    season && team ? `/api/season-outlook/${encode(team)}?season=${encode(season)}` : '',
  )

  if (loading) return <Loading rows={4} label={`Aggregating ${team} ${season}`} />
  if (error) return <ErrorState message={error} />
  if (!data) return <EmptyState title="No outlook" hint="Pick a season and a team." />

  const batting = describeIndex(data.attack_index)
  const bowling = describeIndex(data.defence_index)
  const won = data.wins === 1 ? 'one win' : `${data.wins} wins`
  const decided = data.decided_matches === 1 ? 'one decided match' : `${data.decided_matches} decided matches`

  return (
    <div className="space-y-4">
      <Takeaway title="In plain English">
        Based on the {season} season alone, {team} would start the next match at about{' '}
        <strong>{data.next_match_win_probability}%</strong> — {outlookWord(data.next_match_win_probability).toLowerCase()}.
        They {batting.text.toLowerCase()} with the bat and {bowling.text.toLowerCase()} with
        the ball, and won {won} in {decided}.
      </Takeaway>

      <Panel title="Next-match estimate" meta="historical estimate · not a live probability">
        <div className="grid gap-6 md:grid-cols-[auto_1fr]">
          <div>
            <p className="figure text-7xl leading-none" style={{ color: 'var(--accent)' }}>
              {data.next_match_win_probability}
              <span className="ml-1 text-2xl text-ink-faint">%</span>
            </p>
            <p className="mt-1.5 text-sm text-ink-dim">{outlookWord(data.next_match_win_probability)}</p>
            <p className="label mt-2">
              {data.next_match_win_probability === 50
                ? 'exactly a coin toss'
                : `${Math.abs(data.next_match_win_probability - 50)} point${
                  Math.abs(data.next_match_win_probability - 50) === 1 ? '' : 's'} ${
                  data.next_match_win_probability > 50 ? 'above' : 'below'} even odds`}
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <PlainStat
              label="Scoring"
              text={batting.text}
              tone={batting.tone}
              value={Math.round((data.attack_index / 1.3) * 100)}
            />
            <PlainStat
              label="Conceding runs"
              text={bowling.text}
              tone={bowling.tone}
              value={Math.round((data.defence_index / 1.3) * 100)}
            />
            <PlainStat
              label="Matches won"
              text={`${won} in ${decided}`}
              tone={data.win_rate >= 50 ? 'up' : 'down'}
              value={data.win_rate}
            />
          </div>
        </div>

        <div className="mt-6 grid gap-5 border-t border-line pt-5 sm:grid-cols-3 lg:grid-cols-6">
          {[
            ['Matches played', fmt(data.matches)],
            ['Matches decided', fmt(data.decided_matches)],
            ['Won', fmt(data.wins)],
            ['Runs scored', fmt(data.average_score)],
            ['Runs conceded', fmt(data.average_conceded)],
            ['League average', fmt(data.league_average)],
          ].map(([label, value]) => (
            <div key={label}>
              <p className="label">{label}</p>
              <p className="figure mt-1 text-xl">{value}</p>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="How this is worked out">
        <p className="text-sm leading-relaxed text-ink-dim">{data.method}</p>
        <p className="mt-4 border-t border-line pt-3 text-xs leading-relaxed text-ink-faint">
          <strong className="text-ink-dim">What this cannot tell you:</strong>{' '}
          {data.limitation}
        </p>
      </Panel>
    </div>
  )
}
