import { useState, type FormEvent } from 'react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { Button, Dialog, Input } from '../ui'
import { ErrorMessage } from '../common'

export function SessionDialog({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const [kind, setKind] = useState<'session' | 'progress'>('session')
  const [summary, setSummary] = useState('')
  const [nextStep, setNextStep] = useState('')
  const action = useAction()
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!summary.trim()) return
    void action.run(() => api(`/projects/${projectId}/updates`, 'POST', { kind, summary: summary.trim(), next_step: nextStep.trim() || null }), onClose)
  }
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title="Save your place" description="A few words now make it easy to pick this back up later.">
    <form onSubmit={submit} className="form-grid">
      <label className="full">What did you accomplish?<textarea autoFocus required className="input" rows={3} maxLength={100000} value={summary} onChange={e => setSummary(e.target.value)} placeholder="Even a small thing counts" /></label>
      <label className="full">What should you do next?<Input maxLength={2000} value={nextStep} onChange={e => setNextStep(e.target.value)} placeholder="Optional. This becomes the project’s next action." /></label>
      <label>Type<select className="input" value={kind} onChange={e => setKind(e.target.value as 'session' | 'progress')}><option value="session">Work session</option><option value="progress">Progress update</option></select></label>
      <div className="full"><ErrorMessage message={action.error} /></div>
      <div className="dialog-actions full"><Button variant="outline" type="button" onClick={onClose} disabled={action.pending}>Cancel</Button><Button disabled={action.pending || !summary.trim()}>{action.pending ? 'Saving…' : 'Save'}</Button></div>
    </form>
  </Dialog>
}
