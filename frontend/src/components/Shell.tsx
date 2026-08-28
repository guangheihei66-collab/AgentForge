import { Activity, BadgeCheck, BookOpen, Bot, ClipboardList, FileSearch, FolderKanban, Gauge, HeartPulse, LayoutDashboard, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'

export type Page = 'dashboard' | 'agent' | 'projects' | 'project-detail' | 'approvals' | 'detail' | 'report' | 'diagnostics'
export function Shell({ page, setPage, pending, children }: { page: Page; setPage: (page: Page) => void; pending: number; children: ReactNode }) {
  const nav: { label: string; icon: typeof Gauge; page: Page }[] = [
    { label: 'Dashboard', icon: LayoutDashboard, page: 'dashboard' },
    { label: 'Agent', icon: Bot, page: 'agent' },
    { label: 'Projects', icon: FolderKanban, page: 'projects' },
    { label: 'Tasks', icon: ClipboardList, page: 'detail' },
    { label: 'Approvals', icon: BadgeCheck, page: 'approvals' },
    { label: 'Evidence', icon: FileSearch, page: 'detail' },
    { label: 'Audit', icon: Activity, page: 'detail' },
    { label: 'Reports', icon: BookOpen, page: 'report' },
    { label: 'Diagnostics', icon: HeartPulse, page: 'diagnostics' },
  ]
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><ShieldCheck size={17} /></span><span>AgentForge</span></div>
      <div className="brand-sub">AI Agent Operations</div>
      <nav>{nav.map(({ label, icon: Icon, page: target }) => <button className={`nav-item ${page === target ? 'active' : ''}`} onClick={() => setPage(target)} key={label}><Icon size={17} /><span>{label}</span>{label === 'Approvals' && pending > 0 && <b className="nav-count">{pending}</b>}</button>)}</nav>
      <div className="sidebar-footer"><span className="health-dot" /> System operational<br /><small>All times in UTC</small></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><div><div className="eyebrow">ENTERPRISE AI AGENT OPERATIONS CONSOLE</div><h1>AgentForge</h1></div><div className="operator"><span className="health-dot" /> System health <span className="operator-avatar">OP</span><span>Operator</span></div></header>
      <div className="page-content">{children}</div>
    </main>
  </div>
}
