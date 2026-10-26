// Formatting helpers. All times are shown in UK local time, like the trading desk sees them.
const UK = 'Europe/London'

const dateTimeFmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: UK, day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false,
})
const dayFmt = new Intl.DateTimeFormat('en-GB', { timeZone: UK, day: '2-digit', month: 'short' })

export const fmtDateTime = (epoch) => dateTimeFmt.format(new Date(epoch * 1000))
export const fmtDay = (epoch) => dayFmt.format(new Date(epoch * 1000))
export const fmtIsoDay = (iso) => dayFmt.format(new Date(`${iso}T12:00:00Z`))

export const fmtMW = (v, digits = 0) =>
  v == null || Number.isNaN(v) ? '–' : `${Math.round(v).toLocaleString('en-GB', { maximumFractionDigits: digits })} MW`

export const fmtGW = (v) => (v == null ? '–' : `${(v / 1000).toFixed(1)} GW`)

export const fmtSignedMW = (v) =>
  v == null ? '–' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Math.round(v)).toLocaleString('en-GB')} MW`

export const fmtPct = (v, digits = 1) => (v == null ? '–' : `${v.toFixed(digits)}%`)

export const pad2 = (n) => String(n).padStart(2, '0')

// "Nice" axis ticks: round numbers like 0, 2000, 4000 …
export function niceTicks(min, max, count = 5) {
  if (min === max) { min -= 1; max += 1 }
  const raw = (max - min) / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)
  const start = Math.floor(min / step) * step
  const ticks = []
  for (let v = start; v <= max + step * 0.5; v += step) ticks.push(Math.round(v * 1e6) / 1e6)
  return ticks
}
