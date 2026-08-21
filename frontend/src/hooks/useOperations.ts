import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ApprovalQueueItem, Report, TaskDetail, TaskSummary } from '../types'

const demoTask: TaskSummary = { id: 'demo-release-v2', title: 'Release v2.0 Verification', goal: 'Verify whether Release v2.0 is ready for release.', workspace: 'D:/AgentProjects/AgentForge', status: 'WAITING_APPROVAL', created_at: '2026-08-21T14:18:07Z', updated_at: '2026-08-21T14:32:01Z' }
const demoPlan = { id: 'plan-demo', version: 1, validation_status: 'VALID', created_at: '2026-08-21T14:22:41Z', plan_json: { steps: [
  { step_id: 'step-1', tool: 'git_read', action: 'check git status', risk_level: 'low', permission_level: 'SAFE_READ' },
  { step_id: 'step-2', tool: 'file_read', action: 'read project metadata', risk_level: 'low', permission_level: 'SAFE_READ' },
  { step_id: 'step-3', tool: 'test_run', action: 'run smoke tests', risk_level: 'medium', permission_level: 'APPROVED_EXEC' },
] } }
const demoApproval: ApprovalQueueItem = { id: 'approval-demo', task_id: demoTask.id, task_title: demoTask.title, plan_id: demoPlan.id, plan_version: 1, decision: 'PENDING', requested_by: 'planner-agent', created_at: '2026-08-21T14:32:01Z', plan_json: demoPlan.plan_json }
const demoDetail: TaskDetail = { task: demoTask, plans: [demoPlan], approvals: [{ id: demoApproval.id, plan_id: demoPlan.id, decision: 'PENDING', approver: 'pending', created_at: demoApproval.created_at }], executions: [], evidence: [], audit: [{ id: 'audit-1', event_type: 'TASK_CREATED', actor: 'operator', payload_summary: 'Task created', correlation_id: 'corr-1', created_at: demoTask.created_at }, { id: 'audit-2', event_type: 'PLAN_CREATED', actor: 'planner', payload_summary: 'Validated plan version 1', correlation_id: 'corr-2', created_at: '2026-08-21T14:22:41Z' }] }

export function useOperations() {
  const [tasks, setTasks] = useState<TaskSummary[]>([demoTask])
  const [approvals, setApprovals] = useState<ApprovalQueueItem[]>([demoApproval])
  const [selectedId, setSelectedId] = useState<string | undefined>()
  const [detail, setDetail] = useState<TaskDetail>(demoDetail)
  const [report, setReport] = useState<Report>({ task: demoTask, readiness: 'PENDING', summary: 'Awaiting human approval before execution.', completed_steps: 0, failed_steps: 0, evidence: [], audit_count: 2, execution_count: 0 })
  const [live, setLive] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [nextTasks, nextApprovals] = await Promise.all([api.listTasks(), api.getPendingApprovals()])
      setTasks(nextTasks); setApprovals(nextApprovals)
      const id = selectedId && nextTasks.some(task => task.id === selectedId) ? selectedId : nextTasks[0]?.id
      if (id) {
        setSelectedId(id)
        setDetail(await api.getTaskDetail(id))
        setReport(await api.getReport(id))
      }
      setLive(true)
    } catch { setLive(false) }
  }, [selectedId])

  useEffect(() => { void refresh() }, [refresh])

  async function chooseTask(id: string) {
    setSelectedId(id)
    try { setDetail(await api.getTaskDetail(id)); setReport(await api.getReport(id)); setLive(true) } catch { if (id === demoTask.id) { setDetail(demoDetail); setReport({ task: demoTask, readiness: 'PENDING', summary: 'Awaiting human approval before execution.', completed_steps: 0, failed_steps: 0, evidence: [], audit_count: 2, execution_count: 0 }) } }
  }

  async function act(action: 'approve' | 'reject' | 'cancel', approvalId?: string) {
    if (action === 'approve' && approvalId) await api.approve(approvalId)
    if (action === 'reject' && approvalId) await api.reject(approvalId, 'Plan requires operator changes')
    if (action === 'cancel' && selectedId) await api.cancel(selectedId)
    await refresh()
  }

  return { tasks, approvals, detail, report, selectedId, chooseTask, act, refresh, live }
}
