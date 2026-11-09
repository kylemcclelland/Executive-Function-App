import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BookMarked, FolderOpen, Link2, Pencil, Trash2, Unlink } from 'lucide-react'
import { api, ApiError } from '../../services/api'
import { connectionLabel, noteTypeLabel } from '../../lib/notes'
import { formatDateTime } from '../../lib/projects'
import type { Connection, LibraryNote } from '../../types'
import { Button, Card } from '../ui'
import { ConfirmDelete, Empty, ErrorMessage, Loading } from '../common'
import { Markdown } from '../Markdown'
import { NoteEditor } from './NoteEditor'
import { ConnectDialog, RemoveConnectionDialog } from './ConnectDialog'

function Connections({ note }: { note: LibraryNote }) {
  const [connecting, setConnecting] = useState(false)
  const [removing, setRemoving] = useState<Connection | null>(null)
  const query = useQuery({ queryKey: ['note-connections', note.id], queryFn: () => api<Connection[]>(`/notes/${note.id}/connections`) })
  const connections = query.data ?? []
  return <section className="connections" aria-labelledby="connections-heading">
    <div className="section-heading"><h3 id="connections-heading">Connections</h3><Button size="sm" variant="outline" onClick={() => setConnecting(true)}><Link2 size={14} />Connect an Idea</Button></div>
    {query.isPending ? <Loading /> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" size="sm" onClick={() => void query.refetch()}>Try again</Button></> : connections.length ? <ul className="connection-list">{connections.map(connection => {
      const label = connectionLabel(connection)
      return <li key={connection.id} className="connection-item">
        <div><p className="connection-label"><span className="tag">{label}</span> <Link to={`/notes/${connection.note.id}`} className="connection-link">{connection.note.title}</Link></p>
          <p className="muted small">{noteTypeLabel(connection.note.note_type)}{connection.note.book_title ? ` · ${connection.note.book_title}` : ''}</p>
          {connection.explanation && <p className="preserve-lines connection-why">{connection.explanation}</p>}</div>
        <Button variant="ghost" size="icon" aria-label={`Remove connection: ${label} ${connection.note.title}`} onClick={() => setRemoving(connection)}><Unlink size={15} /></Button>
      </li>
    })}</ul> : <p className="muted">No connections yet. Link this note to an idea it supports, develops, answers or contradicts.</p>}
    {connecting && <ConnectDialog note={note} connections={connections} onClose={() => setConnecting(false)} />}
    {removing && <RemoveConnectionDialog linkId={removing.id} label={connectionLabel(removing)} title={removing.note.title} onClose={() => setRemoving(null)} />}
  </section>
}

export function NoteView({ noteId }: { noteId: string }) {
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const query = useQuery({ queryKey: ['note', noteId], queryFn: () => api<LibraryNote>(`/notes/${noteId}`), retry: false })
  if (query.isPending) return <Loading />
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404
    return <Card><Empty title={missing ? 'We couldn’t find that note' : 'Something went wrong'}>{missing ? 'It may have been deleted.' : query.error.message}</Empty>{!missing && <Button variant="outline" onClick={() => void query.refetch()}>Try again</Button>}</Card>
  }
  const note = query.data
  const attribution = [note.book_title, note.source_location].filter(Boolean).join(', ')
  return <Card className={`note-view note-type-${note.note_type}`}>
    <div className="note-view-head">
      <div><p className="eyebrow">{noteTypeLabel(note.note_type).toUpperCase()}</p><h2 className="note-view-title">{note.title}</h2></div>
      <div className="task-actions"><Button variant="ghost" size="icon" aria-label={`Edit note: ${note.title}`} onClick={() => setEditing(true)}><Pencil size={15} /></Button><Button variant="ghost" size="icon" aria-label={`Delete note: ${note.title}`} onClick={() => setDeleting(true)}><Trash2 size={15} /></Button></div>
    </div>
    <div className="note-context">
      {note.book_id && <Link to={`/library/${note.book_id}`}><BookMarked size={13} />{note.book_title}</Link>}
      {!note.book_id && note.former_book && <span className="muted"><BookMarked size={13} />Formerly from {note.former_book}</span>}
      {note.project_id && <Link to={`/projects/${note.project_id}`}><FolderOpen size={13} />{note.project_name}</Link>}
      {note.source_location && <span className="note-source">{note.source_location}</span>}
      {note.tags.map(tag => <span key={tag} className="note-tag">#{tag}</span>)}
    </div>
    {note.content.trim() ? note.note_type === 'quotation' ? <figure className="quotation"><blockquote><Markdown>{note.content}</Markdown></blockquote>{attribution && <figcaption>— {attribution}</figcaption>}</figure> : <Markdown>{note.content}</Markdown> : <p className="muted">No text yet.</p>}
    <p className="muted small note-dates">Written {formatDateTime(note.created_at)}{note.updated_at !== note.created_at && ` · Edited ${formatDateTime(note.updated_at)}`}</p>
    <Connections note={note} />
    {editing && <NoteEditor note={note} onClose={() => setEditing(false)} />}
    {deleting && <ConfirmDelete title={note.title} onClose={() => setDeleting(false)} onDelete={async () => { await api(`/notes/${note.id}`, 'DELETE'); navigate('/notes') }} />}
  </Card>
}
