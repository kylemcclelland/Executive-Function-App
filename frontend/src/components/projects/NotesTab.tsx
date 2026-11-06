import { useState, type FormEvent } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { formatDateTime } from '../../lib/projects'
import type { Project, ProjectNote } from '../../types'
import { Button, Card, Dialog, Input } from '../ui'
import { ConfirmDelete, Empty, ErrorMessage, Loading } from '../common'

function NoteEditor({ projectId, note, onClose }: { projectId: string; note?: ProjectNote; onClose: () => void }) {
  const [title, setTitle] = useState(note?.title ?? '')
  const [content, setContent] = useState(note?.content ?? '')
  const action = useAction()
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!content.trim()) return
    const body = { title: title.trim() || null, content }
    void action.run(() => api(note ? `/projects/${projectId}/notes/${note.id}` : `/projects/${projectId}/notes`, note ? 'PATCH' : 'POST', body), onClose)
  }
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title={note ? 'Edit note' : 'A new note'} description="Save what you want to find again later.">
    <form onSubmit={submit} className="form-grid">
      <label className="full">Title<Input maxLength={300} value={title} onChange={e => setTitle(e.target.value)} placeholder="Optional" /></label>
      <label className="full">Note<textarea autoFocus required className="input" rows={8} maxLength={100000} value={content} onChange={e => setContent(e.target.value)} /></label>
      <div className="full"><ErrorMessage message={action.error} /></div>
      <div className="dialog-actions full"><Button variant="outline" type="button" onClick={onClose} disabled={action.pending}>Cancel</Button><Button disabled={action.pending || !content.trim()}>{action.pending ? 'Saving…' : 'Save note'}</Button></div>
    </form>
  </Dialog>
}

function NoteCard({ projectId, note }: { projectId: string; note: ProjectNote }) {
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const label = note.title ?? note.content.slice(0, 40)
  return <article className="note-entry"><div className="note-head"><h3>{note.title ?? 'Untitled note'}</h3><div className="task-actions">
    <Button variant="ghost" size="icon" aria-label={`Edit note: ${label}`} onClick={() => setEditing(true)}><Pencil size={15} /></Button>
    <Button variant="ghost" size="icon" aria-label={`Delete note: ${label}`} onClick={() => setDeleting(true)}><Trash2 size={15} /></Button></div></div>
    <p className="preserve-lines">{note.content}</p><span className="muted small">Updated {formatDateTime(note.updated_at)}</span>
    {editing && <NoteEditor projectId={projectId} note={note} onClose={() => setEditing(false)} />}
    {deleting && <ConfirmDelete title={label} onClose={() => setDeleting(false)} onDelete={() => api(`/projects/${projectId}/notes/${note.id}`, 'DELETE')} />}
  </article>
}

export function NotesTab({ project }: { project: Project }) {
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const term = search.trim()
  const query = useQuery({ queryKey: ['project-notes', project.id, term], queryFn: () => api<ProjectNote[]>(`/projects/${project.id}/notes${term ? `?q=${encodeURIComponent(term)}` : ''}`), placeholderData: keepPreviousData })
  return <div>
    <div className="task-toolbar"><Input aria-label="Search notes" placeholder="Search this project’s notes…" value={search} onChange={e => setSearch(e.target.value)} /><Button onClick={() => setCreating(true)}><Plus size={17} />New note</Button></div>
    <Card>{query.isPending ? <Loading /> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></> : query.data.length ? query.data.map(note => <NoteCard key={note.id} projectId={project.id} note={note} />) : <Empty title={term ? 'Nothing matches just yet' : 'A place for what you learn'}>{term ? 'Try another word, or clear your search.' : 'Links, ideas, research, decisions. Anything you’ll want to find again.'}</Empty>}</Card>
    {creating && <NoteEditor projectId={project.id} onClose={() => setCreating(false)} />}
  </div>
}
