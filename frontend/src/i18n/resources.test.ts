import { describe, expect, it } from 'vitest'
import { i18n, resources } from './index'

function keys(value: unknown, prefix = ''): string[] {
  if (!value || typeof value !== 'object') return [prefix]
  return Object.entries(value).flatMap(([key, child]) => keys(child, prefix ? `${prefix}.${key}` : key))
}

describe('native localization resources', () => {
  it('contains exactly en-US and zh-CN with matching keys', () => {
    expect(Object.keys(resources).sort()).toEqual(['en-US', 'zh-CN'])
    expect(keys(resources['en-US'].translation).sort()).toEqual(keys(resources['zh-CN'].translation).sort())
  })

  it('uses English as deterministic fallback for missing keys', () => {
    expect(i18n.options.fallbackLng).toEqual(['en-US'])
    expect(i18n.t('missing.key')).toBe('missing.key')
  })
})
