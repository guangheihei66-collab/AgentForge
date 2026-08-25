import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Diagnostics } from './Diagnostics'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const base = (overall: string, revision: string | null = 'abc123') => ({
  identity: { product: 'AgentForge', version: '0.1.0', revision, environment: 'beta' },
  health: { overall, backend: overall, database: overall, provider: overall },
  provider: { provider: 'openai-compatible', model: 'deepseek-v4-flash', structured_output_mode: 'json_object', credential_configured: true, connection: 'SUCCESS' },
  recent_task: null, recent_errors: [],
})

describe('Diagnostics status page', () => {
  it.each(['HEALTHY', 'DEGRADED', 'UNHEALTHY', 'UNKNOWN'])('renders %s state', async (state) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => base(state) }))
    render(<Diagnostics />)
    expect(screen.getByText('Loading diagnostics…')).toBeInTheDocument()
    expect((await screen.findAllByText(state)).length).toBeGreaterThanOrEqual(1)
  })

  it('renders revision fallback and configured state without secrets', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ...base('HEALTHY', null), provider: { ...base('HEALTHY').provider, credential_configured: false, secret: 'SECRET_SENTINEL_DO_NOT_RENDER' } }) }))
    render(<Diagnostics />)
    expect(await screen.findByText(/Revision unavailable/)).toBeInTheDocument()
    expect(screen.getByText('Credentials: Not configured')).toBeInTheDocument()
    await waitFor(() => expect(document.body).not.toHaveTextContent('SECRET_SENTINEL_DO_NOT_RENDER'))
  })

  it('renders API failure safely', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('diagnostics unavailable')))
    render(<Diagnostics />)
    expect(await screen.findByRole('alert')).toHaveTextContent('diagnostics unavailable')
  })
})
