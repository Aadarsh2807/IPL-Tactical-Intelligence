/**
 * Turning numbers into sentences.
 *
 * The API keeps full precision on purpose — the tests and the SQL viewer need
 * it. This file is the translation layer the reader actually sees: whole
 * numbers, percentages, and plain words for anything that would otherwise be
 * an unexplained decimal.
 */

/** Whole numbers by default. Decimals are noise unless they change meaning. */
export const fmt = (value, digits = 0) => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return Number(value).toFixed(digits)
}

export const pct = (value, digits = 0) =>
  value === null || value === undefined ? '—' : `${fmt(value * 100, digits)}%`

/** One decimal, but never a pointless trailing ".0". */
export const oneDp = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return String(Number(value.toFixed(1)))
}

export const plural = (count, singular, pluralForm = `${singular}s`) =>
  `${count} ${count === 1 ? singular : pluralForm}`

/**
 * An index where 1.00 means "exactly the league average".
 * Returns a sentence a newcomer can act on, not a ratio.
 */
export const describeIndex = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return { text: 'No data this season', tone: 'flat', delta: null }
  }
  const delta = Math.round((value - 1) * 100)
  if (Math.abs(delta) < 2) return { text: 'Level with the league', tone: 'flat', delta: 0 }
  if (delta >= 2) {
    return {
      text: `${delta}% ${delta >= 12 ? 'well ' : ''}above the league average`,
      tone: 'up',
      delta,
    }
  }
  return {
    text: `${Math.abs(delta)}% ${delta <= -12 ? 'well ' : ''}below the league average`,
    tone: 'down',
    delta,
  }
}

/** Stability is an index where 50 is the league standard for that role. */
export const stabilityWord = (score) => {
  if (score >= 70) return 'Very reliable'
  if (score >= 60) return 'Reliable'
  if (score >= 50) return 'Steady'
  if (score >= 40) return 'Unsteady'
  return 'Highly variable'
}

export const stabilityTone = (score) => {
  if (score >= 60) return 'up'
  if (score >= 50) return 'flat'
  return 'down'
}

export const confidenceText = {
  High: 'Full-season sample',
  Medium: 'Part-season sample',
  Low: 'Small sample — read with care',
}

/** Mirrors analytics.role_mix_comment() so the two never drift apart. */
export const roleMixComment = (counts = {}) => {
  const batters = counts.Batter ?? 0
  const allRounders = counts['All-rounder'] ?? 0
  const bowlers = counts.Bowler ?? 0
  if (bowlers < 4) return 'short on bowling'
  if (batters < 5) return 'short on batting'
  if (batters >= 6 && bowlers >= 5 && allRounders >= 1) return 'well balanced'
  return 'adequate'
}

export const squadWord = (score) => {
  if (score >= 80) return 'Strong season'
  if (score >= 70) return 'Solid season'
  if (score >= 60) return 'Average season'
  if (score >= 50) return 'Below average'
  return 'Difficult season'
}

export const xiWord = (score) => {
  if (score >= 80) return 'A strong eleven'
  if (score >= 70) return 'A solid eleven'
  if (score >= 60) return 'A workable eleven'
  return 'A fragile eleven'
}

export const outlookWord = (probability) => {
  if (probability >= 65) return 'Favourable'
  if (probability >= 55) return 'Slightly favourable'
  if (probability >= 45) return 'Around even'
  if (probability >= 35) return 'Slightly unfavourable'
  return 'Unfavourable'
}

/** One sentence for the matchup card, in the order a fan would say it. */
export const matchupSentence = (data) => {
  if (!data) return ''
  const dismissed = data.dismissals === 1 ? 'dismissed once' : `dismissed ${data.dismissals} times`
  return `${data.batter} scored ${data.runs} runs from ${data.balls} balls against ` +
         `${data.bowler}, who ${dismissed} in ${data.matches} ` +
         `${data.matches === 1 ? 'match' : 'matches'}.`
}
