import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import type { Book, LibraryNote, LinkType } from '../types'

const stamp = '2026-11-06T10:00:00Z'
const SYMMETRIC = new Set<LinkType>(['related_to', 'contradicts'])
interface Link { id: string; source: string; target: string; link_type: LinkType; explanation: string | null }
const makeBook = (id: string, title: string, fields: Partial<Book> = {}): Book => ({
  id, title, authors: [], isbn_10: null, isbn_13: null, publication_year: null, publisher: null, edition: null, cover_url: null,
  goodreads_id: null, description: null, created_at: stamp, updated_at: stamp, note_count: 0, ...fields,
})
const makeNote = (id: string, title: string, fields: Partial<LibraryNote> = {}): LibraryNote => ({
  id, title, note_type: 'general', book_id: null, book_title: null, project_id: null, project_name: null, source_location: null, tags: [],
  excerpt: '', updated_at: stamp, content: '', former_book: null, created_at: stamp, ...fields,
})

let books: Book[]
let notes: LibraryNote[]
let links: Link[]
let nextId: number
let queryClient: QueryClient
type RequestRecord = { url: string; method: string; body: Record<string, unknown> | undefined }
let requests: RequestRecord[]
const projects = [{ id: 'p1', name: 'Write the paper' }]
const response = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const withCount = (book: Book): Book => ({ ...book, note_count: notes.filter(n => n.book_id === book.id).length })
const brief = (note: LibraryNote) => ({ ...note, excerpt: note.content.slice(0, 240) })
const withRefs = (note: LibraryNote): LibraryNote => ({ ...note, book_title: books.find(b => b.id === note.book_id)?.title ?? null, project_name: projects.find(p => p.id === note.project_id)?.name ?? null })
const view = (link: Link, perspective: string) => {
  const other = notes.find(n => n.id === (link.source === perspective ? link.target : link.source))!
  const direction = SYMMETRIC.has(link.link_type) ? 'mutual' : link.source === perspective ? 'outgoing' : 'incoming'
  return { id: link.id, link_type: link.link_type, direction, explanation: link.explanation, created_at: stamp, note: brief(withRefs(other)) }
}

