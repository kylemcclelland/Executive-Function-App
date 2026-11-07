import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import type { Book, CoverBatch, ImportPreview, ImportResult } from '../types'

const stamp = '2026-11-06T10:00:00Z'
const makeBook = (id: string, title: string, fields: Partial<Book> = {}): Book => ({
  id, title, authors: [], isbn_10: null, isbn_13: null, publication_year: null, publisher: null, edition: null, cover_url: null,
  goodreads_id: null, description: null, created_at: stamp, updated_at: stamp, note_count: 0, ...fields,
})
const previewBody = (fields: Partial<ImportPreview> = {}): ImportPreview => ({
  token: 'tok-1', expires_in_seconds: 900,
  counts: { total_rows: 5, to_add: 3, matched: 1, to_update: 1, duplicates: 1, ambiguous: 0, invalid: 0 },
  warnings: ['2 books have no Goodreads ID or ISBN, so they can only be matched by title and author.'],
  problems: [{ row: 4, title: 'The Republic', kind: 'duplicate', message: 'repeated in this file' }],
  sample_new: [{ title: 'Pensées', authors: ['Blaise Pascal'], year: 1670, goodreads_id: '11' }, { title: 'Confessions', authors: ['Augustine'], year: null, goodreads_id: '12' }],
  sample_matched: [{ title: 'Summa Theologiae', book_id: 'b1', reason: 'title_author', fills: ['goodreads_id', 'publication_year'] }],
  ...fields,
})
const resultBody: ImportResult = {
  summary: { added: 3, matched: 1, updated: 1, skipped: 1, duplicates: 1, ambiguous: 0, invalid: 0 },
  problems: [{ row: 4, title: 'The Republic', kind: 'duplicate', message: 'repeated in this file' }],
  books: [{ id: 'new-1', title: 'Pensées', action: 'added' }, { id: 'b1', title: 'Summa Theologiae', action: 'updated' }],
}

let books: Book[]
let previewResponse: () => Response
let confirmResponse: () => Response
let missing: number
let lookupStats: { found_lookups: number; not_found_lookups: number }
type Cooldown = { blocked_until: string | null; retry_after_seconds: number | null }
let cooldown: Cooldown
let enrich: (body: { limit: number; skip: string[] }, signal?: AbortSignal) => Promise<Response> | Response
const batch = (fields: Partial<CoverBatch> = {}): CoverBatch => ({ checked: 0, found: 0, not_found: 0, errors: 0, cached: 0, converted: 0, rate_limited: false, stopped_early: false, blocked_until: null, retry_after_seconds: null, checked_ids: [], remaining: 0, legacy_remaining: 0, ...fields })
const inMinutes = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString()
let queryClient: QueryClient
type RequestRecord = { url: string; method: string; body: unknown; contentType?: string }
let requests: RequestRecord[]
const response = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const withCount = (book: Book) => ({ ...book, note_count: 0 })

