import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { AppRoutes } from '../App'
import type { Book } from '../types'

const stamp = '2026-11-06T10:00:00Z'
const makeBook = (id: string, title: string, fields: Partial<Book> = {}): Book => ({
  id, title, authors: [`Author of ${title}`], isbn_10: null, isbn_13: null, publication_year: null, publisher: null, edition: null,
  cover_url: null, goodreads_id: null, description: null, created_at: stamp, updated_at: stamp, note_count: 0, ...fields,
})
const pad = (n: number) => String(n).padStart(3, '0')

let books: Book[]
let queryClient: QueryClient
type RequestRecord = { url: string; method: string }
let requests: RequestRecord[]
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const bookRequests = () => requests.filter(r => r.url.startsWith('/books?') || r.url === '/books').map(r => r.url)

beforeEach(() => {
  books = [...Array.from({ length: 119 }, (_, i) => makeBook(`b${pad(i + 1)}`, `Book ${pad(i + 1)}`)), makeBook('zebra', 'Zebra Finale', { authors: ['Zed Last'] })]
  requests = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const url = new URL(input.replace('/api', ''), 'http://local')
    requests.push({ url: url.pathname + url.search, method: options?.method ?? 'GET' })
    if (url.pathname === '/books') {
      const q = url.searchParams.get('q')?.toLowerCase()
      const size = Number(url.searchParams.get('page_size') ?? 50)
      const sort = url.searchParams.get('sort') ?? 'title'
      let found = books.filter(b => !q || `${b.title} ${b.authors.join(' ')}`.toLowerCase().includes(q))
      found = [...found].sort((a, b) => a.title.localeCompare(b.title))
      if (sort === 'title_desc') found.reverse()
      const totalPages = Math.ceil(found.length / size)
      const page = Math.max(1, Math.min(Number(url.searchParams.get('page') ?? 1), totalPages))
      return response({ items: found.slice((page - 1) * size, page * size), total: found.length, page, page_size: size, total_pages: totalPages })
    }
    const single = /^\/books\/([^/]+)$/.exec(url.pathname)
    if (single) { const book = books.find(b => b.id === single[1]); return book ? response(book) : response({ detail: 'Book not found' }, 404) }
    if (url.pathname === '/books/covers/missing') return response({ count: 0, with_covers: 0, found_lookups: 0, not_found_lookups: 0, blocked_until: null, retry_after_seconds: null })
    if (url.pathname === '/notes') return response([])
    if (url.pathname === '/projects') return response([])
    return response({ detail: `Unhandled ${url.pathname}` }, 404)
  }))
})
afterEach(() => { queryClient.clear(); vi.unstubAllGlobals() })

function Where() { const location = useLocation(); return <output data-testid="where">{location.pathname}{location.search}</output> }
function setup(path = '/library') {
  const user = userEvent.setup()
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /><Where /></MemoryRouter></QueryClientProvider>)
  return user
}
const summary = () => screen.getByText(/^Showing /)
const where = () => screen.getByTestId('where').textContent
const listed = () => within(screen.getByRole('region', { name: 'Books' })).getAllByRole('link')

