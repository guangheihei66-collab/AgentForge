import i18next from 'i18next'
import { initReactI18next, I18nextProvider } from 'react-i18next'
import { resolveLocale, setDocumentLocale } from './locale'
import { enUS } from './resources/en-US'
import { zhCN } from './resources/zh-CN'

export const resources = { 'en-US': { translation: enUS }, 'zh-CN': { translation: zhCN } } as const
// Use the package singleton so components rendered outside an explicit
// I18nextProvider (including focused unit tests) share the same initialized
// instance as the application provider.
export const i18n = i18next
const initialLocale = resolveLocale(typeof localStorage === 'undefined' ? { getItem: () => null, setItem: () => undefined } : localStorage, typeof navigator === 'undefined' ? undefined : navigator.language)

void i18n.use(initReactI18next).init({ resources, lng: initialLocale, fallbackLng: 'en-US', interpolation: { escapeValue: false }, initImmediate: false })
setDocumentLocale(initialLocale)

export { I18nextProvider, I18nextProvider as I18nProvider }
