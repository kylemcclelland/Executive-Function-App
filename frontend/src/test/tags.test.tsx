import { useState } from 'react'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { TagInput } from '../components/notes/TagInput'
import type { LibraryNote, TagSuggestion } from '../types'

const stamp = '2026-11-06T10:00:00Z'
const catalog: TagSuggestion[] = [
  { tag: 'Ethics', count: 3 }, { tag: 'Epistemology', count: 1 }, { tag: 'Law', count: 2 },
  { tag: 'Metaphysics', count: 1 }, { tag: 'Natural Law', count: 1 },
]
const makeNote = (id: string, title: string, tags: string[] = []): LibraryNote => ({
  id, title, note_type: 'general', book_id: null, book_title: null, project_id: null, project_name: null, source_location: null,
  tags, excerpt: '', updated_at: stamp, content: '', former_book: null, created_at: stamp,
})

let notes: LibraryNote[]
let tagsStatus: number
let queryClient: QueryClient
type RequestRecord = { url: string; method: string; body: unknown }
let requests: RequestRecord[]
const response = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const suggestionRequests = () => requests.filter(r => r.url.startsWith('/notes/tags')).map(r => r.url)
const writes = () => requests.filter(r => r.method !== 'GET')

beforeEach(() => {
  notes = [makeNote('n1', 'On virtue', ['Ethics', 'Law'])]
  tagsStatus = 200
  requests = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const url = new URL(input.replace('/api', ''), 'http://local')
    const method = options?.method ?? 'GET'
    const body = options?.body ? JSON.parse(options.body as string) : undefined
    requests.push({ url: url.pathname + url.search, method, body })
    if (url.pathname === '/notes/tags') {
      if (tagsStatus !== 200) return response({ detail: 'down' }, tagsStatus)
      const q = (url.searchParams.get('q') ?? '').toLowerCase()
      const matches = catalog.filter(item => item.tag.toLowerCase().includes(q))
      matches.sort((a, b) => Number(!a.tag.toLowerCase().startsWith(q)) - Number(!b.tag.toLowerCase().startsWith(q)) || b.count - a.count || a.tag.localeCompare(b.tag))
      return response(matches.slice(0, Number(url.searchParams.get('limit') ?? 10)))
    }
    if (url.pathname === '/notes') {
      if (method === 'POST') { const created = makeNote(`new-${notes.length}`, body.title, body.tags); notes.unshift(created); return response(created, 201) }
      return response(notes)
    }
    if (url.pathname === '/books') return response({ items: [], total: 0, page: 1, page_size: 25, total_pages: 0 })
    if (url.pathname === '/projects') return response([])
    const connections = /^\/notes\/([^/]+)\/connections$/.exec(url.pathname)
    if (connections) return response([])
    const single = /^\/notes\/([^/]+)$/.exec(url.pathname)
    if (single) {
      const note = notes.find(n => n.id === single[1])
      if (!note) return response({ detail: 'Note not found' }, 404)
      if (method === 'PATCH') Object.assign(note, body)
      return response(note)
    }
    return response({ detail: `Unhandled ${method} ${url.pathname}` }, 404)
  }))
})
afterEach(() => { queryClient.clear(); vi.unstubAllGlobals() })

function Harness({ initial = [], onChange }: { initial?: string[]; onChange?: (tags: string[]) => void }) {
  const [tags, setTags] = useState<string[]>(initial)
  return <TagInput value={tags} onChange={next => { setTags(next); onChange?.(next) }} />
}
function renderField(initial: string[] = []) {
  const changes: string[][] = []
  const user = userEvent.setup()
  render(<QueryClientProvider client={queryClient}><Harness initial={initial} onChange={tags => changes.push(tags)} /></QueryClientProvider>)
  return { user, changes, field: screen.getByRole('combobox', { name: 'Tags' }) }
}
const chips = () => within(screen.getByRole('list', { name: 'Selected tags' })).queryAllByRole('listitem').map(item => item.querySelector('span')?.textContent)
const optionNames = () => screen.queryAllByRole('option').map(option => option.textContent)

