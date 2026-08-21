import { useState } from 'react'
import { Shell } from './components/Shell'
import { useOperations } from './hooks/useOperations'
import { Approvals } from './pages/Approvals'
import { Dashboard } from './pages/Dashboard'
import { Report } from './pages/Report'
import { TaskDetail } from './pages/TaskDetail'

export function App() {
  const [page, setPage] = useState<'dashboard' | 'approvals' | 'detail' | 'report'>('dashboard')
  const ops = useOperations()
  return <Shell page={page} setPage={setPage} pending={ops.approvals.length}>
    {!ops.live && <div className="demo-banner">Demo data preview · connect the FastAPI backend to use live task data.</div>}
    {page === 'dashboard' && <Dashboard tasks={ops.tasks} approvals={ops.approvals} onTask={(id) => { void ops.chooseTask(id); setPage('detail') }} onApprovals={() => setPage('approvals')} />}
    {page === 'approvals' && <Approvals approvals={ops.approvals} onApprove={(id) => void ops.act('approve', id)} onReject={(id) => void ops.act('reject', id)} onCancel={() => void ops.act('cancel')} />}
    {page === 'detail' && <TaskDetail detail={ops.detail} onBack={() => setPage('dashboard')} onReport={() => setPage('report')} />}
    {page === 'report' && <Report report={ops.report} onBack={() => setPage('detail')} />}
  </Shell>
}
