import { useState, type FormEvent } from 'react'
import { ArrowRight, FolderKanban } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Empty, PanelTitle } from './Dashboard'
import { capabilityLabelKey } from '../i18n/status'
import { permissionKey } from '../i18n/status'
import type { ProjectSummary } from '../types'

const capabilities = [
  { id: 'repository_state', permission: 'SAFE_READ' },
  { id: 'project_metadata', permission: 'SAFE_READ' },
  { id: 'test_verification', permission: 'APPROVED_EXEC' },
]

export function Projects({ projects, onOpen, onCreate, onValidate }: {
  projects: ProjectSummary[]
  onOpen: (id: string) => void
  onCreate: (payload: { name: string; description?: string; workspace_root: string; environment: string; allowed_capability_ids: string[] }) => Promise<void>
  onValidate: (workspace: string) => Promise<string>
}) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [workspace, setWorkspace] = useState('')
  const [environment, setEnvironment] = useState('development')
  const [selected, setSelected] = useState<string[]>([])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage('')
    try {
      await onCreate({ name, workspace_root: workspace, environment, allowed_capability_ids: selected })
      setName(''); setWorkspace(''); setSelected([]); setMessage(t('projects.projectCreated'))
    } catch (error) { setMessage(error instanceof Error ? error.message : t('projects.creationFailed')) }
    finally { setBusy(false) }
  }

  async function validate() {
    setBusy(true); setMessage('')
    try { setMessage(t('projects.validWorkspace', { workspace: await onValidate(workspace) })) }
    catch (error) { setMessage(error instanceof Error ? error.message : t('projects.validationFailed')) }
    finally { setBusy(false) }
  }

  return <section className="page-stack">
    <div className="page-heading"><div><div className="eyebrow">{t('projects.eyebrow')}</div><h2>{t('projects.title')}</h2><p>{t('projects.subtitle')}</p></div></div>
    <div className="project-layout">
      <div className="panel"><PanelTitle title={t('projects.local')} action={t('projects.configured', { count: projects.length })} />
        <div className="project-list">{projects.map(project => <button className="project-row" key={project.id} onClick={() => onOpen(project.id)}><FolderKanban size={18} /><div><strong>{project.name}</strong><span>{project.workspace_root}</span></div><span className="project-activity">{project.environment}<small>{t(project.recent_task_count === 1 ? 'projects.recentTask' : 'projects.recentTasks', { count: project.recent_task_count })}</small></span><b className={`project-status ${project.status.toLowerCase()}`}>{t(project.status === 'ACTIVE' ? 'projects.active' : 'projects.archived')}</b><ArrowRight size={15} /></button>)}</div>
        {projects.length === 0 && <Empty text={t('projects.empty')} />}
      </div>
      <form className="panel project-form" onSubmit={submit}><PanelTitle title={t('projects.createProject')} />
        <label>{t('projects.name')}<input value={name} onChange={event => setName(event.target.value)} required /></label>
        <label>{t('projects.workspacePath')}<input aria-label={t('projects.workspacePath')} value={workspace} onChange={event => setWorkspace(event.target.value)} placeholder={t('projects.workspacePlaceholder')} required /></label>
        <button className="button button-secondary" type="button" disabled={busy || !workspace} onClick={() => void validate()}>{t('projects.validateWorkspace')}</button>
        <label>{t('projects.environment')}<input value={environment} onChange={event => setEnvironment(event.target.value)} required /></label>
        <fieldset><legend>{t('projects.allowedCapabilities')}</legend><p>{t('projects.defaultDeny')}</p>{capabilities.map(capability => <label className="capability-option" key={capability.id}><input type="checkbox" aria-label={capability.id} checked={selected.includes(capability.id)} onChange={event => setSelected(current => event.target.checked ? [...current, capability.id] : current.filter(id => id !== capability.id))} /><span><strong>{t(capabilityLabelKey(capability.id))}</strong><small>{t(permissionKey(capability.permission))} · {capability.id}</small></span></label>)}</fieldset>
        {message && <div className="form-message" role="status">{message}</div>}
        <button className="button button-primary" type="submit" disabled={busy}>{t('projects.createProject')}</button>
      </form>
    </div>
  </section>
}
