// All calls to the Python backend go through here.
// Same origin in production (Vercel) and via the Vite proxy in development.
const BASE = import.meta.env?.VITE_API_BASE ?? ''

async function getJSON(path, params = {}) {
  const query = new URLSearchParams(params).toString()
  const res = await fetch(`${BASE}${path}${query ? `?${query}` : ''}`)
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail ?? detail } catch { /* not JSON */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.json()
}

export const fetchMeta = () => getJSON('/api/meta')

export const fetchAnalysis = ({ start, end, cutoffHour, cutoffMinute }) =>
  getJSON('/api/analysis', { start, end, cutoff_hour: cutoffHour, cutoff_minute: cutoffMinute })
