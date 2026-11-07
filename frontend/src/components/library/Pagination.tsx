import { ChevronLeft, ChevronRight } from 'lucide-react'
import { pageWindow } from '../../lib/pagination'
import { Button } from '../ui'

export function Pagination({ page, pageSize, total, totalPages, onPage }: { page: number; pageSize: number; total: number; totalPages: number; onPage: (page: number) => void }) {
  if (total === 0) return null
  const first = (page - 1) * pageSize + 1
  const last = Math.min(page * pageSize, total)
  return <nav className="pagination" aria-label="Library pages">
    <p className="pagination-summary" aria-live="polite">Showing {first.toLocaleString()}–{last.toLocaleString()} of {total.toLocaleString()} {total === 1 ? 'book' : 'books'}</p>
    {totalPages > 1 && <div className="pagination-controls">
      <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)}><ChevronLeft size={14} />Previous</Button>
      <ol className="pagination-pages">{pageWindow(page, totalPages).map((entry, index) => <li key={entry === 'gap' ? `gap-${index}` : entry}>{entry === 'gap' ? <span aria-hidden="true">…</span> : <Button size="sm" variant={entry === page ? 'default' : 'ghost'} aria-label={`Page ${entry}`} aria-current={entry === page ? 'page' : undefined} onClick={() => onPage(entry)}>{entry}</Button>}</li>)}</ol>
      <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>Next<ChevronRight size={14} /></Button>
    </div>}
  </nav>
}