describe('Library pagination', () => {
  it('shows the first 50 books with a clear range, and Previous disabled on page 1', async () => {
    setup()
    await screen.findByText('Showing 1–50 of 120 books')
    expect(listed()).toHaveLength(50)
    expect(within(listed()[0]).getByText('Book 001')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Previous/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Next/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Page 1' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: 'Page 3' })).toBeInTheDocument()
    expect(bookRequests()).toEqual(['/books'])                         // the default page, 50 per page
  })

  it('moves through the first, middle and last pages with Next, Previous and page numbers', async () => {
    const user = setup()
    await screen.findByText('Showing 1–50 of 120 books')
    await user.click(screen.getByRole('button', { name: /Next/ }))
    await screen.findByText('Showing 51–100 of 120 books')
    expect(within(listed()[0]).getByText('Book 051')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Previous/ })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: /Next/ }))
    await screen.findByText('Showing 101–120 of 120 books')
    expect(listed()).toHaveLength(20)
    expect(within(listed().at(-1)!).getByText('Zebra Finale')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Next/ })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Page 1' }))
    await screen.findByText('Showing 1–50 of 120 books')
    await user.click(screen.getByRole('button', { name: 'Page 3' }))
    await screen.findByText('Showing 101–120 of 120 books')
    await user.click(screen.getByRole('button', { name: /Previous/ }))
    await screen.findByText('Showing 51–100 of 120 books')
    expect(bookRequests()).toEqual(['/books', '/books?page=2', '/books?page=3', '/books', '/books?page=3', '/books?page=2'])
  })

  it('pages add up: every book across the three pages is shown exactly once', async () => {
    const user = setup()
    const seen: string[] = []
    for (const [index, range] of ['Showing 1–50 of 120 books', 'Showing 51–100 of 120 books', 'Showing 101–120 of 120 books'].entries()) {
      await screen.findByText(range)
      seen.push(...listed().map(link => link.getAttribute('href')!.split('?')[0]))
      if (index < 2) await user.click(screen.getByRole('button', { name: /Next/ }))
    }
    expect(seen).toHaveLength(120)
    expect(new Set(seen).size).toBe(120)
  })

  it('searches the whole library, finds a book outside the first 50, and resets to page 1', async () => {
    const user = setup('/library?page=3')
    await screen.findByText('Showing 101–120 of 120 books')
    await user.type(screen.getByRole('textbox', { name: 'Search books' }), 'zebra')
    await screen.findByText('Showing 1–1 of 1 book')
    expect(listed()).toHaveLength(1)
    expect(within(listed()[0]).getByText('Zebra Finale')).toBeInTheDocument()
    expect(where()).toBe('/library?q=zebra')                          // page was dropped
    expect(bookRequests().at(-1)).toBe('/books?q=zebra')
    expect(screen.queryByRole('button', { name: /Next/ })).not.toBeInTheDocument()
    await user.clear(screen.getByRole('textbox', { name: 'Search books' }))
    await screen.findByText('Showing 1–50 of 120 books')
  })

  it('searches across all pages and paginates the matches', async () => {
    const user = setup()
    await screen.findByText('Showing 1–50 of 120 books')
    await user.type(screen.getByRole('textbox', { name: 'Search books' }), 'book 0')
    await screen.findByText('Showing 1–50 of 99 books')              // Book 001–099
    await user.click(screen.getByRole('button', { name: /Next/ }))
    await screen.findByText('Showing 51–99 of 99 books')
    expect(listed()).toHaveLength(49)
  })

  it('resets to page 1 when the sort order changes, and sorts the whole library', async () => {
    const user = setup('/library?page=2')
    await screen.findByText('Showing 51–100 of 120 books')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Sort books' }), 'title_desc')
    await screen.findByText('Showing 1–50 of 120 books')
    expect(within(listed()[0]).getByText('Zebra Finale')).toBeInTheDocument()   // the overall last title leads
    expect(where()).toBe('/library?sort=title_desc')
    expect(bookRequests().at(-1)).toBe('/books?sort=title_desc')
    await user.click(screen.getByRole('button', { name: 'Page 2' }))
    await screen.findByText('Showing 51–100 of 120 books')
    expect(bookRequests().at(-1)).toBe('/books?sort=title_desc&page=2')  // sort and page together
  })

  it('keeps the selected page when opening a book and returning to the list', async () => {
    const user = setup('/library?page=2')
    await screen.findByText('Showing 51–100 of 120 books')
    const link = within(listed()[3]).getByText('Book 054').closest('a')!
    expect(link).toHaveAttribute('href', '/library/b054?page=2')        // the list state travels with the link
    await user.click(link)
    await screen.findByRole('heading', { name: 'Book 054' })
    expect(where()).toBe('/library/b054?page=2')
    expect(screen.getByText('Showing 51–100 of 120 books')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Books' })).getByRole('link', { name: /Book 054/ })).toHaveAttribute('aria-current', 'true')
    const back = screen.getByRole('link', { name: /All books/ })
    expect(back).toHaveAttribute('href', '/library?page=2')
    await user.click(back)
    await screen.findByText('Choose a book')
    expect(summary()).toHaveTextContent('Showing 51–100 of 120 books')
  })

  it('keeps search and sort together with the page', async () => {
    setup('/library/b007?q=book&sort=title_desc&page=2')
    await screen.findByText('Showing 51–100 of 119 books')
    expect(bookRequests()[0]).toBe('/books?q=book&sort=title_desc&page=2')
    expect(screen.getByRole('textbox', { name: 'Search books' })).toHaveValue('book')
    expect(screen.getByRole('combobox', { name: 'Sort books' })).toHaveValue('title_desc')
    expect(listed()[0]).toHaveAttribute('href', expect.stringContaining('?q=book&sort=title_desc&page=2'))
  })

  it('follows the server when the requested page no longer exists', async () => {
    setup('/library?page=99')
    await screen.findByText('Showing 101–120 of 120 books')
    await waitFor(() => expect(where()).toBe('/library?page=3'))
  })

  it('scrolls the book list in its own region, with the page controls kept outside it', async () => {
    setup()
    await screen.findByText('Showing 1–50 of 120 books')
    const region = screen.getByRole('region', { name: 'Books' })
    expect(region).toHaveClass('book-scroll')
    expect(region).toHaveAttribute('tabindex', '0')                    // keyboard users can scroll it
    const nav = screen.getByRole('navigation', { name: 'Library pages' })
    expect(region.contains(nav)).toBe(false)
  })

  it('says so when nothing matches, without pagination controls', async () => {
    const user = setup()
    await screen.findByText('Showing 1–50 of 120 books')
    await user.type(screen.getByRole('textbox', { name: 'Search books' }), 'zzzz no such')
    await screen.findByText('Nothing matches just yet')
    expect(screen.queryByRole('navigation', { name: 'Library pages' })).not.toBeInTheDocument()
  })

  it('shows ellipses between distant page numbers on a long library', async () => {
    books = Array.from({ length: 1000 }, (_, i) => makeBook(`l${pad(i)}`, `Long ${String(i).padStart(4, '0')}`))
    const user = setup('/library?page=10')
    await screen.findByText('Showing 451–500 of 1,000 books')
    const pages = within(screen.getByRole('navigation', { name: 'Library pages' })).getAllByRole('button').map(b => b.textContent)
    expect(pages).toEqual(['Previous', '1', '9', '10', '11', '20', 'Next'])
    await user.click(screen.getByRole('button', { name: 'Page 20' }))
    await screen.findByText('Showing 951–1,000 of 1,000 books')
  })
})

describe('Linking a note to a book without loading the whole library', () => {
  it('searches for the book and says how many more match', async () => {
    const user = setup('/notes')
    await user.click(await screen.findByRole('button', { name: 'New note' }))
    const dialog = await screen.findByRole('dialog')
    await within(dialog).findByText('95 more books match. Type to narrow the list.')
    expect(within(within(dialog).getByLabelText('Book')).getAllByRole('option')).toHaveLength(26)   // "No book" plus the first 25
    expect(bookRequests()).toContain('/books?page_size=25')
    await user.type(within(dialog).getByRole('textbox', { name: 'Search books to link' }), 'zebra')
    await waitFor(() => expect(within(dialog).getByRole('option', { name: 'Zebra Finale' })).toBeInTheDocument())
    expect(bookRequests().at(-1)).toBe('/books?page_size=25&q=zebra')
    await user.selectOptions(within(dialog).getByLabelText('Book'), 'zebra')
    expect(within(dialog).getByLabelText('Book')).toHaveValue('zebra')
    await waitFor(() => expect(within(dialog).queryByText(/more books? match/)).not.toBeInTheDocument())
  })
})
