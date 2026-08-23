import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

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
