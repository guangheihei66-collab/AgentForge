import type { Report, TaskDetail } from '../types'

export function AgentReportCard({ report, detail }: { report: Report; detail: TaskDetail }) {
  const evidence = detail.evidence.length ? detail.evidence : report.evidence
  return <div className="panel" aria-label="Agent report"><div className="panel-title"><h3>Evidence-backed Report</h3><span>{report.readiness}</span></div><p>{report.summary}</p><p>Completed: {report.completed_steps} · Failed: {report.failed_steps} · Rejected: {report.rejected_steps}</p><h4>Evidence</h4>{evidence.length ? <ul>{evidence.map(item => <li key={item.id}>{item.summary} · {item.artifact_path ?? 'path unavailable'}{item.content_hash ? ` · ${item.content_hash}` : ''}</li>)}</ul> : <p>Evidence unavailable.</p>}</div>
}
