import { isHttpUrl } from '../../lib/notes'

/** A small cover thumbnail. Only http(s) URLs are ever loaded; otherwise a quiet placeholder. */
export function BookCover({ url, title, large }: { url: string | null; title: string; large?: boolean }) {
  const size = large ? 'book-cover book-cover-large' : 'book-cover'
  return isHttpUrl(url)
    ? <img className={size} src={url} alt="" loading="lazy" referrerPolicy="no-referrer" />
    : <span className={`${size} book-cover-fallback`} aria-hidden="true">{title.trim().charAt(0).toUpperCase()}</span>
}
