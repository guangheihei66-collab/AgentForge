import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Diagnostics as DiagnosticsData, HealthState } from '../types'

export function Diagnostics() {
  const [data, setData] = useState<DiagnosticsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { void api.getDiagnostics().then(setData).catch((reason: Error) => setError(reason.message)) }, [])
  if (error) return <section className="panel"><h2>System diagnostics</h2><p role="alert">Unable to load diagnostics: {error}</p></section>
  if (!data) return <section className="panel"><h2>System diagnostics</h2><p>Loading diagnostics…</p></section>
  const health = (label: string, value: HealthState) => <div className="stat-row" key={label}><span>{label}</span><strong>{value}</strong></div>
  return <section className="panel"><div className="section-heading"><div><div className="eyebrow">OPERABILITY</div><h2>System diagnostics</h2></div><strong>{data.health.overall}</strong></div><p>{data.identity.product} {data.identity.version} · {data.identity.revision ?? 'Revision unavailable'}</p><div className="stats-grid">{health('Backend', data.health.backend)}{health('Database', data.health.database)}{health('Provider', data.health.provider)}</div><p>Provider: {data.provider.provider} · {data.provider.model} · {data.provider.connection}</p><p>Credentials: {data.provider.credential_configured ? 'Configured' : 'Not configured'}</p></section>
}