describe('Tag autocomplete', () => {
  it('suggests tags from existing notes as you type, in a listbox, ignoring case', async () => {
    const { user, field } = renderField()
    expect(field).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    await user.type(field, 'eth')
    const list = await screen.findByRole('listbox', { name: 'Tag suggestions' })
    expect(field).toHaveAttribute('aria-expanded', 'true')
    expect(field).toHaveAttribute('aria-controls', list.id)
    expect(optionNames()[0]).toBe('Ethics3 notes')
    expect(suggestionRequests().at(-1)).toBe('/notes/tags?limit=8&q=eth')
    await user.clear(field)
    await user.type(field, 'LAW')
    await waitFor(() => expect(optionNames().slice(0, 2)).toEqual(['Law2 notes', 'Natural Law1 note']))   // prefix match first
  })

  it('shows the most-used tags when the list is opened with the arrow key and nothing typed', async () => {
    const { user, field } = renderField()
    await user.click(field)
    await user.keyboard('{ArrowDown}')
    await screen.findByRole('listbox')
    expect(optionNames()[0]).toBe('Ethics3 notes')
    expect(suggestionRequests().at(-1)).toBe('/notes/tags?limit=8')
  })

  it('moves through suggestions with the arrow keys and selects with Enter', async () => {
    const { user, changes, field } = renderField()
    await user.type(field, 'e')
    await screen.findByRole('option', { name: /Ethics/ })
    await waitFor(() => expect(screen.getAllByRole('option').length).toBeGreaterThanOrEqual(3))   // Ethics, Epistemology, Metaphysics…
    const active = () => field.getAttribute('aria-activedescendant')
    expect(active()).toBeNull()                                           // nothing is chosen until you move
    await user.keyboard('{ArrowDown}')
    expect(screen.getAllByRole('option')[0]).toHaveAttribute('aria-selected', 'true')
    expect(active()).toBe(screen.getAllByRole('option')[0].id)
    await user.keyboard('{ArrowDown}')
    expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByRole('option')[0]).toHaveAttribute('aria-selected', 'false')
    await user.keyboard('{ArrowUp}{ArrowUp}')                             // wraps to the last option
    const options = screen.getAllByRole('option')
    expect(options.at(-1)).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{ArrowDown}{ArrowDown}')                         // wraps forward to the second
    expect(screen.getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true')
    const chosen = screen.getAllByRole('option')[1].querySelector('span')!.textContent!
    await user.keyboard('{Enter}')
    expect(chips()).toEqual([chosen])
    expect(changes.at(-1)).toEqual([chosen])
    expect(field).toHaveValue('')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('selects a suggestion with the mouse', async () => {
    const { user, field } = renderField()
    await user.type(field, 'meta')
    await user.click(await screen.findByRole('option', { name: /Metaphysics/ }))
    expect(chips()).toEqual(['Metaphysics'])
    expect(field).toHaveValue('')
    expect(field).toHaveFocus()                                           // typing can continue
  })

  it('reuses the existing capitalization when the typed tag matches one', async () => {
    const { user, changes, field } = renderField()
    await user.type(field, 'ethics')
    await screen.findByRole('option', { name: /Ethics/ })
    await user.keyboard('{Enter}')                                        // nothing highlighted: add what was typed
    expect(chips()).toEqual(['Ethics'])                                   // not "ethics"
    await user.type(field, 'NATURAL LAW,')
    await screen.findByText('Natural Law', { selector: '.tag-chip span' }).catch(() => undefined)
    expect(changes.at(-1)).toEqual(['Ethics', 'Natural Law'])
  })

  it('never adds the same tag twice, whatever its capitalization or spacing', async () => {
    const { user, changes, field } = renderField()
    await user.type(field, 'eth')
    await user.click(await screen.findByRole('option', { name: /Ethics/ }))
    expect(chips()).toEqual(['Ethics'])
    await user.type(field, '  ETHICS  ')
    expect(await screen.findByText('“ETHICS” is already added.')).toBeInTheDocument()
    await user.keyboard('{Enter}')
    await user.type(field, 'ethics,')
    await user.type(field, ' #Ethics ,')
    expect(chips()).toEqual(['Ethics'])
    expect(changes).toEqual([['Ethics']])                                 // no change event for the repeats
    await user.type(field, 'eth')
    await waitFor(() => expect(optionNames().some(name => name?.startsWith('Ethics'))).toBe(false))   // already chosen: not suggested
  })

  it('creates a new tag when none exists, with the spelling as typed', async () => {
    const { user, changes, field } = renderField()
    await user.type(field, 'Brand New Idea')
    const create = await screen.findByRole('option', { name: 'Create “Brand New Idea”' })
    expect(create).toBeInTheDocument()
    await user.keyboard('{Enter}')                                        // Enter with nothing highlighted creates it
    expect(chips()).toEqual(['Brand New Idea'])
    await user.type(field, 'Telos')
    await user.click(await screen.findByRole('option', { name: 'Create “Telos”' }))
    await user.type(field, 'Alpha, Beta,')                                // commas add tags as you go
    expect(changes.at(-1)).toEqual(['Brand New Idea', 'Telos', 'Alpha', 'Beta'])
    expect(chips()).toEqual(['Brand New Idea', 'Telos', 'Alpha', 'Beta'])
  })

  it('offers "Create" last, and an arrow-selected create option adds the typed tag', async () => {
    const { user, field } = renderField()
    await user.type(field, 'Law')
    await screen.findByRole('option', { name: /^Law2 notes/ })
    expect(screen.queryByRole('option', { name: /Create/ })).not.toBeInTheDocument()   // "Law" exists: reuse, don't recreate
    await user.clear(field)
    await user.type(field, 'Lawful')
    const create = await screen.findByRole('option', { name: 'Create “Lawful”' })
    expect(screen.getAllByRole('option').at(-1)).toBe(create)
    await user.keyboard('{ArrowUp}{Enter}')
    expect(chips()).toEqual(['Lawful'])
  })

  it('shows tags as removable chips', async () => {
    const { user, changes } = renderField(['Ethics', 'Telos'])
    expect(chips()).toEqual(['Ethics', 'Telos'])
    await user.click(screen.getByRole('button', { name: 'Remove tag Ethics' }))
    expect(chips()).toEqual(['Telos'])
    expect(changes.at(-1)).toEqual(['Telos'])
    await user.click(screen.getByRole('combobox', { name: 'Tags' }))
    await user.keyboard('{Backspace}')                                    // Backspace on an empty field removes the last chip
    expect(chips()).toEqual([])
  })

  it('keeps typed text as a tag when the field loses focus', async () => {
    const { user, changes, field } = renderField()
    await user.type(field, 'Pending Idea')
    await user.tab()
    expect(chips()).toEqual(['Pending Idea'])
    expect(changes.at(-1)).toEqual(['Pending Idea'])
  })

  it('still lets you add tags when suggestions cannot be loaded', async () => {
    tagsStatus = 500
    const { user, field } = renderField()
    await user.type(field, 'Offline tag')
    await user.keyboard('{Enter}')
    expect(chips()).toEqual(['Offline tag'])
  })

  it('stops at the 20-tag limit and says so', async () => {
    const { field } = renderField(Array.from({ length: 20 }, (_, i) => `tag ${i}`))
    expect(field).toBeDisabled()
    expect(screen.getByText('That’s the limit of 20 tags.')).toBeInTheDocument()
  })
})

describe('Tags in the note editor', () => {
  async function openEditor(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole('button', { name: 'New note' }))
    return screen.findByRole('dialog')
  }
  function setup(path: string) {
    const user = userEvent.setup()
    render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
    return user
  }

  it('saves chosen and new tags with the note, and the note shows them afterwards', async () => {
    const user = setup('/notes')
    const dialog = await openEditor(user)
    await user.type(within(dialog).getByLabelText('Title'), 'Happiness and the good')
    const field = within(dialog).getByRole('combobox', { name: 'Tags' })
    await user.type(field, 'eth')
    await user.keyboard('{ArrowDown}{Enter}')
    await user.type(field, 'Telos,')
    await user.click(within(dialog).getByRole('button', { name: 'Save note' }))
    await screen.findByRole('heading', { name: 'Happiness and the good' })
    expect(writes()[0]).toMatchObject({ url: '/notes', method: 'POST', body: { title: 'Happiness and the good', tags: ['Ethics', 'Telos'] } })
    const pane = within(screen.getByRole('region', { name: 'Selected note' }))
    expect(await pane.findByText('#Ethics')).toBeInTheDocument()
    expect(pane.getByText('#Telos')).toBeInTheDocument()
  })

  it('shows an existing note’s tags as chips and saves the edited list', async () => {
    const user = setup('/notes/n1')
    await user.click(await screen.findByRole('button', { name: 'Edit note: On virtue' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(within(dialog).getByRole('list', { name: 'Selected tags' })).getAllByRole('listitem').map(item => item.textContent)).toEqual(['Ethics', 'Law'])
    await user.click(within(dialog).getByRole('button', { name: 'Remove tag Law' }))
    await user.type(within(dialog).getByRole('combobox', { name: 'Tags' }), 'Prudence')
    await user.click(await within(dialog).findByRole('option', { name: 'Create “Prudence”' }))
    await user.click(within(dialog).getByRole('button', { name: 'Save note' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(writes().at(-1)).toMatchObject({ url: '/notes/n1', method: 'PATCH', body: { tags: ['Ethics', 'Prudence'] } })
    expect(notes[0].tags).toEqual(['Ethics', 'Prudence'])
    const pane = within(screen.getByRole('region', { name: 'Selected note' }))
    expect(await pane.findByText('#Prudence')).toBeInTheDocument()
    expect(pane.queryByText('#Law')).not.toBeInTheDocument()
  })

  it('an open suggestion list takes Escape first, so the unsaved note is not lost', async () => {
    const user = setup('/notes')
    const dialog = await openEditor(user)
    await user.type(within(dialog).getByLabelText('Title'), 'Do not lose me')
    await user.type(within(dialog).getByRole('combobox', { name: 'Tags' }), 'eth')
    await within(dialog).findByRole('listbox')
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()                // still open, title intact
    expect(within(screen.getByRole('dialog')).getByLabelText('Title')).toHaveValue('Do not lose me')
    await user.keyboard('{Escape}')                                       // with no list open, Escape closes as before
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
})
