import { Activity, BadgeCheck, BookOpen, Bot, ClipboardList, FileSearch, FolderKanban, Gauge, HeartPulse, LayoutDashboard, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

export type Page = 'dashboard' | 'agent' | 'projects' | 'project-detail' | 'approvals' | 'detail' | 'report' | 'diagnostics'
export function Shell({ page, setPage, pending, children, languageSelector }: { page: Page; setPage: (page: Page) => void; pending: number; children: ReactNode; languageSelector?: ReactNode }) {
  const { t } = useTranslation()
  const nav: { id: string; label: string; icon: typeof Gauge; page: Page }[] = [
    { id: 'dashboard', label: t('navigation.dashboard'), icon: LayoutDashboard, page: 'dashboard' },
    { id: 'agent', label: t('navigation.agent'), icon: Bot, page: 'agent' },
    { id: 'projects', label: t('navigation.projects'), icon: FolderKanban, page: 'projects' },
    { id: 'tasks', label: t('navigation.tasks'), icon: ClipboardList, page: 'detail' },
    { id: 'approvals', label: t('navigation.approvals'), icon: BadgeCheck, page: 'approvals' },
    { id: 'evidence', label: t('navigation.evidence'), icon: FileSearch, page: 'detail' },
    { id: 'audit', label: t('navigation.audit'), icon: Activity, page: 'detail' },
    { id: 'reports', label: t('navigation.reports'), icon: BookOpen, page: 'report' },
    { id: 'diagnostics', label: t('navigation.diagnostics'), icon: HeartPulse, page: 'diagnostics' },
  ]
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><ShieldCheck size={17} /></span><span>AgentForge</span></div>
      <div className="brand-sub">{t('shell.brandSub')}</div>
      <nav>{nav.map(({ id, label, icon: Icon, page: target }) => <button className={`nav-item ${page === target ? 'active' : ''}`} onClick={() => setPage(target)} key={id}><Icon size={17} /><span>{label}</span>{target === 'approvals' && pending > 0 && <b className="nav-count">{pending}</b>}</button>)}</nav>
      <div className="sidebar-footer"><span className="health-dot" /> {t('shell.systemOperational')}<br /><small>{t('common.labels.allTimesUtc')}</small></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div><div className="eyebrow">{t('shell.eyebrow')}</div><h1>AgentForge</h1></div><div className="operator"><span className="health-dot" /> {t('common.labels.systemHealth')} <span className="operator-avatar">OP</span><span>{t('common.labels.operator')}</span>{languageSelector}</div></header>
      <div className="page-content">{children}</div>
    </main>
  </div>
}
