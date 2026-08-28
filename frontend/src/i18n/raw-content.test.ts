import { afterEach, describe, expect, it } from 'vitest'
import { setI18n } from 'react-i18next'
import { i18n } from './index'

afterEach(async () => { setI18n(i18n); await i18n.changeLanguage('en-US') })

describe('raw runtime content preservation', () => {
  it('keeps runtime values byte-equivalent while presentation locale changes', async () => {
    const raw = {
      goal: 'Verify Release v2.0', projectName: 'Alpha', taskGoal: 'Run checks', evidence: 'pytest output', observation: 'Observed FAILED', error: 'raw error', path: 'D:/workspace/file.py', sha: 'abc123', model: 'deepseek-v4-flash', provider: 'openai-compatible', capability: 'test_verification', tool: 'test_run', command: 'pytest -q', json: '{"ok":true}', code: 'def check(): pass', filename: 'report.json',
    }
    const localized = i18n.cloneInstance({ lng: 'en-US' })
    await localized.changeLanguage('zh-CN')
    expect(raw).toEqual({ goal: 'Verify Release v2.0', projectName: 'Alpha', taskGoal: 'Run checks', evidence: 'pytest output', observation: 'Observed FAILED', error: 'raw error', path: 'D:/workspace/file.py', sha: 'abc123', model: 'deepseek-v4-flash', provider: 'openai-compatible', capability: 'test_verification', tool: 'test_run', command: 'pytest -q', json: '{"ok":true}', code: 'def check(): pass', filename: 'report.json' })
  })
})
