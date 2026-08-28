export type Locale = 'en-US' | 'zh-CN'

export const SUPPORTED_LOCALES: readonly Locale[] = ['en-US', 'zh-CN']
export const LOCALE_STORAGE_KEY = 'agentforge.locale'

export type StorageLike = Pick<Storage, 'getItem' | 'setItem'>

export function isLocale(value: string | null | undefined): value is Locale {
  return value === 'en-US' || value === 'zh-CN'
}

export function resolveLocale(storage: StorageLike, browserLanguage: string | undefined): Locale {
  try {
    const stored = storage.getItem(LOCALE_STORAGE_KEY)
    if (isLocale(stored)) return stored
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }
  return browserLanguage?.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en-US'
}

export function persistLocale(locale: Locale, storage: StorageLike): void {
  try {
    storage.setItem(LOCALE_STORAGE_KEY, locale)
  } catch {
    // Persistence is best-effort; the active session still changes locale.
  }
}

export function setDocumentLocale(locale: Locale): void {
  if (typeof document !== 'undefined') document.documentElement.lang = locale
}
