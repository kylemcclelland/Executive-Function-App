import { useState, type FormEvent } from 'react'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import type { Book } from '../../types'
import { Button, Dialog, Input } from '../ui'
import { ErrorMessage } from '../common'

export function BookEditor({ book, onClose, onSaved }: { book?: Book; onClose: () => void; onSaved?: (book: Book) => void }) {
  const [title, setTitle] = useState(book?.title ?? '')
  const [authors, setAuthors] = useState(book?.authors.join('\n') ?? '')
  const [isbn10, setIsbn10] = useState(book?.isbn_10 ?? '')
  const [isbn13, setIsbn13] = useState(book?.isbn_13 ?? '')
  const [year, setYear] = useState(book?.publication_year?.toString() ?? '')
  const [publisher, setPublisher] = useState(book?.publisher ?? '')
  const [edition, setEdition] = useState(book?.edition ?? '')
  const [coverUrl, setCoverUrl] = useState(book?.cover_url ?? '')
  const [goodreadsId, setGoodreadsId] = useState(book?.goodreads_id ?? '')
  const [description, setDescription] = useState(book?.description ?? '')
  const action = useAction()
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) return
    const body = {
      title: title.trim(), authors: authors.split('\n').map(name => name.trim()).filter(Boolean),
      isbn_10: isbn10.trim() || null, isbn_13: isbn13.trim() || null, publication_year: year.trim() ? Number(year) : null,
      publisher: publisher.trim() || null, edition: edition.trim() || null, cover_url: coverUrl.trim() || null,
      goodreads_id: goodreadsId.trim() || null, description: description.trim() || null,
    }
    void action.run(() => api<Book>(book ? `/books/${book.id}` : '/books', book ? 'PATCH' : 'POST', body), saved => { onSaved?.(saved); onClose() })
  }
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title={book ? 'Edit book' : 'Add a book'} description="Only a title is needed. Everything else can wait.">
    <form onSubmit={submit} className="form-grid">
      <label className="full">Title<Input autoFocus required maxLength={300} value={title} onChange={e => setTitle(e.target.value)} /></label>
      <label className="full">Author or authors<textarea className="input" rows={2} value={authors} onChange={e => setAuthors(e.target.value)} placeholder="One author per line" /></label>
      <label>ISBN-10<Input maxLength={13} value={isbn10} onChange={e => setIsbn10(e.target.value)} placeholder="Optional" /></label>
      <label>ISBN-13<Input maxLength={17} value={isbn13} onChange={e => setIsbn13(e.target.value)} placeholder="Optional" /></label>
      <label>Publication year<Input type="number" min={-3000} max={2200} value={year} onChange={e => setYear(e.target.value)} placeholder="Optional" /></label>
      <label>Publisher<Input maxLength={200} value={publisher} onChange={e => setPublisher(e.target.value)} placeholder="Optional" /></label>
      <label className="full">Edition or volume<Input maxLength={200} value={edition} onChange={e => setEdition(e.target.value)} placeholder="e.g. Vol. 2, Benziger translation" /></label>
      <label className="full">Cover image URL<Input type="url" maxLength={2000} value={coverUrl} onChange={e => setCoverUrl(e.target.value)} placeholder="https://… (optional)" /></label>
      <label className="full">Goodreads book ID<Input maxLength={50} value={goodreadsId} onChange={e => setGoodreadsId(e.target.value)} placeholder="Optional, kept for future importing" /></label>
      <label className="full">Description<textarea className="input" rows={3} value={description} onChange={e => setDescription(e.target.value)} placeholder="Optional" /></label>
      <div className="full"><ErrorMessage message={action.error} /></div>
      <div className="dialog-actions full"><Button variant="outline" type="button" onClick={onClose} disabled={action.pending}>Cancel</Button><Button disabled={action.pending || !title.trim()}>{action.pending ? 'Saving…' : book ? 'Save changes' : 'Add book'}</Button></div>
    </form>
  </Dialog>
}
