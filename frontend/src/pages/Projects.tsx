import { useState, type FormEvent } from 'react'
import { ArrowRight, FolderKanban } from 'lucide-react'
import { Empty, PanelTitle } from './Dashboard'
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
      setName(''); setWorkspace(''); setSelected([]); setMessage('Project created.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Project creation failed.') }
    finally { setBusy(false) }
  }

  async function validate() {
    setBusy(true); setMessage('')
    try { setMessage(`Valid workspace: ${await onValidate(workspace)}`) }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Workspace validation failed.') }
    finally { setBusy(false) }
  }

  return <section className="page-stack">
    <div className="page-heading"><div><div className="eyebrow">LOCAL EXECUTION BOUNDARIES</div><h2>Projects</h2><p>Bind every new task to one validated workspace and an explicit capability policy.</p></div></div>
    <div className="project-layout">
      <div className="panel"><PanelTitle title="Local projects" action={`${projects.length} configured`} />
        <div className="project-list">{projects.map(project => <button className="project-row" key={project.id} onClick={() => onOpen(project.id)}><FolderKanban size={18} /><div><strong>{project.name}</strong><span>{project.workspace_root}</span></div><span>{project.environment}</span><b className={`project-status ${project.status.toLowerCase()}`}>{project.status}</b><ArrowRight size={15} /></button>)}</div>
        {projects.length === 0 && <Empty text="No local Projects configured." />}
      </div>
      <form className="panel project-form" onSubmit={submit}><PanelTitle title="Create Project" />
        <label>Project name<input value={name} onChange={event => setName(event.target.value)} required /></label>
        <label>Workspace path<input aria-label="Workspace path" value={workspace} onChange={event => setWorkspace(event.target.value)} placeholder="D:\\AgentProjects\\Example" required /></label>
        <button className="button button-secondary" type="button" disabled={busy || !workspace} onClick={() => void validate()}>Validate Workspace</button>
        <label>Environment<input value={environment} onChange={event => setEnvironment(event.target.value)} required /></label>
        <fieldset><legend>Allowed capabilities</legend><p>Nothing is enabled implicitly.</p>{capabilities.map(capability => <label className="capability-option" key={capability.id}><input type="checkbox" aria-label={capability.id} checked={selected.includes(capability.id)} onChange={event => setSelected(current => event.target.checked ? [...current, capability.id] : current.filter(id => id !== capability.id))} /><span><strong>{capability.id}</strong><small>{capability.permission}</small></span></label>)}</fieldset>
        {message && <div className="form-message" role="status">{message}</div>}
        <button className="button button-primary" type="submit" disabled={busy}>Create Project</button>
      </form>
    </div>
  </section>
}
