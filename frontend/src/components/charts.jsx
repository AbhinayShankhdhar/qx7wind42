// Small, dependency-free SVG charts. Kept generic so every chart on the page
// shares the same axes, colours, spacing and hover behaviour.
import { useEffect, useMemo, useRef, useState } from 'react'
import { fmtDateTime, fmtDay, fmtMW, fmtSignedMW, niceTicks } from '../format.js'

const M = { top: 12, right: 16, bottom: 30, left: 56 } // chart margins

// Track the rendered width of a container so charts are responsive.
export function useWidth(initial = 800) {
  const ref = useRef(null)
  const [width, setWidth] = useState(initial)
  useEffect(() => {
    if (!ref.current) return
    // Ignore zero/tiny widths reported before layout settles.
    const ro = new ResizeObserver(([entry]) => { if (entry.contentRect.width > 120) setWidth(entry.contentRect.width) })
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, width]
}

function YAxis({ ticks, y, width, format }) {
  return (
    <g>
      {ticks.map((t) => (
        <g key={t} transform={`translate(0,${y(t)})`}>
          <line x1={M.left} x2={width - M.right} className={t === 0 ? 'axis-zero' : 'grid'} />
          <text x={M.left - 8} dy="0.32em" textAnchor="end" className="tick">{format(t)}</text>
        </g>
      ))}
    </g>
  )
}

function Tooltip({ x, y, width, children }) {
  const flip = x > width * 0.62 // keep the tooltip inside the chart
  return (
    <div className="tooltip" style={{ left: x, top: y, transform: `translate(${flip ? 'calc(-100% - 14px)' : '14px'}, -50%)` }}>
      {children}
    </div>
  )
}

// Binary search: index of the item whose `key` is closest to target.
function nearest(arr, target, key) {
  if (!arr.length) return -1
  let lo = 0, hi = arr.length - 1
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (arr[mid][key] < target) lo = mid + 1
    else hi = mid
  }
  if (lo > 0 && Math.abs(arr[lo - 1][key] - target) < Math.abs(arr[lo][key] - target)) lo -= 1
  return lo
}

// Build an SVG path, breaking the line where data is missing (gap > maxGap seconds).
function linePath(points, x, y, xKey, yKey, maxGap = 3 * 3600) {
  let d = ''
  let prev = null
  for (const p of points) {
    const cmd = prev == null || p[xKey] - prev > maxGap ? 'M' : 'L'
    d += `${cmd}${x(p[xKey]).toFixed(1)},${y(p[yKey]).toFixed(1)}`
    prev = p[xKey]
  }
  return d
}

/** Actual vs decision-time forecast over time, with a crosshair tooltip. */
export function TimeSeriesChart({ actual, forecast, height = 320 }) {
  const [ref, width] = useWidth()
  const [hoverT, setHoverT] = useState(null)

  const { x, y, yTicks, xTicks, t0, t1 } = useMemo(() => {
    const times = [...actual.map((d) => d.start), ...forecast.map((d) => d.start)]
    const t0 = Math.min(...times), t1 = Math.max(...times)
    const yMax = Math.max(1, ...actual.map((d) => d.actual), ...forecast.map((d) => d.forecast))
    const yTicks = niceTicks(0, yMax, 5)
    const top = yTicks[yTicks.length - 1]
    const x = (t) => M.left + ((t - t0) / Math.max(1, t1 - t0)) * (width - M.left - M.right)
    const y = (v) => height - M.bottom - (v / top) * (height - M.top - M.bottom)
    // One label per N days so labels never collide (~90px each).
    const days = Math.max(1, Math.round((t1 - t0) / 86400))
    const every = Math.max(1, Math.ceil(days / Math.max(1, Math.floor((width - M.left - M.right) / 90))))
    const xTicks = []
    const firstMidnight = Math.ceil(t0 / 86400) * 86400
    for (let t = firstMidnight, i = 0; t <= t1; t += 86400, i++) if (i % every === 0) xTicks.push(t)
    return { x, y, yTicks, xTicks, t0, t1 }
  }, [actual, forecast, width, height])

  if (!actual.length && !forecast.length) return <p className="empty">No data for this selection.</p>

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = e.clientX - rect.left
    const t = t0 + ((px - M.left) / (width - M.left - M.right)) * (t1 - t0)
    setHoverT(Math.min(t1, Math.max(t0, t)))
  }

  const fi = hoverT == null ? -1 : nearest(forecast, hoverT, 'start')
  const f = fi >= 0 ? forecast[fi] : null
  const ai = f ? nearest(actual, f.start, 'start') : hoverT == null ? -1 : nearest(actual, hoverT, 'start')
  const a = ai >= 0 ? actual[ai] : null
  const focusT = f ? f.start : a?.start

  return (
    <div className="chart" ref={ref}>
      <div className="legend" aria-hidden="true">
        <span><i className="swatch line s-actual" />Actual generation</span>
        <span><i className="swatch line s-forecast" />Forecast available at decision time</span>
      </div>
      <svg width={width} height={height} role="img"
        aria-label="Line chart of actual wind generation versus the forecast available at decision time"
        onMouseMove={onMove} onMouseLeave={() => setHoverT(null)}>
        <YAxis ticks={yTicks} y={y} width={width} format={(v) => `${v / 1000}`} />
        {xTicks.map((t) => (
          <text key={t} x={x(t)} y={height - 8} textAnchor="middle" className="tick">{fmtDay(t)}</text>
        ))}
        <path d={linePath(actual, x, y, 'start', 'actual')} className="series s-actual" />
        <path d={linePath(forecast, x, y, 'start', 'forecast')} className="series s-forecast" />
        {focusT != null && (
          <g>
            <line x1={x(focusT)} x2={x(focusT)} y1={M.top} y2={height - M.bottom} className="crosshair" />
            {a && <circle cx={x(a.start)} cy={y(a.actual)} r="4.5" className="dot s-actual" />}
            {f && <circle cx={x(f.start)} cy={y(f.forecast)} r="4.5" className="dot s-forecast" />}
          </g>
        )}
      </svg>
      <div className="axis-note">Generation, GW · times in UK local time</div>
      {focusT != null && (
        <Tooltip x={x(focusT)} y={height / 2} width={width}>
          <div className="tt-title">{fmtDateTime(focusT)}</div>
          <div className="tt-row"><i className="swatch line s-actual" />Actual<b>{fmtMW(a?.actual)}</b></div>
          {f && <>
            <div className="tt-row"><i className="swatch line s-forecast" />Forecast<b>{fmtMW(f.forecast)}</b></div>
            <div className="tt-row muted">Error<b>{fmtSignedMW(f.error)}</b></div>
            <div className="tt-row muted">Published<b>{fmtDateTime(f.publish)}</b></div>
            <div className="tt-row muted">Made ahead<b>{f.horizon_h.toFixed(1)} h</b></div>
          </>}
        </Tooltip>
      )}
    </div>
  )
}

