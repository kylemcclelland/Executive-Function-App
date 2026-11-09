import { useState, type ChangeEvent } from 'react'
import { Link } from 'react-router-dom'
import { FileUp } from 'lucide-react'
import { api, apiUpload } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import type { ImportPreview, ImportResult } from '../../types'
import { Button, Dialog } from '../ui'
import { ErrorMessage } from '../common'

type Stage = { name: 'upload' } | { name: 'preview'; preview: ImportPreview; filename: string } | { name: 'results'; result: ImportResult }

const reasonText = { goodreads_id: 'same Goodreads ID', isbn: 'same ISBN', title_author: 'same title and author' } as const
const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`

function Stat({ value, label, quiet }: { value: number; label: string; quiet?: boolean }) {
  return <div className={`import-stat ${quiet && value === 0 ? 'is-quiet' : ''}`}><strong>{value}</strong><span>{label}</span></div>
}

export function ImportDialog({ onClose }: { onClose: () => void }) {
  const [stage, setStage] = useState<Stage>({ name: 'upload' })
  const [reading, setReading] = useState(false)
  const [error, setError] = useState('')
  const action = useAction()
  async function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setReading(true)
    setError('')
    try { setStage({ name: 'preview', preview: await apiUpload<ImportPreview>('/books/import/preview', file), filename: file.name }) }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not read that file.') }
    finally { setReading(false) }
  }
  function leave() {
    if (stage.name === 'preview') void api(`/books/import/${stage.preview.token}`, 'DELETE').catch(() => undefined)
    onClose()
  }
  return <Dialog open onOpenChange={open => { if (!open && !action.pending && !reading) leave() }} title={stage.name === 'results' ? 'Import complete' : stage.name === 'preview' ? 'Preview your import' : 'Import books'} description={stage.name === 'upload' ? 'Add books from a Goodreads export. Only bibliographic details are read.' : undefined}>
    {stage.name === 'upload' && <div className="import-stage">
      <ol className="import-steps"><li>On Goodreads, open <strong>My Books</strong>, then <strong>Import and export</strong>, then <strong>Export Library</strong>.</li><li>Choose the downloaded CSV file here.</li><li>Review a preview. Nothing is added until you confirm.</li></ol>
      <label className={`file-drop ${reading ? 'is-busy' : ''}`}><FileUp size={22} /><span>{reading ? 'Reading your file…' : 'Choose a Goodreads CSV file'}</span><input type="file" accept=".csv,text/csv" aria-label="Goodreads CSV file" disabled={reading} onChange={event => void choose(event)} /></label>
      <p className="muted small">Ratings, shelves, reading dates and reviews are not imported. Books already in your library are matched, never duplicated.</p>
      <ErrorMessage message={error} />
      <div className="dialog-actions"><Button variant="outline" onClick={onClose} disabled={reading}>Cancel</Button></div>
    </div>}
    {stage.name === 'preview' && (() => {
      const { preview } = stage
      const { counts } = preview
      const nothing = counts.to_add === 0 && counts.to_update === 0
      const concerns = preview.problems.filter(problem => problem.kind !== 'warning')
      return <div className="import-stage">
        <p className="import-banner" role="status"><strong>Preview.</strong> Nothing has been imported yet. <span className="muted">From {stage.filename}</span></p>
        <div className="import-stats"><Stat value={counts.to_add} label="to add" /><Stat value={counts.matched} label="already in library" /><Stat value={counts.to_update} label="gain missing details" quiet /><Stat value={counts.duplicates + counts.ambiguous + counts.invalid} label="skipped" quiet /></div>
        <p className="muted small">{plural(counts.total_rows, 'row', 'rows')} in the file{counts.duplicates > 0 && ` · ${plural(counts.duplicates, 'repeat', 'repeats')}`}{counts.ambiguous > 0 && ` · ${plural(counts.ambiguous, 'ambiguous match', 'ambiguous matches')}`}{counts.invalid > 0 && ` · ${plural(counts.invalid, 'unusable row', 'unusable rows')}`}</p>
        {preview.warnings.map(warning => <p key={warning} className="import-note">{warning}</p>)}
        {preview.sample_new.length > 0 && <><h3 className="import-heading">Books to add{counts.to_add > preview.sample_new.length && ` (first ${preview.sample_new.length})`}</h3><ul className="import-list">{preview.sample_new.map((book, index) => <li key={`${book.title}-${index}`}><strong>{book.title}</strong><span className="muted small">{[book.authors.join(', '), book.year].filter(Boolean).join(' · ')}</span></li>)}</ul></>}
        {preview.sample_matched.length > 0 && <><h3 className="import-heading">Already in your library</h3><ul className="import-list">{preview.sample_matched.map(book => <li key={book.book_id}><strong>{book.title}</strong><span className="muted small">Matched by {reasonText[book.reason]}{book.fills.length > 0 && ` · will fill in ${book.fills.join(', ').replaceAll('_', ' ')}`}</span></li>)}</ul></>}
        {concerns.length > 0 && <><h3 className="import-heading">Skipped</h3><ul className="import-list">{concerns.slice(0, 8).map((problem, index) => <li key={index}><strong>{problem.title ?? `Row ${problem.row}`}</strong><span className="muted small">{problem.message}</span></li>)}</ul></>}
        {nothing && <p className="import-note">Everything in this file is already in your library, so there is nothing to import.</p>}
        <ErrorMessage message={action.error} />
        <div className="dialog-actions"><Button variant="outline" onClick={leave} disabled={action.pending}>Cancel</Button>
          <Button disabled={nothing || action.pending} onClick={() => void action.run(() => api<ImportResult>('/books/import/confirm', 'POST', { token: preview.token }), result => setStage({ name: 'results', result }))}>{action.pending ? 'Importing…' : nothing ? 'Nothing to import' : counts.to_add > 0 ? `Import ${plural(counts.to_add, 'book', 'books')}` : 'Fill in missing details'}</Button></div>
      </div>
    })()}
    {stage.name === 'results' && <div className="import-stage">
      <p className="import-banner is-done" role="status"><strong>Done.</strong> Your library has been updated.</p>
      <div className="import-stats"><Stat value={stage.result.summary.added} label="added" /><Stat value={stage.result.summary.matched} label="already there" /><Stat value={stage.result.summary.updated} label="details filled in" quiet /><Stat value={stage.result.summary.skipped} label="skipped" quiet /></div>
      {stage.result.books.length > 0 && <><h3 className="import-heading">Open a book</h3><ul className="import-list">{stage.result.books.slice(0, 8).map(book => <li key={book.id}><Link to={`/library/${book.id}`} onClick={onClose}>{book.title}</Link><span className="muted small">{book.action === 'added' ? 'Added' : 'Details filled in'}</span></li>)}</ul></>}
      {stage.result.problems.length > 0 && <><h3 className="import-heading">Skipped</h3><ul className="import-list">{stage.result.problems.slice(0, 6).map((problem, index) => <li key={index}><strong>{problem.title ?? `Row ${problem.row}`}</strong><span className="muted small">{problem.message}</span></li>)}</ul></>}
      <p className="muted small">Use “Find missing covers” on the Library page to look for cover images.</p>
      <div className="dialog-actions"><Button onClick={onClose}>Done</Button></div>
    </div>}
  </Dialog>
}
