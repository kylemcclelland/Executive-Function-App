import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BookOpen } from 'lucide-react'
import { Card } from '../ui'
import { api } from '../../services/api'
import { noteTypeLabel } from '../../lib/notes'
import type { BookPage, NoteBrief } from '../../types'

/**
 * Reading and intellectual life. The library deliberately tracks no reading status or progress,
 * so this shows what the data does support: the newest books and the most recently edited notes.
 */
export function ReadingCard() {
  const books = useQuery({ queryKey: ['today-books'], queryFn: () => api<BookPage>('/books?page_size=3&sort=recent'), retry: false })
  const notes = useQuery({ queryKey: ['today-notes'], queryFn: () => api<NoteBrief[]>('/notes?limit=3'), retry: false })
  if (books.isError && notes.isError) return null
  const recentBooks = books.data?.items ?? []
  const recentNotes = notes.data ?? []
  const empty = books.data && notes.data && recentBooks.length === 0 && recentNotes.length === 0
  return <Card className="reading-card">
    <div className="section-title"><BookOpen size={17} /><h2>Reading &amp; notes</h2></div>
    {empty ? <p className="muted">Books you add and notes you write will gather here.</p> : <>
      {recentBooks.length > 0 && <section aria-label="Recently added books"><p className="eyebrow">RECENTLY ADDED</p>
        <ul className="reading-list">{recentBooks.map(book => <li key={book.id}><Link to={`/library/${book.id}`}><strong>{book.title}</strong>{book.authors.length > 0 && <small>{book.authors.join(', ')}</small>}</Link></li>)}</ul>
      </section>}
      {recentNotes.length > 0 && <section aria-label="Recent notes"><p className="eyebrow">LATEST NOTES</p>
        <ul className="reading-list">{recentNotes.map(note => <li key={note.id}><Link to={`/notes/${note.id}`}><strong>{note.title}</strong><small>{noteTypeLabel(note.note_type)}{note.book_title ? ` · ${note.book_title}` : ''}</small></Link></li>)}</ul>
      </section>}
    </>}
    <div className="previous-footer"><Link to="/library">Library{books.data ? ` (${books.data.total.toLocaleString()})` : ''} <ArrowRight size={13} /></Link> <Link to="/notes">Notes <ArrowRight size={13} /></Link></div>
  </Card>
}