beforeEach(() => {
  books = [makeBook('b1', 'Summa Theologiae', { authors: ['Thomas Aquinas'] }), makeBook('b2', 'Meditations', { authors: ['Marcus Aurelius'], cover_url: 'https://example.com/m.jpg' })]
  previewResponse = () => response(previewBody())
  confirmResponse = () => { books.unshift(makeBook('new-1', 'Pensées', { authors: ['Blaise Pascal'] })); return response(resultBody) }
  missing = 0
  lookupStats = { found_lookups: 0, not_found_lookups: 0 }
  cooldown = { blocked_until: null, retry_after_seconds: null }
  enrich = () => response(batch())
  requests = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const url = new URL(input.replace('/api', ''), 'http://local')
    const method = options?.method ?? 'GET'
    const headers = (options?.headers ?? {}) as Record<string, string>
    const raw = options?.body
    const body = raw instanceof File ? `file:${raw.name}` : raw ? JSON.parse(raw as string) : undefined
    requests.push({ url: url.pathname + url.search, method, body, contentType: headers['Content-Type'] })
    const q = url.searchParams.get('q')?.toLowerCase()
    if (url.pathname === '/books') {
      const found = books.filter(b => !q || `${b.title} ${b.authors.join(' ')}`.toLowerCase().includes(q)).map(withCount)
      return response({ items: found, total: found.length, page: 1, page_size: 50, total_pages: found.length ? 1 : 0 })
    }
    if (url.pathname === '/books/import/preview') return previewResponse()
    if (url.pathname === '/books/import/confirm') return confirmResponse()
    if (url.pathname.startsWith('/books/import/') && method === 'DELETE') return response(null, 204)
    if (url.pathname === '/books/covers/missing') return response({ count: missing, with_covers: books.filter(b => b.cover_url).length, ...lookupStats, ...cooldown })
    if (url.pathname === '/books/covers/enrich') return enrich(body as { limit: number; skip: string[] }, options?.signal ?? undefined)
    return response({ detail: `Unhandled ${method} ${url.pathname}` }, 404)
  }))
})
afterEach(() => { queryClient.clear(); vi.unstubAllGlobals() })
function setup(path = '/library') {
  const user = userEvent.setup()
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
  return user
}
const csvFile = (name = 'goodreads_library_export.csv') => new File(['Book Id,Title,Author\n11,Pensées,Blaise Pascal\n'], name, { type: 'text/csv' })
const writes = () => requests.filter(r => r.method !== 'GET')
async function openImport(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'Import Books' }))
  return screen.findByRole('dialog')
}