beforeEach(() => {
  books = [
    makeBook('b1', 'Summa Theologiae', { authors: ['Thomas Aquinas'], publication_year: 1274, publisher: 'Christian Classics', edition: 'Vol. 1', isbn_13: '9780870612129' }),
    makeBook('b2', 'Confessions', { authors: ['Augustine of Hippo'] }),
  ]
  notes = [
    makeNote('n1', 'On beatitude', { note_type: 'quotation', book_id: 'b1', source_location: 'ST I–II, q. 1, a. 8', content: 'Beatitude is the perfect good of the rational nature.', project_id: 'p1' }),
    makeNote('n2', 'Restless hearts', { note_type: 'reading_note', book_id: 'b2', content: '# Augustine\n\nline one\nline two\n\n[a link](https://example.com)' }),
    makeNote('n3', 'Is happiness enough?', { note_type: 'question' }),
  ]
  links = []
  nextId = 1
  requests = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const url = new URL(input.replace('/api', ''), 'http://local')
    const path = url.pathname
    const method = options?.method ?? 'GET'
    const body = options?.body ? JSON.parse(options.body as string) : undefined
    requests.push({ url: path + url.search, method, body })
    const q = url.searchParams.get('q')?.toLowerCase()
    if (path === '/projects') return response(projects)
    if (path === '/books') {
      if (method === 'POST') { const created = makeBook(`new-${nextId++}`, body.title, body); books.push(created); return response(withCount(created), 201) }
      return response(books.filter(b => !q || `${b.title} ${b.authors.join(' ')}`.toLowerCase().includes(q)).map(withCount))
    }
    const bookMatch = /^\/books\/([^/]+)$/.exec(path)
    if (bookMatch) {
      const book = books.find(b => b.id === bookMatch[1])
      if (!book) return response({ detail: 'Book not found' }, 404)
      if (method === 'DELETE') {
        if (notes.some(n => n.book_id === book.id) && url.searchParams.get('keep_notes') !== 'true') return response({ detail: 'notes linked' }, 409)
        notes.forEach(n => { if (n.book_id === book.id) { n.book_id = null; n.former_book = book.title } })
        books = books.filter(b => b.id !== book.id)
        return response(null, 204)
      }
      if (method === 'PATCH') Object.assign(book, body)
      return response(withCount(book))
    }
    if (path === '/notes') {
      if (method === 'POST') { const created = makeNote(`new-${nextId++}`, body.title, body); notes.unshift(created); return response(withRefs(created), 201) }
      const type = url.searchParams.get('note_type'); const bookId = url.searchParams.get('book_id')
      return response(notes.filter(n => (!q || `${n.title} ${n.content} ${n.source_location ?? ''}`.toLowerCase().includes(q)) && (!type || n.note_type === type) && (!bookId || n.book_id === bookId)).map(n => brief(withRefs(n))))
    }
    const connectionsMatch = /^\/notes\/([^/]+)\/connections$/.exec(path)
    if (connectionsMatch) {
      const id = connectionsMatch[1]
      if (method === 'POST') {
        const link: Link = { id: `link-${nextId++}`, source: id, target: body.target_note_id, link_type: body.link_type, explanation: body.explanation }
        links.push(link)
        return response(view(link, id), 201)
      }
      return response(links.filter(l => l.source === id || l.target === id).map(l => view(l, id)))
    }
    const noteMatch = /^\/notes\/([^/]+)$/.exec(path)
    if (noteMatch) {
      const note = notes.find(n => n.id === noteMatch[1])
      if (!note) return response({ detail: 'Note not found' }, 404)
      if (method === 'DELETE') { notes = notes.filter(n => n.id !== note.id); links = links.filter(l => l.source !== note.id && l.target !== note.id); return response(null, 204) }
      if (method === 'PATCH') Object.assign(note, body)
      return response(withRefs(note))
    }
    const linkMatch = /^\/note-links\/([^/]+)$/.exec(path)
    if (linkMatch && method === 'DELETE') { links = links.filter(l => l.id !== linkMatch[1]); return response(null, 204) }
    return response({ detail: `Unhandled ${method} ${path}` }, 404)
  }))
})
afterEach(() => { queryClient.clear(); vi.unstubAllGlobals() })
function setup(path: string) {
  const user = userEvent.setup()
  const utils = render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
  return { user, ...utils }
}
const writes = () => requests.filter(r => r.method !== 'GET')

describe('Navigation', () => {
  it('offers Library and Notes in the sidebar, replacing the placeholder', async () => {
    setup('/')
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' })
    expect(within(nav).getByRole('link', { name: 'Library' })).toHaveAttribute('href', '/library')
    expect(within(nav).getByRole('link', { name: 'Notes' })).toHaveAttribute('href', '/notes')
    expect(within(nav).queryByText('Notes & Books')).not.toBeInTheDocument()
  })
})

