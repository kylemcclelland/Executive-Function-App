import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { Button, Input } from '../components/ui'
import { Empty, ErrorMessage, Loading, PageHeader } from '../components/common'
import { NoteCard } from '../components/notes/NoteCard'
import { NoteEditor } from '../components/notes/NoteEditor'
import { NoteView } from '../components/notes/NoteView'
import { api } from '../services/api'
import { noteTypes } from '../lib/notes'
import type { NoteBrief, NoteType } from '../types'

export function NotesPage() {
  const { noteId } = useParams()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [type, setType] = useState<NoteType | 'all'>('all')
  const [creating, setCreating] = useState(false)
  const params = new URLSearchParams()
  if (search.trim()) params.set('q', search.trim())
  if (type !== 'all') params.set('note_type', type)
  const query = useQuery({ queryKey: ['notes', params.toString()], queryFn: () => api<NoteBrief[]>(`/notes?${params}`), placeholderData: keepPreviousData })
  const notes = query.data ?? []
  const filtering = !!search.trim() || type !== 'all'
  return <><PageHeader eyebrow="YOUR COMMONPLACE BOOK" title="Notes" action={<Button onClick={() => setCreating(true)}><Plus size={17} />New note</Button>}>Quotations, summaries, reflections and questions, connected to each other.</PageHeader>
    <div className="notes-layout">
      <aside className={`notes-list ${noteId ? 'has-selection' : ''}`} aria-label="Your notes">
        <Input aria-label="Search notes" placeholder="Search titles, text, sources, tags…" value={search} onChange={e => setSearch(e.target.value)} />
        <div className="type-filters" role="group" aria-label="Filter by type">{[{ value: 'all', label: 'All' }, ...noteTypes].map(option => <Button key={option.value} size="sm" variant={type === option.value ? 'default' : 'ghost'} aria-pressed={type === option.value} onClick={() => setType(option.value as NoteType | 'all')}>{option.label}</Button>)}</div>
        {query.isPending ? <Loading /> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></> : notes.length ? <div className="note-card-list">{notes.map(note => <NoteCard key={note.id} note={note} selected={note.id === noteId} />)}</div> : <Empty title={filtering ? 'Nothing matches just yet' : 'No notes yet'}>{filtering ? 'Try another word, or clear the filters.' : 'Capture a quotation, a paraphrase, or a question. A title is all it needs.'}</Empty>}
      </aside>
      <section className="note-main" aria-label="Selected note">
        {noteId ? <NoteView key={noteId} noteId={noteId} /> : <Empty title="Choose a note to read">Or start a new one. Notes can stand on their own, or belong to a book or a project.</Empty>}
      </section>
    </div>
    {creating && <NoteEditor onClose={() => setCreating(false)} onSaved={note => navigate(`/notes/${note.id}`)} />}
  </>
}
