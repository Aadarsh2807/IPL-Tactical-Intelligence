/**
 * Shared primitives. No chart library and no icon library: a sparkline is ten
 * lines of SVG and an icon is one path, which is why the dependency list can
 * stay at React alone.
 */

export function Panel({ title, meta, children, className = '', dense = false }) {
  return (
    <section className={`border border-line bg-panel ${className}`}>
      {(title || meta) && (
        <header className="flex items-baseline justify-between gap-4 border-b border-line px-4 py-2.5">
          {title && <h2 className="label">{title}</h2>}
          {meta && <span className="label">{meta}</span>}
        </header>
      )}
      <div className={dense ? '' : 'p-4'}>{children}</div>
    </section>
  )
}

export function Metric({ label, value, unit, delta, hint }) {
  const sign = delta === undefined || delta === null ? null : delta >= 0 ? '+' : ''
  const tone = delta === undefined || delta === null
    ? ''
    : delta >= 0 ? 'text-up' : 'text-down'
  return (
    <div className="min-w-0">
      <p className="label">{label}</p>
      <p className="figure mt-1 text-2xl leading-none text-ink">
        {value ?? '—'}
        {unit && <span className="ml-0.5 text-sm text-ink-faint">{unit}</span>}
        {sign && <span className={`ml-1.5 text-sm ${tone}`}>{sign}{delta}</span>}
      </p>
      {hint && <p className="mt-1 text-xs text-ink-faint">{hint}</p>}
    </div>
  )
}

export function Meter({ label, value, max = 100, suffix = '' }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="label">{label}</span>
        <span className="figure text-xs text-ink-dim">{value}{suffix}</span>
      </div>
      <div className="mt-1 h-[3px] w-full bg-line">
        <div className="h-full" style={{ width: `${pct}%`, background: 'var(--accent)' }} />
      </div>
    </div>
  )
}

const TONE_CLASS = { up: 'text-up', down: 'text-down', flat: 'text-ink-dim' }

/**
 * A metric explained in words. The bar is a supporting cue only — the sentence
 * carries the meaning, so no bare index number is ever shown.
 */
export function PlainStat({ label, text, tone = 'flat', value, max = 100 }) {
  return (
    <div>
      <span className="label">{label}</span>
      <p className={`mt-0.5 text-sm ${TONE_CLASS[tone]}`}>{text}</p>
      {value !== undefined && (
        <div className="mt-1.5 h-[3px] w-full bg-line">
          <div className="h-full" style={{
            width: `${Math.max(0, Math.min(100, (value / max) * 100))}%`,
            background: 'var(--accent)',
          }} />
        </div>
      )}
    </div>
  )
}

/** One sentence, in plain English, at the top of every view. */
export function Takeaway({ title = 'In plain English', children }) {
  return (
    <div className="border-l-2 bg-panel-2 px-4 py-3" style={{ borderColor: 'var(--accent)' }}>
      <p className="label">{title}</p>
      <p className="mt-1.5 text-[15px] leading-relaxed text-ink">{children}</p>
    </div>
  )
}

export function Chip({ children, tone = 'neutral' }) {
  const tones = {
    neutral: 'border-line text-ink-faint',
    accent: 'border-transparent text-ink-dim',
    good: 'border-line text-up',
    bad: 'border-line text-down',
  }
  return (
    <span className={`inline-flex items-center gap-1 border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.12em] ${tones[tone]}`}
          style={tone === 'accent' ? { borderColor: 'var(--accent)', color: 'var(--accent)' } : undefined}>
      {children}
    </span>
  )
}

export function Sparkline({ values, width = 76, height = 20 }) {
  if (!values || values.length < 2) {
    return <span className="text-xs text-ink-faint" title="fewer than two matches recorded">—</span>
  }
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const step = width / (values.length - 1)
  const y = (value) => height - 2 - ((value - min) / span) * (height - 4)
  const points = values.map((value, index) => `${(index * step).toFixed(1)},${y(value).toFixed(1)}`).join(' ')
  const crossesZero = min <= 0 && max >= 0

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}
         role="img" aria-label={`trend across ${values.length} matches`}>
      {crossesZero && (
        <line x1="0" y1={y(0)} x2={width} y2={y(0)} stroke="#ffffff" strokeOpacity="0.22" strokeDasharray="2 2" />
      )}
      <polyline points={points} fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx={width} cy={y(values[values.length - 1])} r="2" fill="var(--accent)" />
    </svg>
  )
}

export function Loading({ rows = 4, label = 'Loading' }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <p className="label mb-3">{label}</p>
      <div className="space-y-2">
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="skeleton h-6 w-full" style={{ width: `${100 - index * 7}%` }} />
        ))}
      </div>
    </div>
  )
}

export function ErrorState({ message, onRetry }) {
  return (
    <div role="alert" className="border border-line bg-panel p-4">
      <p className="label text-down">Could not load</p>
      <p className="mt-1 text-sm text-ink-dim">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry}
                className="mt-3 border border-line px-3 py-1.5 text-xs uppercase tracking-[0.14em] text-ink-dim hover:border-[var(--accent)] hover:text-ink">
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, hint }) {
  return (
    <div className="border border-dashed border-line p-8 text-center">
      <p className="label">{title}</p>
      {hint && <p className="mx-auto mt-2 max-w-sm text-sm text-ink-faint">{hint}</p>}
    </div>
  )
}

