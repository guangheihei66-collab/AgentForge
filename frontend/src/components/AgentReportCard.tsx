import type { Report, TaskDetail } from '../types'
import { useTranslation } from 'react-i18next'

export function AgentReportCard({ report, detail }: { report: Report; detail: TaskDetail }) {
  const { t } = useTranslation()
  const evidence = detail.evidence.length ? detail.evidence : report.evidence
  return <div className="panel" aria-label="Agent report"><div className="panel-title"><h3>{t('agentReport.title')}</h3><span>{report.readiness}</span></div><p>{report.summary}</p><p>{t('agentReport.completed')}: {report.completed_steps} · {t('agentReport.failed')}: {report.failed_steps} · {t('agentReport.rejected')}: {report.rejected_steps}</p><h4>{t('agentReport.evidence')}</h4>{evidence.length ? <ul>{evidence.map(item => <li key={item.id}>{item.summary} · {item.artifact_path ?? t('common.labels.unknown')}{item.content_hash ? ` · ${item.content_hash}` : ''}</li>)}</ul> : <p>{t('agentReport.unavailable')}</p>}</div>
}