describe('Library', () => {
  it('lists books with authors and the number of notes, and searches', async () => {
    const { user } = setup('/library')
    const summa = (await screen.findByRole('link', { name: /Summa Theologiae/ }))
    expect(within(summa).getByText('Thomas Aquinas')).toBeInTheDocument()
    expect(within(summa).getByLabelText('1 note')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Confessions/ })).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Search books' }), 'augustine')
    await waitFor(() => expect(screen.queryByRole('link', { name: /Summa Theologiae/ })).not.toBeInTheDocument())
    expect(requests.some(r => r.url === '/books?q=augustine')).toBe(true)
    expect(screen.getByText('Choose a book')).toBeInTheDocument()
  })
  it('adds a book from only a title, then opens it', async () => {
    const { user } = setup('/library')
    await user.click(await screen.findByRole('button', { name: 'Add a book' }))
    await user.type(screen.getByLabelText('Title'), '  The City of God ')
    await user.click(screen.getByRole('button', { name: 'Add book' }))
    await screen.findByRole('heading', { name: 'The City of God' })
    expect(writes()[0]).toEqual({ url: '/books', method: 'POST', body: { title: 'The City of God', authors: [], isbn_10: null, isbn_13: null, publication_year: null, publisher: null, edition: null, cover_url: null, goodreads_id: null, description: null } })
    expect(screen.getByRole('button', { name: 'Add Note' })).toBeInTheDocument()
  })
  it('has no reading status, progress, rating or shelving anywhere', async () => {
    setup('/library/b1')
    await screen.findByRole('heading', { name: 'Summa Theologiae' })
    expect(screen.queryByText(/read|rating|stars|progress|streak|goal|shelf|shelve/i, { selector: 'button, label, option, h1, h2, h3' })).not.toBeInTheDocument()
  })
  it('shows bibliographic details and emphasizes the book’s notes', async () => {
    setup('/library/b1')
    await screen.findByRole('heading', { name: 'Summa Theologiae' })
    expect(screen.getByText('Thomas Aquinas', { selector: '.book-authors' })).toBeInTheDocument()
    for (const text of ['1274', 'Christian Classics', 'Vol. 1', '9780870612129']) expect(screen.getByText(text)).toBeInTheDocument()
    const notesCard = screen.getByRole('heading', { name: /Notes from this book/ }).closest('.card') as HTMLElement
    expect(within(notesCard).getByText('On beatitude')).toBeInTheDocument()
    expect(within(notesCard).queryByText('Restless hearts')).not.toBeInTheDocument()
  })
  it('creates a quotation from a book, linked to it, with a precise source reference', async () => {
    const { user } = setup('/library/b2')
    await user.click(await screen.findByRole('button', { name: 'Add Note' }))
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(within(dialog).getByLabelText('Book')).toHaveValue('b2'))
    await user.type(within(dialog).getByLabelText('Title'), 'Our hearts are restless')
    await user.selectOptions(within(dialog).getByLabelText('Type'), 'quotation')
    expect(within(dialog).getByText('The author’s exact words, attributed to a source.')).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText(/Source/), 'Book I, chapter 1')
    await user.type(within(dialog).getByLabelText('Note'), 'You have made us for yourself.')
    await user.click(within(dialog).getByRole('button', { name: 'Save note' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(writes()[0]).toEqual({ url: '/notes', method: 'POST', body: { title: 'Our hearts are restless', note_type: 'quotation', content: 'You have made us for yourself.', source_location: 'Book I, chapter 1', book_id: 'b2', project_id: null, tags: [] } })
    expect(await screen.findByText('Our hearts are restless')).toBeInTheDocument()
  })
  it('deleting a book says its notes are kept, and keeps them', async () => {
    const { user } = setup('/library/b1')
    await user.click(await screen.findByRole('button', { name: 'Delete book: Summa Theologiae' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/Its 1 note will be kept/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Keep it' }))
    expect(writes()).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Delete book: Summa Theologiae' }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Delete book' }))
    await screen.findByText('Choose a book')
    expect(writes()[0]).toEqual({ url: '/books/b1?keep_notes=true', method: 'DELETE', body: undefined })
    expect(notes.find(n => n.id === 'n1')).toMatchObject({ book_id: null, former_book: 'Summa Theologiae' })
    expect(screen.queryByRole('link', { name: /Summa Theologiae/ })).not.toBeInTheDocument()
  })
  it('explains a missing book kindly', async () => {
    setup('/library/gone')
    await screen.findByText('We couldn’t find that book')
  })
})

