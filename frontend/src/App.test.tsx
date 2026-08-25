import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { api } from './api/client'

describe('AgentForge operations console', () => {
  afterEach(() => cleanup())

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('backend unavailable')))
  })

  it('renders the task dashboard and approval queue', async () => {
    render(<App />)
    expect((await screen.findAllByText('Release v2.0 Verification')).length).toBeGreaterThan(0)
    expect(screen.getByText('Approval queue')).toBeInTheDocument()
    expect(screen.getByText('Demo data preview · connect the FastAPI backend to use live task data.')).toBeInTheDocument()
  })

  it('opens the approval center from the dashboard', async () => {
    render(<App />)
    fireEvent.click((await screen.findAllByRole('button', { name: /Review approvals/i }))[0])
    expect(screen.getByRole('heading', { name: 'Approval Center' })).toBeInTheDocument()
    expect(screen.getByText('This is what the Agent will execute.')).toBeInTheDocument()
    expect(screen.getByText('test_verification')).toBeInTheDocument()
    expect(screen.getByText(/Resolved tool: test_run/i)).toBeInTheDocument()
    expect(screen.getByText(/profile: smoke/i)).toBeInTheDocument()
    expect(screen.getAllByText(/Registry fingerprint:/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /Approve/i })).toBeInTheDocument()
  })

  it('shows the approval error when the decision request is rejected', async () => {
    render(<App />)
    fireEvent.click((await screen.findAllByRole('button', { name: /Review approvals/i }))[0])
    fireEvent.click(await screen.findByRole('button', { name: /Approve/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('backend unavailable')
  })

  it('completes approval for a waiting task without an approval record', async () => {
    const fetchMock = approvalFlowFetch()
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/tasks/task-live/detail'))).toBe(true))
    fireEvent.click((await screen.findAllByRole('button', { name: /Review approvals/i }))[0])
    fireEvent.click(await screen.findByRole('button', { name: /Approve/i }))

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url, options]) => String(url).endsWith('/tasks/task-live/approval') && (options as RequestInit).method === 'POST')).toBe(true)
      expect(fetchMock.mock.calls.some(([url, options]) => String(url).endsWith('/approvals/approval-live/approve') && (options as RequestInit).method === 'POST')).toBe(true)
    })
  })

  it('shows safe LLM provider status without a secret editor', async () => {
    vi.stubGlobal('fetch', providerFetch({
      provider: 'openai-compatible', configured: true, model: 'example-model',
      credential_configured: true, connection_status: 'not tested', failure_category: null,
    }))

    render(<App />)

    expect(await screen.findByText('LLM Provider')).toBeInTheDocument()
    expect(screen.getByText('OpenAI-compatible')).toBeInTheDocument()
    expect(screen.getByText('example-model')).toBeInTheDocument()
    expect(screen.getByText('Credential configured')).toBeInTheDocument()
    expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/base url/i)).not.toBeInTheDocument()
  })

  it('tests provider connection only after an explicit click', async () => {
    const fetchMock = providerFetch({
      provider: 'mock', configured: true, model: 'deterministic-mock',
      credential_configured: false, connection_status: 'not tested', failure_category: null,
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)

    expect(await screen.findByText('Connection not tested')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([url, options]) => String(url).endsWith('/llm/provider/test') && (options as RequestInit | undefined)?.method === 'POST')).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Test Connection' }))
    expect(await screen.findByText('Connection success')).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/llm/provider/test'))).toHaveLength(1)
  })

  it('keeps the successful connection result when the initial status request resolves late', async () => {
    let resolveInitial: ((response: Response) => void) | undefined
    const initialStatus = new Promise<Response>((resolve) => { resolveInitial = resolve })
    const fetchMock = vi.fn(async (input: string | URL | Request, options?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/llm/provider/test') && options?.method === 'POST') {
        return jsonResponse({
          provider: 'openai-compatible', configured: true, model: 'example-model',
          credential_configured: true, connection_status: 'success', failure_category: null,
        })
      }
      if (url.endsWith('/llm/provider')) return initialStatus
      throw new Error('backend unavailable')
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Test Connection' }))
    expect(await screen.findByText('Connection success')).toBeInTheDocument()

    await act(async () => {
      resolveInitial?.(jsonResponse({
        provider: 'openai-compatible', configured: true, model: 'example-model',
        credential_configured: true, connection_status: 'not tested', failure_category: null,
      }))
      await Promise.resolve()
    })

    await waitFor(() => expect(screen.getByText('Connection success')).toBeInTheDocument())
  })

  it.each(['success', 'not tested', 'failed'] as const)('renders the immediate provider result: %s', async (connectionStatus) => {
    const fetchMock = vi.fn(async (input: string | URL | Request, options?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/llm/provider/test') && options?.method === 'POST') {
        return jsonResponse({
          provider: 'openai-compatible', configured: true, model: 'example-model',
          credential_configured: true, connection_status: connectionStatus, failure_category: null,
        })
      }
      if (url.endsWith('/llm/provider')) return jsonResponse({
        provider: 'openai-compatible', configured: true, model: 'example-model',
        credential_configured: true, connection_status: 'not tested', failure_category: null,
      })
      throw new Error('backend unavailable')
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Test Connection' }))

    expect(await screen.findByText(`Connection ${connectionStatus}`)).toBeInTheDocument()
  })

  it('shows the local Projects surface and explicit capability selection', async () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Projects' }))
    expect(await screen.findByRole('heading', { name: 'Projects' })).toBeInTheDocument()
    expect(screen.getByLabelText('Workspace path')).toBeInTheDocument()
    expect(screen.getByLabelText('repository_state')).not.toBeChecked()
    expect(screen.getByText('1 recent task')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create Project' })).toBeInTheDocument()
  })

  it('sends Project-scoped Task creation without workspace or tool authority', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'task-1' }))
    vi.stubGlobal('fetch', fetchMock)

    await api.createTask({ project_id: 'project-1', title: 'Check', goal: 'Verify release' })

    const [, options] = fetchMock.mock.calls[0]
    expect(JSON.parse(String(options.body))).toEqual({
      project_id: 'project-1', title: 'Check', goal: 'Verify release',
    })
    expect(String(options.body)).not.toContain('workspace')
    expect(String(options.body)).not.toContain('tool')
  })

  it('keeps archived Project history readable and disables mutations', async () => {
    const archived = {
      id: 'archived-project', name: 'Archived Project', description: null,
      workspace_root: 'D:/Archive', environment: 'test', status: 'ARCHIVED',
      allowed_capability_ids: ['repository_state'], config_version: 2,
      recent_task_count: 0,
      created_at: '2026-08-21T14:00:00Z', updated_at: '2026-08-21T15:00:00Z',
      recent_tasks: [],
    }
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.endsWith('/projects')) return jsonResponse([archived])
      if (url.endsWith('/projects/archived-project')) return jsonResponse(archived)
      if (url.endsWith('/tasks') || url.endsWith('/approvals/pending')) return jsonResponse([])
      if (url.endsWith('/llm/provider')) return jsonResponse({
        provider: 'mock', configured: true, model: 'deterministic-mock',
        credential_configured: false, connection_status: 'not tested', failure_category: null,
      })
      throw new Error('not needed')
    }))
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Projects' }))
    fireEvent.click(await screen.findByRole('button', { name: /Archived Project/i }))

    expect(await screen.findByRole('heading', { name: 'Archived Project' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create Task' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Archive Project' })).toBeDisabled()
    expect(screen.getByText(/History remains readable/i)).toBeInTheDocument()
  })
})

