import { AlertTriangle, CheckCircle2, CircleHelp, FileSearch, ListChecks, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { AnalystFinding, AnalystNextAction, AnalystSynthesis } from '../types'

type Props = { analyst?: AnalystSynthesis }

function evidenceRefs(refs: string[]) {
  return <div className="analyst-evidence-refs">{refs.map((reference) => <code key={reference}>{reference}</code>)}</div>
}

function stateCopy(status: AnalystSynthesis['status'], failure: string | null, t: (key: string, options?: Record<string, unknown>) => string) {
  if (status === 'PENDING') return t('analyst.pending')
  if (status === 'GENERATING') return t('analyst.generating')
  if (status === 'FAILED') return `${t('analyst.failed')} ${failure ? `(${failure})` : ''}`.trim()
  return t('analyst.notRequested')
}

function Finding({ finding }: { finding: AnalystFinding }) {
  const { t } = useTranslation()
  return <article className="analyst-finding">
    <div className="analyst-finding-heading"><strong>{finding.title}</strong><span className={`risk-pill risk-${finding.severity.toLowerCase()}`}>{t(`analyst.severity.${finding.severity}`)}</span></div>
    <p>{finding.statement}</p>
    <span className="analyst-label">{t('analyst.rationale')}</span><p className="analyst-muted">{finding.rationale}</p>
    <span className="analyst-label">{t('analyst.evidenceRefs')}</span>{evidenceRefs(finding.evidence_refs)}
    <span className="analyst-label">{t('analyst.recommendedAction')}</span><p className="analyst-action">{finding.recommended_action}</p>
  </article>
}

function NextAction({ action }: { action: AnalystNextAction }) {
  const { t } = useTranslation()
  return <li className="analyst-next-action"><span className="step-number">{action.priority}</span><div><strong>{action.action}</strong><p>{action.rationale}</p>{evidenceRefs(action.evidence_refs)}</div></li>
}

export function AnalystReportCard({ analyst }: Props) {
  const { t } = useTranslation()
  const status = analyst?.status ?? 'NOT_REQUESTED'
  const report = analyst?.report
  const heading = t('analyst.title')
  if (!report || status !== 'SUCCEEDED') {
    const icon = status === 'FAILED' ? <AlertTriangle size={17} /> : status === 'GENERATING' || status === 'PENDING' ? <Sparkles size={17} /> : <CircleHelp size={17} />
    return <section className="panel analyst-panel" aria-label={heading}><div className="panel-title"><h3>{heading}</h3><span>{stateCopy(status, analyst?.failure_category ?? null, t)}</span></div><div className="analyst-state"><span className={`analyst-state-icon ${status.toLowerCase()}`}>{icon}</span><div><strong>{status === 'FAILED' ? t('analyst.failedTitle') : stateCopy(status, null, t)}</strong><p>{status === 'FAILED' ? t('analyst.failedDescription') : status === 'GENERATING' ? t('analyst.generatingDescription') : status === 'PENDING' ? t('analyst.pendingDescription') : t('analyst.notRequestedDescription')}</p></div></div></section>
  }

  return <section className="panel analyst-panel" aria-label={heading}>
    <div className="panel-title"><h3>{heading}</h3><span>{t('analyst.succeeded')}</span></div>
    <div className="analyst-assessment"><div><span className="analyst-label">{t('analyst.overallAssessment')}</span><strong>{t(`analyst.overall.${report.overall_status}`)}</strong><p>{report.summary}</p></div><div className="analyst-recommendation"><span>{t('analyst.releaseRecommendation')}</span><strong>{t(`analyst.recommendation.${report.release_recommendation}`)}</strong></div></div>
    <div className="analyst-section"><div className="analyst-section-heading"><h4>{t('analyst.keyFindings')}</h4><span>{report.findings.length}</span></div>{report.findings.length ? <div className="analyst-findings">{report.findings.map(finding => <Finding finding={finding} key={finding.id} />)}</div> : <p className="analyst-muted">{t('analyst.noFindings')}</p>}</div>
    <div className="analyst-section"><div className="analyst-section-heading"><h4><ListChecks size={15} /> {t('analyst.nextActions')}</h4><span>{report.next_actions.length}</span></div>{report.next_actions.length ? <ol className="analyst-next-actions">{[...report.next_actions].sort((a, b) => a.priority - b.priority).map(action => <NextAction action={action} key={`${action.priority}-${action.action}`} />)}</ol> : <p className="analyst-muted">{t('analyst.noNextActions')}</p>}</div>
    <div className="analyst-section"><div className="analyst-section-heading"><h4><FileSearch size={15} /> {t('analyst.limitations')}</h4></div>{report.limitations.length ? <ul className="analyst-limitations">{report.limitations.map(limitation => <li key={limitation}>{limitation}</li>)}</ul> : <p className="analyst-muted">{t('analyst.noLimitations')}</p>}</div>
    <div className="analyst-coverage"><CheckCircle2 size={15} /><span>{t('analyst.evidenceCoverage', { referenced: report.evidence_coverage.referenced_count, available: report.evidence_coverage.available_count })}</span>{report.evidence_coverage.sufficiency && <span data-testid="analyst-evidence-sufficiency" className={`analyst-sufficiency ${report.evidence_coverage.sufficiency.toLowerCase()}`}>{t(`analyst.sufficiency.${report.evidence_coverage.sufficiency}`)}</span>}{report.evidence_coverage.truncated && <span className="analyst-truncated">{t('analyst.truncated')}</span>}</div>
  </section>
}
