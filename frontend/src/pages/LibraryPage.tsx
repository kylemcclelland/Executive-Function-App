import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Pencil, Plus, Trash2 } from 'lucide-react'
import { Button, Card, Dialog, Input } from '../components/ui'
import { Empty, ErrorMessage, Loading, PageHeader } from '../components/common'
import { BookCover } from '../components/library/BookCover'
import { BookEditor } from '../components/library/BookEditor'
import { NoteCard } from '../components/notes/NoteCard'
import { NoteEditor } from '../components/notes/NoteEditor'
import { api, ApiError } from '../services/api'
import { useAction } from '../hooks/useAction'
import { authorLine } from '../lib/notes'
import type { Book, NoteBrief } from '../types'

function DeleteBookDialog({ book, onClose, onDeleted }: { book: Book; onClose: () => void; onDeleted: () => void }) {
  const action = useAction()
  const notes = book.note_count
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title="Delete this book?" description={`“${book.title}” will be removed from your library.`}>
    <p className="muted">{notes ? `Its ${notes} ${notes === 1 ? 'note' : 'notes'} will be kept. They will no longer be linked to this book, but will remember its title.` : 'It has no notes.'}</p>
    <ErrorMessage message={action.error} />
    <div className="dialog-actions"><Button variant="outline" onClick={onClose} disabled={action.pending}>Keep it</Button><Button variant="destructive" disabled={action.pending} onClick={() => void action.run(() => api(`/books/${book.id}${notes ? '?keep_notes=true' : ''}`, 'DELETE'), () => { onClose(); onDeleted() })}>{action.pending ? 'Deleting…' : 'Delete book'}</Button></div>
  </Dialog>
}

function BookDetail({ bookId, onDeleted }: { bookId: string; onDeleted: () => void }) {
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [writing, setWriting] = useState(false)
  const query = useQuery({ queryKey: ['book', bookId], queryFn: () => api<Book>(`/books/${bookId}`), retry: false })
  const notesQuery = useQuery({ queryKey: ['book-notes', bookId], queryFn: () => api<NoteBrief[]>(`/notes?book_id=${bookId}`) })
  if (query.isPending) return <Loading />
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404
    return <Card><Empty title={missing ? 'We couldn’t find that book' : 'Something went wrong'}>{missing ? 'It may have been deleted.' : query.error.message}</Empty></Card>
  }
  const book = query.data
  const facts: [string, string | number | null][] = [['ISBN-10', book.isbn_10], ['ISBN-13', book.isbn_13], ['Published', book.publication_year], ['Publisher', book.publisher], ['Edition', book.edition], ['Goodreads ID', book.goodreads_id]]
  const notes = notesQuery.data ?? []
  return <div className="book-detail">
    <Card className="book-card">
      <Link to="/library" className="back-link"><ArrowLeft size={14} />All books</Link>
      <div className="book-head">
        <BookCover url={book.cover_url} title={book.title} large />
        <div className="book-head-text"><h2 className="book-title">{book.title}</h2>{book.authors.length > 0 && <p className="book-authors">{authorLine(book.authors)}</p>}
          <div className="task-actions"><Button variant="ghost" size="sm" aria-label={`Edit book: ${book.title}`} onClick={() => setEditing(true)}><Pencil size={14} />Edit</Button><Button variant="ghost" size="sm" aria-label={`Delete book: ${book.title}`} onClick={() => setDeleting(true)}><Trash2 size={14} />Delete</Button></div></div>
      </div>
      {facts.some(([, value]) => value) && <dl className="book-facts">{facts.filter(([, value]) => value).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}
      {book.description && <p className="preserve-lines book-description">{book.description}</p>}
    </Card>
    <Card className="book-notes">
      <div className="section-heading"><h2>Notes from this book <span className="count">{notes.length}</span></h2><Button size="sm" onClick={() => setWriting(true)}><Plus size={15} />Add Note</Button></div>
      {notesQuery.isPending ? <Loading /> : notesQuery.isError ? <ErrorMessage message={notesQuery.error.message} /> : notes.length ? <div className="note-card-list">{notes.map(note => <NoteCard key={note.id} note={note} showBook={false} />)}</div> : <Empty title="No notes yet">Add a quotation, a summary of an argument, or your own reflection.</Empty>}
    </Card>
    {editing && <BookEditor book={book} onClose={() => setEditing(false)} />}
    {deleting && <DeleteBookDialog book={book} onClose={() => setDeleting(false)} onDeleted={onDeleted} />}
    {writing && <NoteEditor defaults={{ book_id: book.id }} onClose={() => setWriting(false)} />}
  </div>
}

export function LibraryPage() {
  const { bookId } = useParams()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [adding, setAdding] = useState(false)
  const term = search.trim()
  const query = useQuery({ queryKey: ['books', term], queryFn: () => api<Book[]>(`/books${term ? `?q=${encodeURIComponent(term)}` : ''}`), placeholderData: keepPreviousData })
  const books = query.data ?? []
  return <><PageHeader eyebrow="YOUR LIBRARY" title="Library" action={<Button onClick={() => setAdding(true)}><Plus size={17} />Add a book</Button>}>Books worth keeping, and the thinking they prompt.</PageHeader>
    <div className="library-layout">
      <aside className={`library-list ${bookId ? 'has-selection' : ''}`} aria-label="Your books">
        <Input aria-label="Search books" placeholder="Search title, author, publisher, ISBN…" value={search} onChange={e => setSearch(e.target.value)} />
        {query.isPending ? <Loading /> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></> : books.length ? <div className="book-list">{books.map(book => <Link key={book.id} to={`/library/${book.id}`} className={`book-item ${book.id === bookId ? 'is-selected' : ''}`} aria-current={book.id === bookId ? 'true' : undefined}>
          <BookCover url={book.cover_url} title={book.title} />
          <span className="book-item-text"><strong>{book.title}</strong>{book.authors.length > 0 && <span className="muted small">{authorLine(book.authors)}</span>}</span>
          <span className="count" aria-label={`${book.note_count} ${book.note_count === 1 ? 'note' : 'notes'}`}>{book.note_count}</span>
        </Link>)}</div> : <Empty title={term ? 'Nothing matches just yet' : 'Your library is empty'}>{term ? 'Try another word, or clear your search.' : 'Add a book to begin. A title is all you need.'}</Empty>}
      </aside>
      <section className="library-detail" aria-label="Book">
        {bookId ? <BookDetail key={bookId} bookId={bookId} onDeleted={() => navigate('/library')} /> : <Empty title="Choose a book">Select a book to see its details and the notes you have written about it.</Empty>}
      </section>
    </div>
    {adding && <BookEditor onClose={() => setAdding(false)} onSaved={book => navigate(`/library/${book.id}`)} />}
  </>
}
