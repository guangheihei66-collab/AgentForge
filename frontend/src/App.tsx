import { useState } from 'react'
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

export function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const ops = useOperations()
  return <Shell page={page} setPage={setPage} pending={ops.approvals.length}>
    {!ops.live && <div className="demo-banner">Demo data preview · connect the FastAPI backend to use live task data.</div>}
    {page === 'agent' && <AgentWorkspace projects={ops.projects} planning={ops.agentPlanning} error={ops.agentError} task={ops.selectedId ? ops.detail.task : undefined} detail={ops.selectedId ? ops.detail : undefined} report={ops.selectedId ? ops.report : undefined} onRefreshTask={ops.refreshTask} onStart={async (projectId, goal) => { await ops.createAgentTask(projectId, goal) }} approvals={ops.approvals} onApprove={async (id) => { if (await ops.act('approve', id) && ops.selectedId) { const refreshed = await ops.refreshTask(ops.selectedId, true); if (refreshed) await ops.executeAgentTask(refreshed) } }} onReject={async (id) => { await ops.act('reject', id) }} onExecute={ops.executeAgentTask} />}
    {page === 'dashboard' && <Dashboard tasks={ops.tasks} approvals={ops.approvals} providerStatus={ops.providerStatus} testingProvider={ops.testingProvider} onTestProvider={() => void ops.testProviderConnection()} onTask={(id) => { void ops.chooseTask(id); setPage('detail') }} onApprovals={() => setPage('approvals')} />}
    {page === 'projects' && <Projects projects={ops.projects} onOpen={(id) => { void ops.chooseProject(id); setPage('project-detail') }} onCreate={ops.createProject} onValidate={ops.validateWorkspace} />}
    {page === 'project-detail' && <ProjectDetail project={ops.project} onBack={() => setPage('projects')} onCreateTask={ops.createTask} onArchive={ops.archiveProject} />}
    {page === 'approvals' && <Approvals approvals={ops.approvals} actionError={ops.actionError} onApprove={(id) => void ops.act('approve', id)} onReject={(id) => void ops.act('reject', id)} onCancel={() => void ops.act('cancel')} />}
    {page === 'detail' && <TaskDetail detail={ops.detail} onBack={() => setPage('dashboard')} onReport={() => setPage('report')} />}
    {page === 'report' && <Report report={ops.report} onBack={() => setPage('detail')} />}
    {page === 'diagnostics' && <Diagnostics />}
  </Shell>
}
