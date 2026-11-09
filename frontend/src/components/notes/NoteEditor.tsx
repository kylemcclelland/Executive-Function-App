import { useState, type FormEvent } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { noteTypes } from '../../lib/notes'
import type { Book, BookPage, LibraryNote, NoteType, Project } from '../../types'
import { Button, Dialog, Input } from '../ui'
import { ErrorMessage } from '../common'
import { Markdown } from '../Markdown'
import { TagInput } from './TagInput'

const PICKER_SIZE = 25

/** Links a note to a book without loading the whole library: search, then choose from the top matches. */
function BookPicker({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const [search, setSearch] = useState('')
  const term = search.trim()
  const results = useQuery({ queryKey: ['books', 'picker', term], queryFn: () => api<BookPage>(`/books?page_size=${PICKER_SIZE}${term ? `&q=${encodeURIComponent(term)}` : ''}`), placeholderData: keepPreviousData })
  const chosen = useQuery({ queryKey: ['book', value], queryFn: () => api<Book>(`/books/${value}`), enabled: value !== '' })
  const options = [...(results.data?.items ?? [])]
  if (chosen.data && !options.some(book => book.id === chosen.data.id)) options.unshift(chosen.data)
  const more = (results.data?.total ?? 0) - (results.data?.items.length ?? 0)
  return <div className="book-picker">
    <label>Book<select className="input" value={value} onChange={e => onChange(e.target.value)}><option value="">No book</option>{options.map(book => <option key={book.id} value={book.id}>{book.title}</option>)}</select></label>
    <Input aria-label="Search books to link" placeholder="Search your books…" value={search} onChange={e => setSearch(e.target.value)} />
    {more > 0 && <span className="muted small">{more.toLocaleString()} more {more === 1 ? 'book matches' : 'books match'}. Type to narrow the list.</span>}
  </div>
}

export function NoteEditor({ note, defaults, onClose, onSaved }: { note?: LibraryNote; defaults?: { book_id?: string; project_id?: string }; onClose: () => void; onSaved?: (note: LibraryNote) => void }) {
  const [title, setTitle] = useState(note?.title ?? '')
  const [noteType, setNoteType] = useState<NoteType>(note?.note_type ?? 'general')
  const [source, setSource] = useState(note?.source_location ?? '')
  const [bookId, setBookId] = useState(note ? note.book_id ?? '' : defaults?.book_id ?? '')
  const [projectId, setProjectId] = useState(note ? note.project_id ?? '' : defaults?.project_id ?? '')
  const [tags, setTags] = useState<string[]>(note?.tags ?? [])
  const [content, setContent] = useState(note?.content ?? '')
  const [previewing, setPreviewing] = useState(false)
  const action = useAction()
  const projects = useQuery({ queryKey: ['projects', 'picker'], queryFn: () => api<Project[]>('/projects') })
  const hint = noteTypes.find(type => type.value === noteType)?.hint
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) return
    const body = { title: title.trim(), note_type: noteType, content, source_location: source.trim() || null, book_id: bookId || null, project_id: projectId || null, tags }
    void action.run(() => api<LibraryNote>(note ? `/notes/${note.id}` : '/notes', note ? 'PATCH' : 'POST', body), saved => { onSaved?.(saved); onClose() })
  }
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title={note ? 'Edit note' : 'A new note'} description="Markdown is supported. Line breaks are kept.">
    <form onSubmit={submit} className="form-grid">
      <label className="full">Title<Input autoFocus required maxLength={300} value={title} onChange={e => setTitle(e.target.value)} /></label>
      <label>Type<select className="input" value={noteType} onChange={e => setNoteType(e.target.value as NoteType)}>{noteTypes.map(type => <option key={type.value} value={type.value}>{type.label}</option>)}</select></label>
      <label>Source (page, chapter, section…)<Input maxLength={300} value={source} onChange={e => setSource(e.target.value)} placeholder="e.g. ST I–II, q. 1, a. 8" /></label>
      <p className="full muted note-type-hint">{hint}</p>
      <BookPicker value={bookId} onChange={setBookId} />
      <label>Project<select className="input" value={projectId} onChange={e => setProjectId(e.target.value)}><option value="">No project</option>{projects.data?.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
      <div className="full"><TagInput value={tags} onChange={setTags} /></div>
      <div className="full"><div className="editor-tabs" role="group" aria-label="Note view"><Button type="button" size="sm" variant={previewing ? 'ghost' : 'outline'} aria-pressed={!previewing} onClick={() => setPreviewing(false)}>Write</Button><Button type="button" size="sm" variant={previewing ? 'outline' : 'ghost'} aria-pressed={previewing} onClick={() => setPreviewing(true)}>Preview</Button></div>
        {previewing ? <div className="input note-preview">{content.trim() ? <Markdown>{content}</Markdown> : <p className="muted">Nothing to preview yet.</p>}</div>
          : <label className="sr-label"><span className="sr-only">Note</span><textarea className="input note-textarea" rows={10} maxLength={200000} value={content} onChange={e => setContent(e.target.value)} /></label>}</div>
      <div className="full"><ErrorMessage message={action.error} /></div>
      <div className="dialog-actions full"><Button variant="outline" type="button" onClick={onClose} disabled={action.pending}>Cancel</Button><Button disabled={action.pending || !title.trim()}>{action.pending ? 'Saving…' : 'Save note'}</Button></div>
    </form>
  </Dialog>
}