function providerFetch(initial: Record<string, unknown>) {
  return vi.fn(async (input: string | URL | Request, options?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/llm/provider/test') && options?.method === 'POST') {
      return jsonResponse({ ...initial, connection_status: 'success', failure_category: null })
    }
    if (url.endsWith('/llm/provider')) return jsonResponse(initial)
    throw new Error('backend unavailable')
  })
}

function jsonResponse(value: unknown) {
  return { ok: true, status: 200, json: async () => value } as Response
}

function approvalFlowFetch() {
  const task = { id: 'task-live', project_id: 'project-live', title: 'Release v2.0 Verification', goal: 'Verify release', workspace: 'D:/AgentProjects/AgentForge', status: 'WAITING_APPROVAL', created_at: '2026-08-21T14:18:07Z', updated_at: '2026-08-21T14:32:01Z' }
  const plan = { id: 'plan-live', version: 1, validation_status: 'VALID', created_at: task.created_at, plan_json: { schema_version: 2, steps: [], resolved_steps: [], project_authority: {} } }
  const pending = { id: task.id, approval_id: null, task_id: task.id, task_title: task.title, plan_id: plan.id, plan_version: 1, decision: 'PENDING', requested_by: 'planner-agent', created_at: task.updated_at, plan_json: plan.plan_json, resolved_snapshot: { schema_version: 2, project_authority: {}, steps: [] } }
  let approved = false
  return vi.fn(async (input: string | URL | Request, request?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/tasks') && request?.method !== 'POST') return jsonResponse([{ ...task, status: approved ? 'RUNNING' : 'WAITING_APPROVAL' }])
    if (url.endsWith('/approvals/pending')) return jsonResponse(approved ? [] : [pending])
    if (url.endsWith('/projects')) return jsonResponse([])
    if (url.endsWith('/llm/provider')) return jsonResponse({ provider: 'mock', configured: true, model: 'deterministic-mock', credential_configured: false, connection_status: 'not tested' })
    if (url.endsWith('/tasks/task-live/detail')) return jsonResponse({ task, plans: [plan], approvals: [], executions: [], evidence: [], audit: [] })
    if (url.endsWith('/tasks/task-live/report')) return jsonResponse({ task, readiness: 'PENDING', summary: 'Awaiting approval', completed_steps: 0, failed_steps: 0, evidence: [], audit_count: 0, execution_count: 0 })
    if (url.endsWith('/tasks/task-live/approval') && request?.method === 'POST') return jsonResponse({ id: 'approval-live', task_id: task.id, plan_id: plan.id, plan_version: 1, decision: 'PENDING', approver: 'pending', created_at: task.updated_at })
    if (url.endsWith('/approvals/approval-live/approve') && request?.method === 'POST') {
      approved = true
      return jsonResponse({ id: 'approval-live', task_id: task.id, plan_id: plan.id, plan_version: 1, decision: 'APPROVED', approver: 'operator', created_at: task.updated_at })
    }
    throw new Error(`Unexpected request: ${request?.method ?? 'GET'} ${url}`)
  })
}
