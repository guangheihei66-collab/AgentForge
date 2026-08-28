import { useTranslation } from 'react-i18next'
import { permissionKey, riskKey, taskStatusKey } from '../i18n/status'

export function StatusPill({ status }: { status: string }) {
  const { t } = useTranslation()
  return <span className={`status-pill status-${status.toLowerCase()}`}>{t(taskStatusKey(status))}</span>
}

export function PermissionPill({ value }: { value: string }) {
  const { t } = useTranslation()
  return <span className={`permission-pill permission-${value.toLowerCase()}`}>{t(permissionKey(value))}</span>
}

export function RiskPill({ value }: { value: string }) {
  const { t } = useTranslation()
  return <span className={`risk-pill risk-${value.toLowerCase()}`}>{t(riskKey(value.toLowerCase().replace(' risk', '')))}</span>
}
