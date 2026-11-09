import { isHttpUrl } from '../../lib/notes'
import { isQuotaBoundCoverUrl } from '../../lib/covers'

/**
 * A small cover thumbnail. Only http(s) URLs are ever loaded; otherwise a quiet placeholder.
 * ISBN-addressed Open Library covers are temporarily shown as placeholders too (see
 * isQuotaBoundCoverUrl) so that rendering the Library cannot spend the rate-limit quota
 * enrichment depends on. Their URLs stay stored and come back the moment this check is removed.
 */
export function BookCover({ url, title, large }: { url: string | null; title: string; large?: boolean }) {
  const size = large ? 'book-cover book-cover-large' : 'book-cover'
  return isHttpUrl(url) && !isQuotaBoundCoverUrl(url)
    ? <img className={size} src={url} alt="" loading="lazy" referrerPolicy="no-referrer" />
    : <span className={`${size} book-cover-fallback`} aria-hidden="true">{title.trim().charAt(0).toUpperCase()}</span>
}
