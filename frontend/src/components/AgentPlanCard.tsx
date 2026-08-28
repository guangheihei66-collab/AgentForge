import type { Plan } from '../types'
import { useTranslation } from 'react-i18next'

export function AgentPlanCard({ plan, rawGoal }: { plan: Plan; rawGoal: string }) {
  const { t } = useTranslation()
  return <div className="panel"><div className="panel-title"><h3>{t('agentPlan.planVersion', { version: plan.version })}</h3><span>{plan.validation_status}</span></div><p>{plan.plan_json.summary ?? rawGoal}</p><ol>{plan.plan_json.steps.map(step => <li key={step.step_id}><strong>{step.capability_id}</strong><span>{JSON.stringify(step.parameters)}</span></li>)}</ol><small>{t('agentPlan.planId')}: {plan.id}</small></div>
}
