import { useState } from 'react'
import { ArrowDown, ArrowUp, Plus, X } from 'lucide-react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import type { Task } from '../../types'
import { Button, Input } from '../ui'
import { ConfirmDelete, ErrorMessage } from '../common'

export function Steps({ task }: { task: Task }) {
  const [title, setTitle] = useState('')
  const [deleting, setDeleting] = useState<{ id: string; title: string } | null>(null)
  const action = useAction()
  const steps = [...(task.steps ?? [])].sort((a, b) => a.position - b.position)
  const path = `/tasks/${task.id}/steps`
  return <div className="steps"><p className="eyebrow">Break it down</p>
    {steps.map((step, index) => <div className="step-row" key={step.id}>
      <input type="checkbox" aria-label={`Complete step: ${step.title}`} checked={step.is_completed} disabled={action.pending} onChange={() => void action.run(() => api(`${path}/${step.id}`, 'PATCH', { is_completed: !step.is_completed }))} />
      <span className={step.is_completed ? 'struck' : ''}>{step.title}</span>
      <Button size="icon" variant="ghost" aria-label={`Move step up: ${step.title}`} disabled={index === 0 || action.pending} onClick={() => void action.run(() => api(`${path}/${step.id}`, 'PATCH', { position: steps[index - 1].position }))}><ArrowUp size={14} /></Button>
      <Button size="icon" variant="ghost" aria-label={`Move step down: ${step.title}`} disabled={index === steps.length - 1 || action.pending} onClick={() => void action.run(() => api(`${path}/${step.id}`, 'PATCH', { position: steps[index + 1].position }))}><ArrowDown size={14} /></Button>
      <Button size="icon" variant="ghost" aria-label={`Delete step: ${step.title}`} onClick={() => setDeleting(step)}><X size={14} /></Button>
    </div>)}
    <form className="step-form" onSubmit={event => { event.preventDefault(); if (title.trim()) void action.run(() => api(path, 'POST', { title: title.trim() }), () => setTitle('')) }}><Input aria-label={`New step for ${task.title}`} placeholder="Add a small step…" value={title} maxLength={300} onChange={e => setTitle(e.target.value)} /><Button size="icon" variant="outline" aria-label="Add step" disabled={action.pending || !title.trim()}><Plus size={17} /></Button></form>
    <ErrorMessage message={action.error} />
    {deleting && <ConfirmDelete title={deleting.title} onClose={() => setDeleting(null)} onDelete={() => api(`${path}/${deleting.id}`, 'DELETE')} />}
  </div>
}
