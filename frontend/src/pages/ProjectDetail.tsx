import { useState, type FormEvent } from 'react'
import { ArrowLeft, Archive, ListTodo } from 'lucide-react'
import { Empty, PanelTitle } from './Dashboard'
import type { ProjectDetail as ProjectDetailType } from '../types'

export function ProjectDetail({ project, onBack, onCreateTask, onArchive }: {
  project?: ProjectDetailType
  onBack: () => void
  onCreateTask: (projectId: string, title: string, goal: string) => Promise<void>
  onArchive: (projectId: string, version: number) => Promise<void>
}) {
  const [title, setTitle] = useState('')
  const [goal, setGoal] = useState('')
  const [message, setMessage] = useState('')
  if (!project) return <section className="page-stack"><button className="back-button" onClick={onBack}><ArrowLeft size={14} />Back to Projects</button><div className="panel"><Empty text="Project details are not available." /></div></section>
  const archived = project.status === 'ARCHIVED'
  async function submit(event: FormEvent) {
    event.preventDefault(); setMessage('')
    try { await onCreateTask(project!.id, title, goal); setTitle(''); setGoal(''); setMessage('Task created.') }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Task creation failed.') }
  }
  return <section className="page-stack">
    <button className="back-button" onClick={onBack}><ArrowLeft size={14} />Back to Projects</button>
    <div className="page-heading task-heading"><div><div className="eyebrow">PROJECT EXECUTION AUTHORITY</div><h2>{project.name}</h2><p>{project.description || 'No description provided.'}</p></div><b className={`project-status ${project.status.toLowerCase()}`}>{project.status}</b></div>
    {archived && <div className="callout"><Archive size={18} /><div><strong>Archived Project</strong><span>History remains readable, but new tasks and execution are blocked.</span></div></div>}
    <div className="project-layout"><div className="panel project-facts"><PanelTitle title="Project boundary" /><dl><div><dt>Canonical workspace</dt><dd>{project.workspace_root}</dd></div><div><dt>Environment</dt><dd>{project.environment}</dd></div><div><dt>Config version</dt><dd>{project.config_version}</dd></div></dl><h4>Allowed capabilities</h4><div className="capability-tags">{project.allowed_capability_ids.map(id => <span key={id}>{id}</span>)}</div>{project.allowed_capability_ids.length === 0 && <Empty text="No capabilities enabled (default deny)." />}</div>
      <form className="panel project-form" onSubmit={submit}><PanelTitle title="Create Task" /><label>Title<input value={title} onChange={event => setTitle(event.target.value)} disabled={archived} required /></label><label>Goal<textarea value={goal} onChange={event => setGoal(event.target.value)} disabled={archived} required /></label>{message && <div className="form-message" role="status">{message}</div>}<button className="button button-primary" disabled={archived}>Create Task</button><button className="button button-danger" type="button" disabled={archived} onClick={() => void onArchive(project.id, project.config_version)}>Archive Project</button></form></div>
    <div className="panel"><PanelTitle title="Recent tasks" action={`${project.recent_tasks.length} shown`} /><div className="project-tasks">{project.recent_tasks.map(task => <div key={task.id}><ListTodo size={15} /><span><strong>{task.title}</strong><small>{task.goal}</small></span><b>{task.status}</b></div>)}</div>{project.recent_tasks.length === 0 && <Empty text="No tasks created for this Project." />}</div>
  </section>
}
