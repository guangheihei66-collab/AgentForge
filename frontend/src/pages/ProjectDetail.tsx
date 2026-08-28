import { useState, type FormEvent } from 'react'
import { ArrowLeft, Archive, ListTodo } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Empty, PanelTitle } from './Dashboard'
import { capabilityLabelKey, taskStatusKey } from '../i18n/status'
import type { ProjectDetail as ProjectDetailType } from '../types'

export function ProjectDetail({ project, onBack, onCreateTask, onArchive }: {
  project?: ProjectDetailType
  onBack: () => void
  onCreateTask: (projectId: string, title: string, goal: string) => Promise<void>
  onArchive: (projectId: string, version: number) => Promise<void>
}) {
  const { t } = useTranslation()
  const [title, setTitle] = useState('')
  const [goal, setGoal] = useState('')
  const [message, setMessage] = useState('')
  if (!project) return <section className="page-stack"><button className="back-button" onClick={onBack}><ArrowLeft size={14} />{t('projectDetail.backToProjects')}</button><div className="panel"><Empty text={t('projectDetail.unavailable')} /></div></section>
  const archived = project.status === 'ARCHIVED'
  async function submit(event: FormEvent) {
    event.preventDefault(); setMessage('')
    try { await onCreateTask(project!.id, title, goal); setTitle(''); setGoal(''); setMessage(t('projectDetail.taskCreated')) }
    catch (error) { setMessage(error instanceof Error ? error.message : t('projectDetail.taskCreationFailed')) }
  }
  return <section className="page-stack">
    <button className="back-button" onClick={onBack}><ArrowLeft size={14} />{t('projectDetail.backToProjects')}</button>
    <div className="page-heading task-heading"><div><div className="eyebrow">{t('projectDetail.eyebrow')}</div><h2>{project.name}</h2><p>{project.description || t('projectDetail.noDescription')}</p></div><b className={`project-status ${project.status.toLowerCase()}`}>{t(project.status === 'ACTIVE' ? 'projects.active' : 'projects.archived')}</b></div>
    {archived && <div className="callout"><Archive size={18} /><div><strong>{t('projectDetail.archived')}</strong><span>{t('projectDetail.archivedMessage')}</span></div></div>}
    <div className="project-layout"><div className="panel project-facts"><PanelTitle title={t('projectDetail.boundary')} /><dl><div><dt>{t('projectDetail.canonicalWorkspace')}</dt><dd>{project.workspace_root}</dd></div><div><dt>{t('common.labels.environment')}</dt><dd>{project.environment}</dd></div><div><dt>{t('projectDetail.configVersion')}</dt><dd>{project.config_version}</dd></div></dl><h4>{t('projectDetail.allowedCapabilities')}</h4><div className="capability-tags">{project.allowed_capability_ids.map(id => <span key={id}>{t(capabilityLabelKey(id))} · {id}</span>)}</div>{project.allowed_capability_ids.length === 0 && <Empty text={t('projectDetail.noCapabilities')} />}</div>
      <form className="panel project-form" onSubmit={submit}><PanelTitle title={t('projectDetail.createTask')} /><label>{t('projectDetail.taskTitle')}<input value={title} onChange={event => setTitle(event.target.value)} disabled={archived} required /></label><label>{t('projectDetail.taskGoal')}<textarea value={goal} onChange={event => setGoal(event.target.value)} disabled={archived} required /></label>{message && <div className="form-message" role="status">{message}</div>}<button className="button button-primary" disabled={archived}>{t('projectDetail.createTask')}</button><button className="button button-danger" type="button" disabled={archived} onClick={() => void onArchive(project.id, project.config_version)}>{t('projectDetail.archiveProject')}</button></form></div>
    <div className="panel"><PanelTitle title={t('projectDetail.recentTasks')} action={t('projectDetail.shown', { count: project.recent_tasks.length })} /><div className="project-tasks">{project.recent_tasks.map(task => <div key={task.id}><ListTodo size={15} /><span><strong>{task.title}</strong><small>{task.goal}</small></span><b>{t(taskStatusKey(task.status))}</b></div>)}</div>{project.recent_tasks.length === 0 && <Empty text={t('projectDetail.noTasks')} />}</div>
  </section>
}
