import { useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { noteTypes } from '../../lib/notes'
import type { Book, LibraryNote, NoteType, Project } from '../../types'
import { Button, Dialog, Input } from '../ui'
import { ErrorMessage } from '../common'
import { Markdown } from '../Markdown'

export function NoteEditor({ note, defaults, onClose, onSaved }: { note?: LibraryNote; defaults?: { book_id?: string; project_id?: string }; onClose: () => void; onSaved?: (note: LibraryNote) => void }) {
  const [title, setTitle] = useState(note?.title ?? '')
  const [noteType, setNoteType] = useState<NoteType>(note?.note_type ?? 'general')
  const [source, setSource] = useState(note?.source_location ?? '')
  const [bookId, setBookId] = useState(note ? note.book_id ?? '' : defaults?.book_id ?? '')
  const [projectId, setProjectId] = useState(note ? note.project_id ?? '' : defaults?.project_id ?? '')
  const [tags, setTags] = useState(note?.tags.join(', ') ?? '')
  const [content, setContent] = useState(note?.content ?? '')
  const [previewing, setPreviewing] = useState(false)
  const action = useAction()
  const books = useQuery({ queryKey: ['books', ''], queryFn: () => api<Book[]>('/books') })
  const projects = useQuery({ queryKey: ['projects', 'picker'], queryFn: () => api<Project[]>('/projects') })
  const hint = noteTypes.find(type => type.value === noteType)?.hint
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) return
    const body = { title: title.trim(), note_type: noteType, content, source_location: source.trim() || null, book_id: bookId || null, project_id: projectId || null, tags: tags.split(',').map(tag => tag.trim()).filter(Boolean) }
    void action.run(() => api<LibraryNote>(note ? `/notes/${note.id}` : '/notes', note ? 'PATCH' : 'POST', body), saved => { onSaved?.(saved); onClose() })
  }
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title={note ? 'Edit note' : 'A new note'} description="Markdown is supported. Line breaks are kept.">
    <form onSubmit={submit} className="form-grid">
      <label className="full">Title<Input autoFocus required maxLength={300} value={title} onChange={e => setTitle(e.target.value)} /></label>
      <label>Type<select className="input" value={noteType} onChange={e => setNoteType(e.target.value as NoteType)}>{noteTypes.map(type => <option key={type.value} value={type.value}>{type.label}</option>)}</select></label>
      <label>Source (page, chapter, section…)<Input maxLength={300} value={source} onChange={e => setSource(e.target.value)} placeholder="e.g. ST I–II, q. 1, a. 8" /></label>
      <p className="full muted note-type-hint">{hint}</p>
      <label>Book<select className="input" value={bookId} onChange={e => setBookId(e.target.value)}><option value="">No book</option>{books.data?.map(book => <option key={book.id} value={book.id}>{book.title}</option>)}</select></label>
      <label>Project<select className="input" value={projectId} onChange={e => setProjectId(e.target.value)}><option value="">No project</option>{projects.data?.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
      <label className="full">Tags<Input value={tags} onChange={e => setTags(e.target.value)} placeholder="Comma-separated, optional" /></label>
      <div className="full"><div className="editor-tabs" role="group" aria-label="Note view"><Button type="button" size="sm" variant={previewing ? 'ghost' : 'outline'} aria-pressed={!previewing} onClick={() => setPreviewing(false)}>Write</Button><Button type="button" size="sm" variant={previewing ? 'outline' : 'ghost'} aria-pressed={previewing} onClick={() => setPreviewing(true)}>Preview</Button></div>
        {previewing ? <div className="input note-preview">{content.trim() ? <Markdown>{content}</Markdown> : <p className="muted">Nothing to preview yet.</p>}</div>
          : <label className="sr-label"><span className="sr-only">Note</span><textarea className="input note-textarea" rows={10} maxLength={200000} value={content} onChange={e => setContent(e.target.value)} /></label>}</div>
      <div className="full"><ErrorMessage message={action.error} /></div>
      <div className="dialog-actions full"><Button variant="outline" type="button" onClick={onClose} disabled={action.pending}>Cancel</Button><Button disabled={action.pending || !title.trim()}>{action.pending ? 'Saving…' : 'Save note'}</Button></div>
    </form>
  </Dialog>
}
