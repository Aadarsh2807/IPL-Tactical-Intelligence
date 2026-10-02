/**
 * Team livery colours.
 *
 * This is the ONE file in the frontend where a team name is written down, and
 * it is presentation only: no calculation ever reads it. `backend/tests/
 * test_no_hardcoded.py` enforces that rule mechanically.
 *
 * Values are the clubs' real brand colours. Anything missing falls back to a
 * neutral graphite so a renamed or historic franchise never breaks the UI.
 */
export const DEFAULT_ACCENT = { accent: '#7c8894', ink: '#0b0d0f' }

export const TEAM_ACCENTS = {
  'Chennai Super Kings': { accent: '#f9c22e', ink: '#14100a' },
  'Mumbai Indians': { accent: '#1b4ea8', ink: '#f4f7fb' },
  'Kolkata Knight Riders': { accent: '#6c3fa0', ink: '#f6f2fb' },
  'Royal Challengers Bengaluru': { accent: '#d61f2c', ink: '#fdf3f4' },
  'Sunrisers Hyderabad': { accent: '#f26522', ink: '#160c04' },
  'Rajasthan Royals': { accent: '#d81b60', ink: '#fdf1f6' },
  'Delhi Capitals': { accent: '#0e6bc4', ink: '#f2f7fd' },
  'Punjab Kings': { accent: '#c8102e', ink: '#fdf3f4' },
  'Lucknow Super Giants': { accent: '#00a3e0', ink: '#04212c' },
  'Gujarat Titans': { accent: '#16324f', ink: '#eef3f8' },
  'Deccan Chargers': { accent: '#c8a24a', ink: '#150f04' },
  'Kochi Tuskers Kerala': { accent: '#4c9f70', ink: '#f2faf5' },
  'Pune Warriors': { accent: '#6a1b3a', ink: '#fbf1f5' },
  'Gujarat Lions': { accent: '#c05621', ink: '#150a04' },
  'Rising Pune Supergiants': { accent: '#d7263d', ink: '#fdf2f3' },
}

export function livery(team) {
  return TEAM_ACCENTS[team] ?? DEFAULT_ACCENT
}