describe('Importing from Goodreads', () => {
  it('starts with clear instructions and sends nothing until a file is chosen', async () => {
    const user = setup()
    const dialog = await openImport(user)
    expect(within(dialog).getByRole('heading', { name: 'Import books' })).toBeInTheDocument()
    expect(within(dialog).getByText(/Export Library/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Nothing is added until you confirm/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Ratings, shelves, reading dates and reviews are not imported/)).toBeInTheDocument()
    expect(writes()).toHaveLength(0)
  })

  it('previews the chosen file as a clearly marked preview, without importing', async () => {
    const user = setup()
    const dialog = await openImport(user)
    await user.upload(within(dialog).getByLabelText('Goodreads CSV file'), csvFile())
    await within(dialog).findByText('Preview your import')
    expect(writes()).toEqual([{ url: '/books/import/preview', method: 'POST', body: 'file:goodreads_library_export.csv', contentType: 'text/csv' }])
    expect(within(dialog).getByText('Nothing has been imported yet.')).toBeInTheDocument()
    expect(within(dialog).getByText('From goodreads_library_export.csv')).toBeInTheDocument()
    const stats = within(dialog).getByText('to add').closest('.import-stat') as HTMLElement
    expect(within(stats).getByText('3')).toBeInTheDocument()
    expect(within(dialog).getByText('already in library')).toBeInTheDocument()
    expect(within(dialog).getByText('gain missing details')).toBeInTheDocument()
    expect(within(dialog).getByText('Pensées')).toBeInTheDocument()
    expect(within(dialog).getByText('Blaise Pascal · 1670')).toBeInTheDocument()
    expect(within(dialog).getByText(/Matched by same title and author · will fill in goodreads id, publication year/)).toBeInTheDocument()
    expect(within(dialog).getByText(/2 books have no Goodreads ID or ISBN/)).toBeInTheDocument()
    expect(within(dialog).getByText('repeated in this file')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Import 3 books' })).toBeEnabled()
    expect(books).toHaveLength(2)                                    // the library is unchanged
    expect(within(dialog).queryByText('Import complete')).not.toBeInTheDocument()
  })

  it('cancelling a preview discards it on the server and closes without importing', async () => {
    const user = setup()
    const dialog = await openImport(user)
    await user.upload(within(dialog).getByLabelText('Goodreads CSV file'), csvFile())
    await user.click(await within(dialog).findByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(writes().map(r => `${r.method} ${r.url}`)).toEqual(['POST /books/import/preview', 'DELETE /books/import/tok-1'])
    expect(books).toHaveLength(2)
  })

  it('confirms, shows a results summary, refreshes the list, and keeps the current search', async () => {
    const user = setup()
    await user.type(await screen.findByRole('textbox', { name: 'Search books' }), 'a')
    await waitFor(() => expect(requests.some(r => r.url === '/books?q=a')).toBe(true))
    const dialog = await openImport(user)
    await user.upload(within(dialog).getByLabelText('Goodreads CSV file'), csvFile())
    await user.click(await within(dialog).findByRole('button', { name: 'Import 3 books' }))
    await within(dialog).findByText('Import complete')
    expect(writes().at(-1)).toEqual({ url: '/books/import/confirm', method: 'POST', body: { token: 'tok-1' }, contentType: 'application/json' })
    expect(within(dialog).getByText('Your library has been updated.')).toBeInTheDocument()
    const added = within(dialog).getByText('added').closest('.import-stat') as HTMLElement
    expect(within(added).getByText('3')).toBeInTheDocument()
    expect(within(dialog).getByText('details filled in')).toBeInTheDocument()
    expect(within(dialog).getByText('repeated in this file')).toBeInTheDocument()
    const open = within(dialog).getByRole('link', { name: 'Pensées' })
    expect(open).toHaveAttribute('href', '/library/new-1')
    expect(screen.getByRole('textbox', { name: 'Search books', hidden: true })).toHaveValue('a')   // search preserved behind the dialog
    await waitFor(() => expect(requests.filter(r => r.url === '/books?q=a').length).toBeGreaterThan(1))
    await user.click(within(dialog).getByRole('button', { name: 'Done' }))
    expect(await screen.findByRole('link', { name: /Pensées/ })).toBeInTheDocument()   // refreshed list
  })

  it('lets an imported book be opened straight from the results', async () => {
    const user = setup()
    const dialog = await openImport(user)
    await user.upload(within(dialog).getByLabelText('Goodreads CSV file'), csvFile())
    await user.click(await within(dialog).findByRole('button', { name: 'Import 3 books' }))
    await user.click(await within(dialog).findByRole('link', { name: 'Pensées' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await screen.findByRole('heading', { name: 'Choose a book' }).catch(() => undefined)
    expect(requests.some(r => r.url === '/books/new-1')).toBe(true)
  })

  it('shows a helpful message for an unusable file and lets the user try another', async () => {
    const user = setup()
    previewResponse = () => response({ detail: 'This doesn’t look like a Goodreads library export.' }, 422)
    const dialog = await openImport(user)
    await user.upload(within(dialog).getByLabelText('Goodreads CSV file'), csvFile('notes.csv'))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('This doesn’t look like a Goodreads library export.')
    expect(within(dialog).getByRole('heading', { name: 'Import books' })).toBeInTheDocument()   // still on the upload step
    previewResponse = () => response(previewBody())
    await user.upload(within(dialog).getByLabelText('Goodreads CSV file'), csvFile())
    await within(dialog).findByText('Preview your import')
  })

  it('says so plainly when there is nothing new to import', async () => {
    previewResponse = () => response(previewBody({ counts: { total_rows: 2, to_add: 0, matched: 2, to_update: 0, duplicates: 0, ambiguous: 0, invalid: 0 }, sample_new: [], problems: [], warnings: [] }))
    const user = setup()
    const dialog = await openImport(user)
    await user.upload(within(dialog).getByLabelText('Goodreads CSV file'), csvFile())
    await within(dialog).findByText(/Everything in this file is already in your library/)
    expect(within(dialog).getByRole('button', { name: 'Nothing to import' })).toBeDisabled()
    expect(writes().some(r => r.url === '/books/import/confirm')).toBe(false)
  })

  it('surfaces ambiguous rows as skipped rather than guessing', async () => {
    previewResponse = () => response(previewBody({ counts: { total_rows: 2, to_add: 1, matched: 0, to_update: 0, duplicates: 0, ambiguous: 1, invalid: 0 }, problems: [{ row: 3, title: 'Twin', kind: 'ambiguous', message: 'Could be “Twin”, “Twin”. Nothing was changed.' }] }))
    const user = setup()
    const dialog = await openImport(user)
    await user.upload(within(dialog).getByLabelText('Goodreads CSV file'), csvFile())
    await within(dialog).findByText('Skipped', { selector: 'h3' })
    expect(within(dialog).getByText(/Could be “Twin”, “Twin”\. Nothing was changed\./)).toBeInTheDocument()
    expect(within(dialog).getByText(/1 ambiguous match/)).toBeInTheDocument()
  })

  it('reports an expired preview without importing anything', async () => {
    confirmResponse = () => response({ detail: 'This preview has expired. Choose the file again.' }, 404)
    const user = setup()
    const dialog = await openImport(user)
    await user.upload(within(dialog).getByLabelText('Goodreads CSV file'), csvFile())
    await user.click(await within(dialog).findByRole('button', { name: 'Import 3 books' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('This preview has expired')
    expect(within(dialog).queryByText('Import complete')).not.toBeInTheDocument()
  })
})

describe('Book covers', () => {
  it('shows existing covers and a placeholder when there is none', async () => {
    setup()
    const withCover = await screen.findByRole('link', { name: /Meditations/ })
    expect(withCover.querySelector('img')).toHaveAttribute('src', 'https://example.com/m.jpg')
    const without = screen.getByRole('link', { name: /Summa Theologiae/ })
    expect(without.querySelector('img')).toBeNull()
    expect(without.querySelector('.book-cover-fallback')).toHaveTextContent('S')
  })

  it('offers cover lookup only when books lack covers, in small resumable batches', async () => {
    missing = 3
    const batches = [
      batch({ checked: 2, found: 1, not_found: 1, checked_ids: ['b9'], remaining: 1 }),
      batch({ checked: 1, found: 1, remaining: 0 }),
    ]
    enrich = () => response(batches.shift())
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Find missing covers (3)' }))
    await screen.findByText(/Added 2 covers/)
    const calls = requests.filter(r => r.url === '/books/covers/enrich')
    expect(calls.map(r => r.body)).toEqual([{ limit: 3, skip: [] }, { limit: 3, skip: ['b9'] }])
    expect(screen.getByText(/Open Library has none for 1/)).toBeInTheDocument()
    expect(screen.getByText(/may show a different edition/)).toBeInTheDocument()
  })

  it('does not block the Library while covers are being found, and Stop cancels the request', async () => {
    missing = 5
    let signal: AbortSignal | undefined
    enrich = (_body, abortSignal) => new Promise<Response>((_resolve, reject) => {
      signal = abortSignal
      abortSignal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    })
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Find missing covers (5)' }))
    await screen.findByText(/Looking for covers, one book every few seconds/)
    const search = screen.getByRole('textbox', { name: 'Search books' })
    await user.type(search, 'summa')                                  // the page is still usable
    expect(search).toHaveValue('summa')
    await waitFor(() => expect(screen.queryByRole('link', { name: /Meditations/ })).not.toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: 'Stop' }))
    await screen.findByText(/Stopped\. 0 covers were added so far/)
    expect(signal?.aborted).toBe(true)
    expect(requests.filter(r => r.url === '/books/covers/enrich')).toHaveLength(1)   // no further batches
    expect(screen.getByRole('button', { name: 'Find missing covers (5)' })).toBeEnabled()
  })

  it('stops at once on a rate limit and says when to try again, without claiming success', async () => {
    missing = 2
    const until = inMinutes(10)
    enrich = () => {
      cooldown = { blocked_until: until, retry_after_seconds: 600 }
      return response(batch({ checked: 1, rate_limited: true, stopped_early: true, blocked_until: until, retry_after_seconds: 600, remaining: 2 }))
    }
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Find missing covers (2)' }))
    const note = await screen.findByText(/Open Library asked us to slow down\. You can try again in about 10 minutes \(around /)
    expect(note).toHaveTextContent('Your library is unchanged.')
    expect(screen.queryByText(/Added/)).not.toBeInTheDocument()
    expect(requests.filter(r => r.url === '/books/covers/enrich')).toHaveLength(1)   // no automatic retry
    await waitFor(() => expect(screen.getByRole('button', { name: 'Find missing covers (2)' })).toBeDisabled())
  })

  it('falls back to a gentle message when Open Library gives no time', async () => {
    missing = 2
    enrich = () => response(batch({ checked: 1, rate_limited: true, stopped_early: true, remaining: 2 }))
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Find missing covers (2)' }))
    expect(await screen.findByText('Open Library asked us to slow down. Try again a little later.')).toBeInTheDocument()
    expect(requests.filter(r => r.url === '/books/covers/enrich')).toHaveLength(1)
  })

  it('remembers a cooldown on arrival: the button waits and nothing is requested', async () => {
    missing = 4
    cooldown = { blocked_until: inMinutes(90), retry_after_seconds: 5400 }
    setup()
    expect(await screen.findByText(/You can try again in about 90 minutes/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Find missing covers (4)' })).toBeDisabled()
    expect(requests.some(r => r.url === '/books/covers/enrich')).toBe(false)
  })

  it('explains network trouble without claiming success', async () => {
    missing = 2
    enrich = () => response(batch({ checked: 2, errors: 2, stopped_early: true, remaining: 2 }))
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Find missing covers (2)' }))
    expect(await screen.findByText(/Couldn’t reach Open Library/)).toBeInTheDocument()
    expect(screen.queryByText(/Added/)).not.toBeInTheDocument()
  })

  it('reports progress: covers in place, books missing, and remembered answers', async () => {
    missing = 3
    lookupStats = { found_lookups: 12, not_found_lookups: 20 }
    setup()
    await screen.findByRole('button', { name: 'Find missing covers (3)' })
    expect(screen.getByText(/1 book has a cover · 3 missing · Open Library answers remembered: 12 found, 20 without a cover/)).toBeInTheDocument()
  })

  it('keeps converting old ISBN cover links after the last missing cover, then reports it', async () => {
    missing = 1
    const batches = [
      batch({ checked: 1, found: 1, remaining: 0, legacy_remaining: 2 }),
      batch({ checked: 2, converted: 2, remaining: 0, legacy_remaining: 0 }),
    ]
    enrich = () => response(batches.shift())
    const user = setup()
    await user.click(await screen.findByRole('button', { name: 'Find missing covers (1)' }))
    await screen.findByText(/Added 1 cover\. Steadied 2 existing cover links/)
    expect(requests.filter(r => r.url === '/books/covers/enrich')).toHaveLength(2)
  })

  it('shows a placeholder for ISBN-addressed Open Library covers, but loads ID-addressed ones', async () => {
    books = [
      makeBook('b1', 'Hotlinked', { cover_url: 'https://covers.openlibrary.org/b/isbn/9780195093872-M.jpg' }),
      makeBook('b2', 'Steady', { cover_url: 'https://covers.openlibrary.org/b/id/8231856-M.jpg' }),
    ]
    setup()
    const hotlinked = await screen.findByRole('link', { name: /Hotlinked/ })
    expect(hotlinked.querySelector('img')).toBeNull()                 // never requested
    expect(hotlinked.querySelector('.book-cover-fallback')).toHaveTextContent('H')
    const steady = screen.getByRole('link', { name: /Steady/ })
    expect(steady.querySelector('img')).toHaveAttribute('src', 'https://covers.openlibrary.org/b/id/8231856-M.jpg')
  })

  it('shows no cover controls when every book with an ISBN already has one', async () => {
    setup()
    await screen.findByRole('link', { name: /Meditations/ })
    expect(screen.queryByRole('button', { name: /Find missing covers/ })).not.toBeInTheDocument()
  })
})
