import { describe, expect, it, vi } from 'vitest'
import {
  LOCALE_STORAGE_KEY,
  persistLocale,
  resolveLocale,
  setDocumentLocale,
} from './locale'

function storage(values: Record<string, string> = {}) {
  return {
    getItem: vi.fn((key: string) => values[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { values[key] = value }),
  }
}

describe('locale resolution', () => {
  it.each([
    ['en-US', 'en-US'],
    ['zh-CN', 'zh-CN'],
    ['zh-TW', 'zh-CN'],
    ['zh', 'zh-CN'],
    ['fr-FR', 'en-US'],
    [undefined, 'en-US'],
  ])('resolves browser language %s to %s', (browserLanguage, expected) => {
    expect(resolveLocale(storage(), browserLanguage)).toBe(expected)
  })

  it('uses an explicit valid preference before browser language', () => {
    const store = storage({ [LOCALE_STORAGE_KEY]: 'en-US' })
    expect(resolveLocale(store, 'zh-CN')).toBe('en-US')
  })

  it('ignores an invalid preference', () => {
    const store = storage({ [LOCALE_STORAGE_KEY]: 'de-DE' })
    expect(resolveLocale(store, 'zh-CN')).toBe('zh-CN')
  })

  it('persists the selected supported locale', () => {
    const store = storage()
    persistLocale('zh-CN', store)
    expect(store.setItem).toHaveBeenCalledWith(LOCALE_STORAGE_KEY, 'zh-CN')
  })

  it('updates document language', () => {
    setDocumentLocale('zh-CN')
    expect(document.documentElement.lang).toBe('zh-CN')
  })
})
