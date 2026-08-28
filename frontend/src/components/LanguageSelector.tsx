import { useTranslation } from 'react-i18next'
import { persistLocale, type Locale } from '../i18n/locale'

export function LanguageSelector() {
  const { t, i18n } = useTranslation()
  return <label className="language-selector">
    <span className="sr-only">{t('navigation.language')}</span>
    <select aria-label={t('navigation.language')} value={i18n.language} onChange={(event) => {
      const locale = event.target.value as Locale
      persistLocale(locale, localStorage)
      void i18n.changeLanguage(locale)
    }}>
      <option value="en-US">{t('navigation.english')}</option>
      <option value="zh-CN">{t('navigation.chinese')}</option>
    </select>
  </label>
}