describe('Notes', () => {
  it('searches and filters by type, newest first', async () => {
    const { user } = setup('/notes')
    await screen.findByRole('link', { name: /On beatitude/ })
    expect(screen.getAllByText('Quotation').length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: 'Question' }))
    await waitFor(() => expect(screen.queryByRole('link', { name: /On beatitude/ })).not.toBeInTheDocument())
    expect(screen.getByRole('link', { name: /Is happiness enough\?/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'All' }))
    await user.type(screen.getByRole('textbox', { name: 'Search notes' }), 'perfect good')
    await waitFor(() => expect(screen.queryByRole('link', { name: /Restless hearts/ })).not.toBeInTheDocument())
    expect(screen.getByRole('link', { name: /On beatitude/ })).toBeInTheDocument()
    expect(requests.some(r => r.url === '/notes?note_type=question')).toBe(true)
    expect(requests.some(r => r.url === '/notes?q=perfect+good')).toBe(true)
  })
  it('shows a quotation as attributed speech and a reading note as the reader’s own summary', async () => {
    setup('/notes/n1')
    const heading = await screen.findByRole('heading', { name: 'On beatitude' })
    const card = heading.closest('.note-view') as HTMLElement
    const figure = card.querySelector('figure.quotation') as HTMLElement
    expect(figure).not.toBeNull()
    expect(within(figure).getByText('— Summa Theologiae, ST I–II, q. 1, a. 8')).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Summa Theologiae' })).toHaveAttribute('href', '/library/b1')
    expect(within(card).getByRole('link', { name: 'Write the paper' })).toHaveAttribute('href', '/projects/p1')
    expect(within(card).getByText('QUOTATION')).toBeInTheDocument()
  })
  it('renders reading notes as Markdown and keeps them out of the quotation style', async () => {
    setup('/notes/n2')
    const heading = await screen.findByRole('heading', { name: 'Restless hearts' })
    const card = heading.closest('.note-view') as HTMLElement
    expect(card.querySelector('figure.quotation')).toBeNull()
    expect(within(card).getByRole('heading', { name: 'Augustine' })).toBeInTheDocument()
    expect(card.querySelector('.markdown p')?.textContent).toBe('line one\nline two')
    const link = within(card).getByRole('link', { name: 'a link' })
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveAttribute('target', '_blank')
  })
  it('never renders scripts, javascript: links, or remote images from note text', async () => {
    notes.push(makeNote('evil', 'Hostile note', { content: 'Before <script>window.__pwned = true</script> after\n\n<img src="x" onerror="window.__pwned = true">\n\n[click me](javascript:window.__pwned=true)\n\n![tracker](http://evil.example/p.png)\n\n[fine](https://example.com/ok)\n\n<iframe src="http://evil.example"></iframe>' }))
    setup('/notes/evil')
    const heading = await screen.findByRole('heading', { name: 'Hostile note' })
    const card = heading.closest('.note-view') as HTMLElement
    const markdown = card.querySelector('.markdown') as HTMLElement
    expect(markdown.querySelector('script, iframe, img, object, embed')).toBeNull()
    expect(Array.from(markdown.querySelectorAll('a')).every(a => !/^\s*javascript:/i.test(a.getAttribute('href') ?? ''))).toBe(true)
    expect(markdown.querySelector('a[href="https://example.com/ok"]')).not.toBeNull()
    expect(markdown.querySelector('[onerror], [onclick], [onload]')).toBeNull()
    expect((window as unknown as { __pwned?: boolean }).__pwned).toBeUndefined()
  })
  it('creates a note that stands on its own, then opens it', async () => {
    const { user } = setup('/notes')
    await user.click(await screen.findByRole('button', { name: 'New note' }))
    await user.type(screen.getByLabelText('Title'), 'What is a person?')
    await user.selectOptions(screen.getByLabelText('Type'), 'question')
    await user.type(screen.getByLabelText(/Tags/), 'Metaphysics, personhood')
    await user.click(screen.getByRole('button', { name: 'Save note' }))
    await screen.findByRole('heading', { name: 'What is a person?' })
    expect(writes()[0]).toEqual({ url: '/notes', method: 'POST', body: { title: 'What is a person?', note_type: 'question', content: '', source_location: null, book_id: null, project_id: null, tags: ['Metaphysics', 'personhood'] } })
  })
  it('links an existing note to a project from the editor', async () => {
    const { user } = setup('/notes/n3')
    await user.click(await screen.findByRole('button', { name: 'Edit note: Is happiness enough?' }))
    await user.selectOptions(await screen.findByLabelText('Project'), 'p1')
    await user.click(screen.getByRole('button', { name: 'Save note' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(writes()[0].body).toMatchObject({ project_id: 'p1', book_id: null })
    expect(writes()[0].url).toBe('/notes/n3')
    expect(await screen.findByRole('link', { name: 'Write the paper' })).toHaveAttribute('href', '/projects/p1')
  })
  it('previews Markdown while editing without saving', async () => {
    const { user } = setup('/notes')
    await user.click(await screen.findByRole('button', { name: 'New note' }))
    await user.type(screen.getByLabelText('Note'), '## Heading')
    await user.click(screen.getByRole('button', { name: 'Preview' }))
    expect(await screen.findByRole('heading', { name: 'Heading', level: 2 })).toBeInTheDocument()
    expect(writes()).toHaveLength(0)
  })
  it('deletes a note only after confirmation', async () => {
    const { user } = setup('/notes/n3')
    await user.click(await screen.findByRole('button', { name: 'Delete note: Is happiness enough?' }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Keep it' }))
    expect(writes()).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Delete note: Is happiness enough?' }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Delete permanently' }))
    await screen.findByText('Choose a note to read')
    expect(writes()[0]).toEqual({ url: '/notes/n3', method: 'DELETE', body: undefined })
  })
})

