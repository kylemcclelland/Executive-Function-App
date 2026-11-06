import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import type { WorkSession } from '../../types'
import { Button, Dialog } from '../ui'
import { ErrorMessage } from '../common'

export function FinishSessionDialog({ session, onClose }: { session: WorkSession; onClose: () => void }) {
  const navigate = useNavigate()
  const [accomplished, setAccomplished] = useState('')
  const [resume, setResume] = useState('')
  const action = useAction()
  const projectPath = `/projects/${session.project_id}`
  function submit(event: FormEvent) {
    event.preventDefault()
    void action.run(() => api(`/work-sessions/${session.id}/finish`, 'POST', { accomplished: accomplished.trim() || null, resume_note: resume.trim() || null }), () => { onClose(); navigate(projectPath) })
  }
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title="Save your place" description="Both notes are optional. “Return to Project” leaves this session open.">
    <form onSubmit={submit} className="form-grid">
      <label className="full">What did you accomplish?<textarea autoFocus className="input" rows={4} maxLength={100000} value={accomplished} onChange={e => setAccomplished(e.target.value)} /></label>
      <label className="full">Where should you resume next time?<textarea className="input" rows={3} maxLength={100000} value={resume} onChange={e => setResume(e.target.value)} /></label>
      <div className="full"><ErrorMessage message={action.error} /></div>
      <div className="dialog-actions full"><Button variant="outline" type="button" disabled={action.pending} onClick={() => { onClose(); navigate(projectPath) }}>Return to Project</Button><Button disabled={action.pending}>{action.pending ? 'Saving…' : 'Save and Finish'}</Button></div>
    </form>
  </Dialog>
}