/** Vertical bar chart. data: [{ key, label, value, tip: [ [label, value], ... ] }] */
export function BarChart({ data, format = (v) => v, height = 220, labelEvery = 1, ariaLabel, highlight }) {
  const [ref, width] = useWidth(400)
  const [hover, setHover] = useState(null)
  const valid = data.filter((d) => d.value != null)
  if (!valid.length) return <p className="empty">No data for this selection.</p>

  const yTicks = niceTicks(0, Math.max(...valid.map((d) => d.value)), 4)
  const top = yTicks[yTicks.length - 1] || 1
  const innerW = width - M.left - M.right
  const slot = innerW / data.length
  const gap = Math.min(2, slot * 0.2) // 2px surface gap between bars
  const y = (v) => height - M.bottom - (v / top) * (height - M.top - M.bottom)
  const base = y(0)
  // Skip labels if they would overlap on narrow screens (~7px per character).
  const labelW = Math.max(...data.map((d) => String(d.label).length)) * 7 + 8
  const every = Math.max(labelEvery, Math.ceil(labelW / slot))

  return (
    <div className="chart" ref={ref}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel} onMouseLeave={() => setHover(null)}>
        <YAxis ticks={yTicks} y={y} width={width} format={format} />
        {data.map((d, i) => {
          const bx = M.left + i * slot + gap / 2
          const bw = Math.max(1, slot - gap)
          const h = d.value == null ? 0 : base - y(d.value)
          const r = Math.min(4, bw / 2, h)
          // bar with rounded top corners, square at the baseline
          const path = `M${bx},${base} V${base - h + r} Q${bx},${base - h} ${bx + r},${base - h} H${bx + bw - r} Q${bx + bw},${base - h} ${bx + bw},${base - h + r} V${base} Z`
          const cls = `bar${highlight?.(d) ? ' bar-hl' : ''}${hover === i ? ' bar-hover' : ''}`
          return (
            <g key={d.key ?? i} onMouseEnter={() => setHover(i)}>
              <rect x={M.left + i * slot} y={M.top} width={slot} height={height - M.top - M.bottom} fill="transparent" />
              {h > 0 && <path d={path} className={cls} />}
              {i % every === 0 && (
                <text x={bx + bw / 2} y={height - 8} textAnchor="middle" className="tick">{d.label}</text>
              )}
            </g>
          )
        })}
      </svg>
      {hover != null && data[hover] && (
        <Tooltip x={M.left + (hover + 0.5) * slot} y={height / 2} width={width}>
          <div className="tt-title">{data[hover].title ?? data[hover].label}</div>
          {(data[hover].tip ?? []).map(([k, v]) => (
            <div className="tt-row" key={k}>{k}<b>{v}</b></div>
          ))}
        </Tooltip>
      )}
    </div>
  )
}