describe('Connecting ideas', () => {
  it('connects two notes, shows the link from both ends with the right direction, and removes it', async () => {
    const { user } = setup('/notes/n1')
    await user.click(await screen.findByRole('button', { name: 'Connect an Idea' }))
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Search your notes'), 'restless')
    await waitFor(() => expect(within(dialog).queryByText('Is happiness enough?')).not.toBeInTheDocument())
    expect(within(dialog).queryByText('On beatitude')).not.toBeInTheDocument()   // never offers the note itself
    await user.click(within(dialog).getByRole('button', { name: /Restless hearts/ }))
    await user.selectOptions(within(dialog).getByLabelText('Relationship'), 'develops')
    expect(within(dialog).getByText(/“On beatitude” develops “Restless hearts”\. This does not say the reverse\./)).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText(/Why are they connected/), 'Both locate happiness in God.')
    await user.click(within(dialog).getByRole('button', { name: 'Save connection' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(writes()[0]).toEqual({ url: '/notes/n1/connections', method: 'POST', body: { target_note_id: 'n2', link_type: 'develops', explanation: 'Both locate happiness in God.' } })

    const section = (await screen.findByRole('heading', { name: 'Connections' })).closest('section') as HTMLElement
    expect(await within(section).findByText('Develops')).toBeInTheDocument()
    expect(within(section).getByText('Both locate happiness in God.')).toBeInTheDocument()
    await user.click(within(section).getByRole('link', { name: 'Restless hearts' }))

    const other = (await screen.findByRole('heading', { name: 'Restless hearts' })).closest('.note-view') as HTMLElement
    const otherSection = within(other).getByRole('heading', { name: 'Connections' }).closest('section') as HTMLElement
    expect(await within(otherSection).findByText('Developed by')).toBeInTheDocument()    // not "Develops"
    expect(within(otherSection).queryByText('Develops')).not.toBeInTheDocument()
    expect(within(otherSection).getByRole('link', { name: 'On beatitude' })).toBeInTheDocument()

    await user.click(within(otherSection).getByRole('button', { name: 'Remove connection: Developed by On beatitude' }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Remove connection' }))
    await within(otherSection).findByText(/No connections yet/)
    expect(writes().at(-1)).toEqual({ url: '/note-links/link-1', method: 'DELETE', body: undefined })
    expect(notes.map(n => n.id)).toContain('n1')   // removing a link never deletes notes
  })
  it('explains that symmetric relationships read the same from both notes', async () => {
    const { user } = setup('/notes/n1')
    await user.click(await screen.findByRole('button', { name: 'Connect an Idea' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(await within(dialog).findByRole('button', { name: /Is happiness enough/ }))
    expect(within(dialog).getByText(/are related to one another\. This reads the same from both notes\./)).toBeInTheDocument()
    await user.selectOptions(within(dialog).getByLabelText('Relationship'), 'contradicts')
    expect(within(dialog).getByText(/contradict one another\. This reads the same from both notes\./)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Save connection' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(writes()[0].body).toMatchObject({ target_note_id: 'n3', link_type: 'contradicts', explanation: null })
  })
  it('keeps connections after a refresh because they come from the server', async () => {
    links.push({ id: 'l9', source: 'n2', target: 'n1', link_type: 'supports', explanation: null })
    const { unmount } = setup('/notes/n1')
    expect(await screen.findByText('Supported by')).toBeInTheDocument()
    unmount()
    queryClient.clear()
    setup('/notes/n2')
    expect(await screen.findByText('Supports')).toBeInTheDocument()
  })
})
