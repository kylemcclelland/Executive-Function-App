import { Book } from 'lucide-react'
import { coverColor } from '../../lib/covers'

/**
 * A generated clothbound-style cover: one muted solid colour per book, a small outline book
 * icon, and (at readable sizes) the centred title and author in warm ivory. No image is ever
 * fetched; the stored cover URLs remain untouched in the database. The colour is a stable
 * hash of the book's id (see lib/covers), identical across page loads and devices.
 */

/** Longer titles step down in size so they stay legible without clipping. */
function titleSize(title: string): string {
  const length = title.trim().length
  return length <= 14 ? '14px' : length <= 28 ? '12px' : length <= 48 ? '11px' : '10px'
}

export function BookCover({ bookId, title, author, size = 'list', className }: {
  bookId: string
  title: string
  author?: string | null
  size?: 'list' | 'detail'
  className?: string
}) {
  const classes = ['book-cover', `book-cover-${size}`, className].filter(Boolean).join(' ')
  // The title and author always sit beside the cover as real text, so the cover is decorative.
  return <span className={classes} style={{ backgroundColor: coverColor(bookId) }} aria-hidden="true">
    <Book className="book-cover-icon" aria-hidden="true" />
    {size !== 'list' && <>
      <span className="book-cover-title" style={{ fontSize: titleSize(title) }}>{title}</span>
      {author ? <span className="book-cover-author">{author}</span> : null}
    </>}
  </span>
}
