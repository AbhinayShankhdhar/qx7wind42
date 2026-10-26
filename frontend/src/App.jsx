import { useEffect, useMemo, useState } from 'react'
import { fetchAnalysis, fetchMeta } from './api.js'
import { BarChart, TimeSeriesChart } from './components/charts.jsx'
import { fmtIsoDay, fmtMW, fmtPct, fmtSignedMW, pad2 } from './format.js'

const CUTOFF_OPTIONS = Array.from({ length: 48 }, (_, i) => ({ h: Math.floor(i / 2), m: (i % 2) * 30 }))

function addDays(iso, n) {
  const d = new Date(`${iso}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

// Turn the numbers into plain-English findings for the trading team.
function buildInsights(res) {
  const m = res.metrics
  if (!m?.n) return []
  const out = []
  const cutoff = `${pad2(res.params.cutoff_hour)}:${pad2(res.params.cutoff_minute)}`
  out.push(`With the forecast available at ${cutoff} on the day before delivery, the typical miss was ${fmtMW(m.mae)} (${fmtPct(m.nmae_pct)} of average wind output).`)
  const biasShare = Math.abs(m.bias) / m.mean_actual
  out.push(biasShare < 0.02
    ? 'There is no meaningful systematic bias: over- and under-forecasts roughly cancel out.'
    : `Forecasts were systematically ${m.bias > 0 ? 'too high' : 'too low'} by ${fmtMW(Math.abs(m.bias))} on average, so ${m.bias > 0 ? 'less wind than expected arrived' : 'more wind than expected arrived'}.`)
  out.push(`Holding a buffer of ${fmtMW(m.shortfall_p90)} would have covered the wind shortfall in 90% of periods (${fmtMW(m.shortfall_p95)} for 95%).`)
  const hz = res.by_horizon.filter((b) => b.mae != null)
  if (hz.length > 2) {
    const first = hz[0], last = hz[hz.length - 1]
    out.push(`Accuracy depends strongly on lead time: forecasts made ${first.from_h}–${first.to_h} h ahead missed by ${fmtMW(first.mae)}, versus ${fmtMW(last.mae)} at ${last.from_h}–${last.to_h} h ahead.`)
  }
  const worst = [...res.daily].sort((a, b) => b.mae - a.mae)[0]
  if (worst && res.daily.length > 1) out.push(`The hardest day was ${fmtIsoDay(worst.day)}, with an average miss of ${fmtMW(worst.mae)}.`)
  return out
}

function downloadCsv(res) {
  const header = 'target_time_utc,forecast_published_utc,horizon_hours,forecast_mw,actual_mw,error_mw'
  const lines = res.series.map((r) => [
    new Date(r.start * 1000).toISOString(), new Date(r.publish * 1000).toISOString(),
    r.horizon_h, r.forecast, r.actual, r.error.toFixed(1),
  ].join(','))
  const blob = new Blob([[header, ...lines].join('\n')], { type: 'text/csv' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `wind_forecast_vs_actual_${res.params.start}_${res.params.end}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}

function Kpi({ label, value, sub, hint }) {
  return (
    <div className="kpi" title={hint}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  )
}

export default function App() {
  const [meta, setMeta] = useState(null)
  const [params, setParams] = useState(null)
  const [res, setRes] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // 1) Load metadata once, then initialise the controls from it.
  useEffect(() => {
    fetchMeta()
      .then((m) => {
        setMeta(m)
        setParams({
          start: m.delivery_window[0], end: m.delivery_window[1],
          cutoffHour: m.default_cutoff.hour, cutoffMinute: m.default_cutoff.minute,
        })
      })
      .catch((e) => setError(e.message))
  }, [])

  // 2) Re-run the analysis whenever a control changes.
  useEffect(() => {
    if (!params) return
    let cancelled = false
    setLoading(true)
    fetchAnalysis(params)
      .then((r) => { if (!cancelled) { setRes(r); setError(null) } })
      .catch((e) => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [params])

  const insights = useMemo(() => (res ? buildInsights(res) : []), [res])
  const set = (patch) => setParams((p) => ({ ...p, ...patch }))

  const [minDay, maxDay] = meta?.delivery_window ?? ['', '']
  const m = res?.metrics
  const singleDay = params && params.start === params.end

  return (
    <div className="page">
      <header className="masthead">
        <div>
          <div className="brand"><span className="brand-mark" aria-hidden="true" />WindCast</div>
          <h1>Day-ahead wind forecast desk</h1>
          <p className="lede">
            What GB national wind forecast did the desk have when it bought day-ahead power, and how far
            off was it? Purchase decisions made in January 2026, using Elexon BMRS data.
          </p>
        </div>
        {meta && (
          <div className="stamp">
            <div>Delivery days <b>{fmtIsoDay(minDay)} – {fmtIsoDay(maxDay)}</b></div>
            <div>Data: Elexon FUELHH (actual) &amp; WINDFOR (forecast)</div>
            {meta.data.fetched_at && <div>Snapshot {meta.data.fetched_at.slice(0, 10)}</div>}
          </div>
        )}
      </header>

      {params && (
        <section className="controls" aria-label="Analysis settings">
          <label>
            <span>Delivery from</span>
            <input type="date" value={params.start} min={minDay} max={params.end}
              onChange={(e) => e.target.value && set({ start: e.target.value })} />
          </label>
          <label>
            <span>to</span>
            <input type="date" value={params.end} min={params.start} max={maxDay}
              onChange={(e) => e.target.value && set({ end: e.target.value })} />
          </label>
          <label>
            <span>Decision time (day before, UK)</span>
            <select value={`${params.cutoffHour}:${params.cutoffMinute}`}
              onChange={(e) => { const [h, mi] = e.target.value.split(':').map(Number); set({ cutoffHour: h, cutoffMinute: mi }) }}>
              {CUTOFF_OPTIONS.map(({ h, m: mi }) => (
                <option key={`${h}:${mi}`} value={`${h}:${mi}`}>{pad2(h)}:{pad2(mi)}</option>
              ))}
            </select>
          </label>
          <div className="presets">
            <button className={!singleDay && params.start === minDay && params.end === maxDay ? 'active' : ''}
              onClick={() => set({ start: minDay, end: maxDay })}>Full month</button>
            <button onClick={() => set({ start: params.start, end: params.start })} className={singleDay ? 'active' : ''}>Single day</button>
            {singleDay && <>
              <button aria-label="Previous day" disabled={params.start <= minDay}
                onClick={() => { const d = addDays(params.start, -1); set({ start: d, end: d }) }}>‹</button>
              <button aria-label="Next day" disabled={params.start >= maxDay}
                onClick={() => { const d = addDays(params.start, 1); set({ start: d, end: d }) }}>›</button>
            </>}
          </div>
          {loading && <span className="loading" role="status">Updating…</span>}
        </section>
      )}

      {error && <div className="error" role="alert">Could not load data: {error}</div>}
      {!res && !error && <div className="loading-block">Loading wind data…</div>}

      {res && m?.n > 0 && (
        <main className={loading ? 'is-loading' : ''}>
          <section className="kpis">
            <Kpi label="Typical miss (MAE)" value={fmtMW(m.mae)} sub={`${fmtPct(m.nmae_pct)} of average output`}
              hint="Mean absolute error: average size of the gap between forecast and actual" />
            <Kpi label="Systematic bias" value={fmtSignedMW(m.bias)} sub={`Forecast too high in ${fmtPct(m.over_forecast_share_pct, 0)} of periods`}
              hint="Average of forecast minus actual. Positive = forecasts were too optimistic" />
            <Kpi label="Shortfall buffer (P90)" value={fmtMW(m.shortfall_p90)} sub={`P95: ${fmtMW(m.shortfall_p95)}`}
              hint="In 90% of periods, actual wind was at most this far below the forecast" />
            <Kpi label="Worst single miss" value={fmtMW(m.max_abs)} sub={`RMSE ${fmtMW(m.rmse)}`}
              hint="Largest absolute error; RMSE weights large misses more heavily" />
            <Kpi label="Periods compared" value={m.n.toLocaleString('en-GB')} sub={`Average wind ${fmtMW(m.mean_actual)}`} />
          </section>

          <section className="card">
            <div className="card-head">
              <div>
                <h2>Forecast the desk had vs. what the wind delivered</h2>
                <p>For each period, the latest forecast published before the decision time on the day before. Hover for details.</p>
              </div>
              <button className="ghost" onClick={() => downloadCsv(res)}>Download CSV</button>
            </div>
            <TimeSeriesChart actual={res.actual_series} forecast={res.series} />
          </section>

          <section className="card insights">
            <h2>Key findings</h2>
            <ul>{insights.map((t) => <li key={t}>{t}</li>)}</ul>
          </section>

          <div className="grid2">
            <section className="card">
              <h2>How big are the misses?</h2>
              <p>Distribution of forecast − actual. Right of zero: forecast too high (shortfall risk).</p>
              <BarChart
                ariaLabel="Histogram of forecast errors"
                data={res.histogram.map((b) => ({
                  key: b.from, value: b.count,
                  label: `${b.from / 1000}`,
                  title: `${fmtSignedMW(b.from)} to ${fmtSignedMW(b.to)}`,
                  tip: [['Periods', b.count], ['Share', fmtPct(100 * b.count / m.n)]],
                }))}
                highlight={(d) => d.key >= 0}
                labelEvery={Math.max(1, Math.ceil(res.histogram.length / 8))}
              />
              <div className="axis-note">Error bins, GW (highlighted = forecast too high)</div>
            </section>

            <section className="card">
              <h2>Does accuracy improve closer to delivery?</h2>
              <p>Average miss of all forecasts, grouped by how far ahead they were published.</p>
              <BarChart
                ariaLabel="Mean absolute error by forecast lead time"
                format={(v) => `${v / 1000}`}
                data={res.by_horizon.map((b) => ({
                  key: b.from_h, value: b.mae, label: `${b.from_h}–${b.to_h}h`,
                  title: `Published ${b.from_h}–${b.to_h} h ahead`,
                  tip: [['Average miss', fmtMW(b.mae)], ['Bias', fmtSignedMW(b.bias)], ['Forecasts', b.n.toLocaleString('en-GB')]],
                }))}
              />
              <div className="axis-note">Mean absolute error, GW, by lead time</div>
            </section>

            <section className="card">
              <h2>When in the day is it hardest?</h2>
              <p>Average miss by delivery hour (UK time), for the forecast used at decision time.</p>
              <BarChart
                ariaLabel="Mean absolute error by hour of day"
                format={(v) => `${v / 1000}`}
                labelEvery={3}
                data={res.by_hour.map((b) => ({
                  key: b.hour, value: b.mae, label: pad2(b.hour),
                  title: `${pad2(b.hour)}:00–${pad2(b.hour)}:59`,
                  tip: [['Average miss', fmtMW(b.mae)], ['Bias', fmtSignedMW(b.bias)], ['Periods', b.n]],
                }))}
              />
              <div className="axis-note">Mean absolute error, GW, by hour</div>
            </section>

            <section className="card">
              <h2>Day by day</h2>
              <p>Average miss for each delivery day. Use the daily table below to open any single day.</p>
              <BarChart
                ariaLabel="Mean absolute error per delivery day"
                format={(v) => `${v / 1000}`}
                labelEvery={Math.max(1, Math.ceil(res.daily.length / 8))}
                data={res.daily.map((d) => ({
                  key: d.day, value: d.mae, label: fmtIsoDay(d.day).split(' ')[0],
                  title: fmtIsoDay(d.day),
                  tip: [['Average miss', fmtMW(d.mae)], ['Bias', fmtSignedMW(d.bias)]],
                }))}
              />
              <div className="axis-note">Mean absolute error, GW, by delivery day</div>
            </section>
          </div>

          <section className="card">
            <details>
              <summary>Daily table</summary>
              <table>
                <thead><tr><th>Delivery day</th><th>Average miss</th><th>Bias</th><th>Periods</th><th></th></tr></thead>
                <tbody>
                  {res.daily.map((d) => (
                    <tr key={d.day}>
                      <td>{fmtIsoDay(d.day)}</td><td>{fmtMW(d.mae)}</td><td>{fmtSignedMW(d.bias)}</td><td>{d.n}</td>
                      <td><button className="link" onClick={() => set({ start: d.day, end: d.day })}>Inspect</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </section>

          <footer className="foot">
            Assumptions: delivery days are UK calendar days; the decision is made at the selected UK time on the day
            before delivery; only forecasts published at or before that moment are used. Error = forecast − actual.
          </footer>
        </main>
      )}
      {res && !m?.n && <div className="empty">No overlapping forecast and actual data for this selection.</div>}
    </div>
  )
}
