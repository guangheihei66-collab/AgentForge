import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { setI18n } from 'react-i18next'
import { App } from './App'
import { I18nProvider, i18n } from './i18n'

describe('application localization boundary', () => {
  afterEach(async () => { document.documentElement.lang = 'en-US'; setI18n(i18n); await i18n.changeLanguage('en-US') })

  it('marks the application root as not translatable and synchronizes document language', () => {
    const localized = i18n.cloneInstance({ lng: 'en-US' })
    render(<I18nProvider i18n={localized}><App /></I18nProvider>)
    expect(document.querySelector('[translate="no"]')).toBeInTheDocument()
    expect(document.documentElement.lang).toBe('en-US')
    fireEvent.change(screen.getByRole('combobox', { name: 'Language' }), { target: { value: 'zh-CN' } })
    expect(document.documentElement.lang).toBe('zh-CN')
  })
})
