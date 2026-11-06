import { useState } from 'react'
import { Archive, ArrowRight, Pencil, RotateCcw, Trash2 } from 'lucide-react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import type { InboxItem } from '../../types'
import { formatDate } from '../../lib/utils'
import { Button, Dialog } from '../ui'
import { ConfirmDelete, ErrorMessage } from '../common'

export function InboxEntry({ item }: { item: InboxItem }) {
  const [editing, setEditing] = useState(false)
  const [content, setContent] = useState(item.content)
  const [deleting, setDeleting] = useState(false)
  const action = useAction()
  return <article className="inbox-entry"><span className="inbox-dot" /><div className="inbox-content"><p className="preserve-lines">{item.content}</p><span className="muted small">{formatDate(item.created_at)} · {item.status === 'unprocessed' ? 'Ready when you are' : item.status === 'processed' ? 'Processed · converted to a task' : 'Archived'}</span>
    <div className="entry-actions">{item.status === 'unprocessed' && <Button size="sm" variant="outline" disabled={action.pending} onClick={() => void action.run(() => api(`/inbox/${item.id}/convert-to-task`, 'POST', {}))}>Make a task <ArrowRight size={14} /></Button>}
      {item.status === 'unprocessed' && !item.converted_task_id && <Button size="sm" variant="ghost" onClick={() => setEditing(true)}><Pencil size={14} />Edit</Button>}
      {item.status !== 'archived' ? <Button size="sm" variant="ghost" disabled={action.pending} onClick={() => void action.run(() => api(`/inbox/${item.id}`, 'PATCH', { status: 'archived' }))}><Archive size={14} />Archive</Button> : <Button size="sm" variant="ghost" disabled={action.pending} onClick={() => void action.run(() => api(`/inbox/${item.id}`, 'PATCH', { status: 'unprocessed' }))}><RotateCcw size={14} />Restore</Button>}
      <Button size="sm" variant="ghost" onClick={() => setDeleting(true)} aria-label={`Delete thought: ${item.content}`}><Trash2 size={14} />Delete</Button></div><ErrorMessage message={action.error} /></div>
    {editing && <Dialog open onOpenChange={setEditing} title="Edit your thought" description="Keep the words that matter to you."><form onSubmit={e => { e.preventDefault(); if (content.trim()) void action.run(() => api(`/inbox/${item.id}`, 'PATCH', { content: content.trim() }), () => setEditing(false)) }}><label>Your thought<textarea className="input" rows={5} value={content} required maxLength={10000} onChange={e => setContent(e.target.value)} /></label><ErrorMessage message={action.error} /><div className="dialog-actions"><Button disabled={action.pending || !content.trim()}>Save thought</Button></div></form></Dialog>}
    {deleting && <ConfirmDelete title={item.content} onClose={() => setDeleting(false)} onDelete={() => api(`/inbox/${item.id}`, 'DELETE')} />}
  </article>
}
