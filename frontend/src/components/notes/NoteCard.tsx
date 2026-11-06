import { Link } from 'react-router-dom'
import { FolderOpen, BookMarked } from 'lucide-react'
import { noteTypeLabel } from '../../lib/notes'
import type { NoteBrief } from '../../types'

/** One note in a list. Quotations are visibly distinct from paraphrases and reflections. */
export function NoteCard({ note, selected, showBook = true }: { note: NoteBrief; selected?: boolean; showBook?: boolean }) {
  return <Link to={`/notes/${note.id}`} className={`note-card note-type-${note.note_type} ${selected ? 'is-selected' : ''}`} aria-current={selected ? 'true' : undefined}>
    <span className="note-card-top"><span className="tag note-type-tag">{noteTypeLabel(note.note_type)}</span>{note.source_location && <span className="note-source">{note.source_location}</span>}</span>
    <strong className="note-card-title">{note.title}</strong>
    {note.excerpt && <span className={`note-card-excerpt ${note.note_type === 'quotation' ? 'is-quotation' : ''}`}>{note.excerpt}</span>}
    <span className="note-card-meta">
      {showBook && note.book_title && <span><BookMarked size={12} />{note.book_title}</span>}
      {note.project_name && <span><FolderOpen size={12} />{note.project_name}</span>}
      {note.tags.map(tag => <span key={tag} className="note-tag">#{tag}</span>)}
    </span>
  </Link>
}
