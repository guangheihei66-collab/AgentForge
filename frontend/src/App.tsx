import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Shell } from './components/Shell'
import type { Page } from './components/Shell'
import { useOperations } from './hooks/useOperations'
import { Approvals } from './pages/Approvals'
import { Dashboard } from './pages/Dashboard'
import { Report } from './pages/Report'
import { TaskDetail } from './pages/TaskDetail'
import { Projects } from './pages/Projects'
import { ProjectDetail } from './pages/ProjectDetail'
import { Diagnostics } from './pages/Diagnostics'
import { AgentWorkspace } from './pages/AgentWorkspace'
import { LanguageSelector } from './components/LanguageSelector'
import { setDocumentLocale } from './i18n/locale'

export function App() {
  const { t, i18n } = useTranslation()
  const [page, setPage] = useState<Page>('dashboard')
  const ops = useOperations()
  useEffect(() => {
    const sync = (locale: string) => setDocumentLocale(locale === 'zh-CN' ? 'zh-CN' : 'en-US')
    sync(i18n.language)
    i18n.on('languageChanged', sync)
    return () => { i18n.off('languageChanged', sync) }
  }, [])
  return <div translate="no"><Shell page={page} setPage={setPage} pending={ops.approvals.length} languageSelector={<LanguageSelector />}>
    {!ops.live && <div className="demo-banner">{t('dashboard.demoBanner')}</div>}
    {page === 'agent' && <AgentWorkspace projects={ops.projects} planning={ops.agentPlanning} error={ops.agentError} task={ops.selectedId ? ops.detail.task : undefined} detail={ops.selectedId ? ops.detail : undefined} report={ops.selectedId ? ops.report : undefined} onRefreshTask={ops.refreshTask} onStart={async (projectId, goal) => { await ops.createAgentTask(projectId, goal) }} approvals={ops.approvals} onApprove={ops.approveAndExecuteAgentTask} onReject={async (id) => { await ops.act('reject', id) }} onExecute={ops.executeAgentTask} />}
    {page === 'dashboard' && <Dashboard tasks={ops.tasks} approvals={ops.approvals} providerStatus={ops.providerStatus} testingProvider={ops.testingProvider} onTestProvider={() => void ops.testProviderConnection()} onTask={(id) => { void ops.chooseTask(id); setPage('detail') }} onApprovals={() => setPage('approvals')} />}
    {page === 'projects' && <Projects projects={ops.projects} onOpen={(id) => { void ops.chooseProject(id); setPage('project-detail') }} onCreate={ops.createProject} onValidate={ops.validateWorkspace} />}
    {page === 'project-detail' && <ProjectDetail project={ops.project} onBack={() => setPage('projects')} onCreateTask={ops.createTask} onArchive={ops.archiveProject} />}
    {page === 'approvals' && <Approvals approvals={ops.approvals} actionError={ops.actionError} onApprove={(id) => void ops.act('approve', id)} onReject={(id) => void ops.act('reject', id)} onCancel={() => void ops.act('cancel')} onOpenInAgentWorkspace={async (taskId) => { await ops.chooseTask(taskId); setPage('agent') }} />}
    {page === 'detail' && <TaskDetail detail={ops.detail} onBack={() => setPage('dashboard')} onReport={() => setPage('report')} />}
    {page === 'report' && <Report report={ops.report} onBack={() => setPage('detail')} />}
    {page === 'diagnostics' && <Diagnostics />}
  </Shell></div>
}