export function Field({ id, label, children }) {
  return (
    <div>
      <label htmlFor={id} className="label">{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  )
}

export const selectClass =
  'w-full appearance-none border border-line bg-panel-2 px-3 py-2 text-sm text-ink hover:border-line-strong'

// ---------------------------------------------------------------------------
// Report primitives
// ---------------------------------------------------------------------------

/**
 * The masthead figure. One number, one word, and the scale it sits on, so
 * there is never a bare index floating in the layout asking to be explained.
 */
export function LeadFigure({ value, suffix, word, label, tone = 'flat' }) {
  const color = tone === 'good' ? 'var(--color-up)'
    : tone === 'bad' ? 'var(--color-down)'
      : 'var(--accent)'
  return (
    <div>
      {label && <p className="kicker" style={{ color: 'var(--accent)' }}>{label}</p>}
      <p className={`display-figure ${label ? 'mt-2' : ''}`} style={{ color }}>{value}</p>
      <div className="mt-2 flex items-baseline gap-2">
        <p className="display-sub">{word}</p>
        <p className="figure text-xs text-ink-faint">{suffix}</p>
      </div>
    </div>
  )
}

/**
 * How a score was made up. Each bar is the points a pillar actually added, with
 * the published ceiling drawn in behind it, so "the rest is not batting" is
 * visible rather than asserted.
 */
export function PillarBars({ items }) {
  const total = items.reduce((sum, item) => sum + item.ceiling, 0) || 1
  return (
    <ul className="space-y-2.5">
      {items.map((item) => (
        <li key={item.key}>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-xs text-ink-dim">{item.label}</span>
            <span className="figure text-xs">
              <span style={{ color: item.shortfall ? 'var(--color-ink)' : 'var(--accent)' }}>
                {item.points}
              </span>
              <span className="text-ink-faint"> / {item.ceiling}</span>
              {item.shortfall > 0 && (
                <span className="ml-2 text-ink-faint">{item.shortfall} short</span>
              )}
            </span>
          </div>
          <div className="relative mt-1 h-[5px] w-full bg-line">
            <div
              className="absolute inset-y-0 left-0 bg-line-strong"
              style={{ width: `${(item.ceiling / total) * 100}%` }}
            />
            <div
              className="absolute inset-y-0 left-0"
              style={{ width: `${(item.points / total) * 100}%`, background: 'var(--accent)' }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}

/** A section divider: serif title, kicker above, rule underneath. */
export function SectionTitle({ kicker, title, blurb, right }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-2 border-b border-line pb-3">
      <div className="min-w-0">
        {kicker && <p className="kicker" style={{ color: 'var(--accent)' }}>{kicker}</p>}
        <h3 className="display-title mt-1">{title}</h3>
        {blurb && <p className="mt-1 text-[11px] text-ink-faint">{blurb}</p>}
      </div>
      {right}
    </div>
  )
}

const INSIGHT_TONE = {
  good: 'var(--color-up)',
  bad: 'var(--color-down)',
  flat: 'var(--accent)',
}

/**
 * One insight: a judgement in serif, the evidence under it, and a visible
 * marker for which tool produced the facts. Tone colours the rule only, never
 * the body text, so meaning never depends on colour alone.
 */
export function InsightCard({ insight, wide = false, children }) {
  return (
    <article className="relative flex h-full flex-col border border-line bg-panel p-5">
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-[3px]"
        style={{ background: INSIGHT_TONE[insight.tone] ?? 'var(--accent)' }}
      />
      <div className="flex items-start justify-between gap-3">
        <p className="kicker" style={{ color: 'var(--accent)' }}>{insight.kicker}</p>
        <span className="label shrink-0">{insight.source}</span>
      </div>
      <h4 className={`card-title mt-2 ${wide ? 'max-w-[40ch]' : ''}`}>{insight.title}</h4>
      <p className={`copy mt-2.5 ${wide ? 'max-w-[78ch]' : ''}`}>{insight.body}</p>
      {children}
    </article>
  )
}

/** The names behind a figure: role, a number, and how much to trust it. */
export function PeopleStrip({ people }) {
  return (
    <ul className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-3">
      {people.map((person) => (
        <li key={person.name} className="bg-panel px-4 py-3">
          <p className="truncate font-display text-[15px] text-ink">{person.name}</p>
          <p className="label mt-0.5">{person.role}</p>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="figure text-xl leading-none" style={{ color: 'var(--accent)' }}>
              {person.stat}
            </span>
            {person.caption && <span className="text-[11px] text-ink-faint">{person.caption}</span>}
          </div>
        </li>
      ))}
    </ul>
  )
}

/** The raw sentence-by-sentence audit trail, set as a numbered list in mono. */
export function NarrativeList({ narrative }) {
  return (
    <ol className="divide-y divide-line border border-line">
      {narrative.map((sentence, index) => (
        <li key={index} className="flex gap-3 px-4 py-2.5">
          <span className="figure w-6 shrink-0 text-[11px] text-ink-faint">
            {String(index + 1).padStart(2, '0')}
          </span>
          <p className="flex-1 text-[13px] leading-relaxed text-ink-dim">{sentence.text}</p>
          <span className="label shrink-0 self-start pt-0.5">{sentence.source}</span>
        </li>
      ))}
    </ol>
  )
}
