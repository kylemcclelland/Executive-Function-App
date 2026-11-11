import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { LIBRARY_CATEGORIES, categoryKeyOf, describeLibraryError, matchesSearch, normalizeText } from '../lib/devotions'
import { ApiError } from '../services/api'
import type { DevotionBrief } from '../types/devotions'
import css from '../components/devotions/oratory.css?raw'

// Neutral filler records that exist only inside these tests (never in the app, a database or a seed).
const brief = (id: string, title: string, fields: Partial<DevotionBrief> = {}): DevotionBrief => ({
  id, slug: id, title, subtitle: null, category: null, estimated_minutes: null, bookmarked: false, has_text: true, ...fields,
})
const library = (): DevotionBrief[] => [
  brief('alpha', 'Filler Alpha', { subtitle: 'A short filler description', category: 'Daily Prayer', estimated_minutes: 5, bookmarked: true }),
  brief('beta', 'Filler Beta', { category: 'our lady', has_text: false }),
  brief('gamma', 'Filler Gamma', { subtitle: 'Mentions Pàter with an accent', category: 'Mystery Category', bookmarked: true, estimated_minutes: 1 }),
  brief('delta', 'Filler Delta'),
  brief('epsilon', 'Filler Epsilon', { category: 'Saints' }),
]

let requests: { path: string; method: string }[]
let respond: () => Response | Promise<Response>
let queryClient: QueryClient
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

function stub(list: DevotionBrief[] | (() => Response | Promise<Response>)) {
  requests = []
  respond = typeof list === 'function' ? list : () => json(list)
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const path = input.replace('/api', '')
    requests.push({ path, method: options?.method ?? 'GET' })
    if (path.startsWith('/editorial')) return json({ detail: 'Editorial access is restricted to the owner' }, 403)
    if (path === '/devotions') return respond()
    const slug = path.replace('/devotions/', '')
    return json({ ...brief(slug, `Filler ${slug}`), overview: 'Overview filler', background: null, significance: null, references: [], instructions: [], steps: [], texts: [] })
  }))
}
function open(path = '/devotions') {
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
}
const titles = () => [...resultsSection().querySelectorAll('.devotion-card-title')].map(title => title.textContent)
const resultsSection = () => screen.getByRole('region', { name: /All devotions|Daily Prayer|Our Lord|Our Lady|Saints|Liturgical Seasons|Other|The library/ })

beforeEach(() => { window.localStorage.clear() })
afterEach(() => { vi.unstubAllGlobals() })

describe('the welcome', () => {
  it('greets the reader with the heading, the subtitle and nothing decorative that a screen reader must wade through', async () => {
    stub([])
    open()
    expect(await screen.findByRole('heading', { level: 1, name: 'The Oratory' })).toBeInTheDocument()
    expect(screen.getByText('Bring what weighs on your heart to God.')).toBeInTheDocument()
    expect(document.querySelector('.oratory-rule')).toHaveAttribute('aria-hidden', 'true')
  })

  it('is called The Oratory in the main navigation', () => {
    stub([])
    open()
    expect(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: 'The Oratory' })).toHaveAttribute('href', '/devotions')
  })
})

describe('an empty library', () => {
  it('says so warmly, without an error and without inventing anything', async () => {
    stub([])
    open()
    expect(await screen.findByText('No devotions have been added yet')).toBeInTheDocument()
    expect(screen.getByText(/Devotions you add will appear here\./)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
    expect(document.querySelectorAll('.devotion-card')).toHaveLength(0)
    expect(screen.getByRole('link', { name: 'See how a devotion page will look' })).toHaveAttribute('href', '/devotions/preview')
  })

  it('still shows a complete page: search, every category and a welcoming saved section', async () => {
    stub([])
    open()
    await screen.findByText('No devotions have been added yet')
    expect(screen.getByRole('searchbox', { name: 'Search devotions' })).toBeInTheDocument()
    const categories = within(screen.getByRole('group', { name: 'Categories' })).getAllByRole('button')
    expect(categories.map(button => button.textContent)).toEqual(['All Devotions', 'Daily Prayer', 'Our Lord', 'Our Lady', 'Saints', 'Liturgical Seasons', 'Other'])
    const saved = screen.getByRole('region', { name: 'Saved prayers' })
    expect(within(saved).getByText('Nothing saved yet')).toBeInTheDocument()
    expect(within(saved).getByText(/When you save a devotion, or a prayer from the Divine Office, it will wait for you here./)).toBeInTheDocument()
  })

  it('does not call an empty library a failed search, whatever is typed or chosen', async () => {
    stub([])
    open()
    await screen.findByText('No devotions have been added yet')
    await userEvent.type(screen.getByRole('searchbox'), 'anything')
    await userEvent.click(screen.getByRole('button', { name: 'Our Lady' }))
    expect(screen.getByText('No devotions have been added yet')).toBeInTheDocument()
    expect(screen.queryByText(/No devotions match/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Nothing in Our Lady yet/)).not.toBeInTheDocument()
  })
})

describe('published devotion cards', () => {
  it('shows the title, subtitle, category, duration, saved mark and a link for each', async () => {
    stub(library())
    open()
    const section = await screen.findByRole('region', { name: 'All devotions' })
    const alpha = within(section).getByRole('link', { name: /Filler Alpha/ })
    expect(alpha).toHaveAttribute('href', '/devotions/alpha')
    expect(within(alpha).getByText('Daily Prayer')).toBeInTheDocument()
    expect(within(alpha).getByText('A short filler description')).toBeInTheDocument()
    expect(within(alpha).getByText('About 5 minutes')).toBeInTheDocument()
    expect(within(alpha).getByLabelText('Saved')).toBeInTheDocument()
    const beta = within(section).getByRole('link', { name: /Filler Beta/ })
    expect(within(beta).queryByLabelText('Saved')).not.toBeInTheDocument()
    expect(within(beta).getByText('No prayer text yet')).toBeInTheDocument()
    expect(within(alpha).queryByText('No prayer text yet')).not.toBeInTheDocument()
    expect(within(section).getAllByRole('listitem')).toHaveLength(5)
  })

  it('is reachable and openable with the keyboard alone', async () => {
    stub(library())
    open()
    const section = await screen.findByRole('region', { name: 'All devotions' })
    const first = within(section).getAllByRole('link')[0]
    expect(first).not.toHaveAttribute('tabindex', '-1')
    first.focus()
    expect(first).toHaveFocus()
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByRole('heading', { level: 1, name: 'Filler alpha' })).toBeInTheDocument()
  })

  it('makes each card one keyboard stop, not several', async () => {
    stub(library())
    open()
    const section = await screen.findByRole('region', { name: 'All devotions' })
    for (const card of within(section).getAllByRole('listitem')) expect(card.querySelectorAll('a, button')).toHaveLength(1)
  })
})

describe('search', () => {
  it('filters the loaded list by title, description and category, without another request', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    const box = screen.getByRole('searchbox', { name: 'Search devotions' })
    await userEvent.type(box, 'beta')
    expect(titles()).toEqual(['Filler Beta'])
    await userEvent.clear(box)
    await userEvent.type(box, 'short filler description')
    expect(titles()).toEqual(['Filler Alpha'])                              // the subtitle is the short description
    await userEvent.clear(box)
    await userEvent.type(box, 'saints')
    expect(titles()).toEqual(['Filler Epsilon'])                            // the category
    expect(requests.filter(request => request.path === '/devotions')).toHaveLength(1)   // one request, however much was typed
  })

  it('ignores case, accents and extra spaces, and needs every word', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    const box = screen.getByRole('searchbox')
    await userEvent.type(box, '  PATER   accent ')
    expect(titles()).toEqual(['Filler Gamma'])
    await userEvent.clear(box)
    await userEvent.type(box, 'filler zzz')
    expect(titles()).toEqual([])
  })

  it('says how many it is showing', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    expect(screen.getByRole('status')).toHaveTextContent('5 devotions')
    await userEvent.type(screen.getByRole('searchbox'), 'beta')
    expect(screen.getByRole('status')).toHaveTextContent('Showing 1 devotion of 5')
  })

  it('can be cleared with the button or Escape, and restores the full list', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    const box = screen.getByRole('searchbox')
    expect(screen.queryByRole('button', { name: 'Clear search' })).not.toBeInTheDocument()
    await userEvent.type(box, 'beta')
    await userEvent.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(box).toHaveValue('')
    expect(titles()).toHaveLength(5)
    await userEvent.type(box, 'beta{Escape}')
    expect(box).toHaveValue('')
    expect(titles()).toHaveLength(5)
  })

  it('starts from a search kept in the address, so Back from a devotion returns to the same view', async () => {
    stub(library())
    open('/devotions?q=beta&category=our-lady')
    await screen.findByRole('region', { name: 'Our Lady' })
    expect(screen.getByRole('searchbox')).toHaveValue('beta')
    expect(screen.getByRole('button', { name: 'Our Lady' })).toHaveAttribute('aria-pressed', 'true')
    expect(titles()).toEqual(['Filler Beta'])
  })

  it('shows a helpful no-results state that never looks like an empty library', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    await userEvent.type(screen.getByRole('searchbox'), 'zzzz')
    expect(screen.getByText('No devotions match “zzzz”')).toBeInTheDocument()
    expect(screen.queryByText('No devotions have been added yet')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('offers to clear the search from the no-results state', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    await userEvent.type(screen.getByRole('searchbox'), 'zzzz')
    const results = resultsSection()
    await userEvent.click(within(results).getByRole('button', { name: 'Clear search' }))
    expect(titles()).toHaveLength(5)
    expect(screen.getByRole('searchbox')).toHaveValue('')
  })
})

describe('categories', () => {
  it('filters the existing results by category and marks the chosen one', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    expect(screen.getByRole('button', { name: 'All Devotions' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Daily Prayer' }))
    expect(titles()).toEqual(['Filler Alpha'])
    expect(screen.getByRole('button', { name: 'Daily Prayer' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'All Devotions' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('region', { name: 'Daily Prayer' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Our Lady' }))
    expect(titles()).toEqual(['Filler Beta'])                               // "our lady" matches whatever its capitalisation
    await userEvent.click(screen.getByRole('button', { name: 'All Devotions' }))
    expect(titles()).toHaveLength(5)
    expect(requests.filter(request => request.path === '/devotions')).toHaveLength(1)
  })

  it('files a category it does not recognise, or none at all, under Other', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    await userEvent.click(screen.getByRole('button', { name: 'Other' }))
    expect(titles()).toEqual(['Filler Gamma', 'Filler Delta'])
  })

  it('combines with search', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    await userEvent.click(screen.getByRole('button', { name: 'Other' }))
    await userEvent.type(screen.getByRole('searchbox'), 'gamma')
    expect(titles()).toEqual(['Filler Gamma'])
    await userEvent.clear(screen.getByRole('searchbox'))
    await userEvent.type(screen.getByRole('searchbox'), 'alpha')
    expect(screen.getByText('No devotions match “alpha”')).toBeInTheDocument()
    expect(within(resultsSection()).getByRole('button', { name: 'Show all devotions' })).toBeInTheDocument()
  })

  it('has an honest, friendly state for a category with nothing in it yet, and a way out', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    await userEvent.click(screen.getByRole('button', { name: 'Our Lord' }))
    expect(screen.getByText('Nothing in Our Lord yet')).toBeInTheDocument()
    expect(screen.getByText(/Nothing is filed under this category yet\./)).toBeInTheDocument()
    expect(screen.queryByText('No devotions have been added yet')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Show all devotions' }))
    expect(titles()).toHaveLength(5)
  })

  it('ignores an unknown category in the address', async () => {
    stub(library())
    open('/devotions?category=nonsense')
    await screen.findByRole('region', { name: 'All devotions' })
    expect(titles()).toHaveLength(5)
  })

  it('classifies categories case-, accent- and space-insensitively', () => {
    expect(LIBRARY_CATEGORIES.map(item => item.label)).toEqual(['Daily Prayer', 'Our Lord', 'Our Lady', 'Saints', 'Liturgical Seasons', 'Other'])
    expect(categoryKeyOf('  OUR   lady ')).toBe('our-lady')
    expect(categoryKeyOf('liturgical seasons')).toBe('liturgical-seasons')
    expect(categoryKeyOf('Something else')).toBe('other')
    expect(categoryKeyOf(null)).toBe('other')
    expect(normalizeText('PÁTER  Noster')).toBe('pater noster')
    expect(matchesSearch(brief('x', 'Title'), '   ')).toBe(true)
  })
})

describe('saved devotions', () => {
  it('lists the reader’s bookmarked devotions in their own section', async () => {
    stub(library())
    open()
    const saved = await screen.findByRole('region', { name: 'Saved prayers' })
    expect(within(saved).getAllByRole('link').map(link => link.querySelector('.devotion-card-title')!.textContent)).toEqual(['Filler Alpha', 'Filler Gamma'])
    expect(within(saved).queryByText('Nothing saved yet')).not.toBeInTheDocument()
  })

  it('is not narrowed by the search or the category, which only shape the library below it', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'Saved prayers' })
    await userEvent.type(screen.getByRole('searchbox'), 'epsilon')
    await userEvent.click(screen.getByRole('button', { name: 'Saints' }))
    expect(within(screen.getByRole('region', { name: 'Saved prayers' })).getAllByRole('link')).toHaveLength(2)
    expect(titles().filter(title => title === 'Filler Epsilon')).toHaveLength(1)
  })

  it('welcomes the reader when nothing has been saved', async () => {
    stub(library().map(devotion => ({ ...devotion, bookmarked: false })))
    open()
    const saved = await screen.findByRole('region', { name: 'Saved prayers' })
    expect(within(saved).getByText('Nothing saved yet')).toBeInTheDocument()
    expect(within(saved).queryByRole('link')).not.toBeInTheDocument()
  })
})

describe('failures are never an empty library', () => {
  const failing = (status: number, detail: string) => () => json({ detail }, status)
  const cases: [string, () => Response | Promise<Response>, RegExp, boolean][] = [
    ['401', failing(401, 'Authentication required'), /session couldn’t be verified/, true],
    ['403', failing(403, 'Forbidden'), /doesn’t have access to the devotional library/, false],
    ['404', failing(404, 'Not Found'), /isn’t available on this server yet \(404 Not Found\)/, true],
    ['500', failing(500, 'Internal Server Error'), /temporarily unavailable \(server error 500\)/, true],
    ['503', failing(503, 'Database unavailable'), /temporarily unavailable \(server error 503\)/, true],
    ['a network failure', () => { throw new TypeError('Failed to fetch') }, /couldn’t reach the server/, true],
  ]
  it.each(cases)('treats %s as an error with its own message', async (_name, response, message, retry) => {
    stub(response)
    open()
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.queryByRole('button', { name: 'Try again' }) !== null).toBe(retry)
    expect(screen.queryByText('No devotions have been added yet')).not.toBeInTheDocument()
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'The Oratory' })).toBeInTheDocument()
  })

  it('gives each status a different message', () => {
    const messages = [401, 403, 404, 500, 503].map(status => describeLibraryError(new ApiError('x', status)).message)
    expect(new Set(messages).size).toBeGreaterThanOrEqual(4)               // 500 and 503 share wording but name their own code
    expect(messages.every(message => !/no devotions have been added/i.test(message))).toBe(true)
    expect(describeLibraryError(new ApiError('Too many requests', 429))).toEqual({ kind: 'other', message: 'Too many requests' })
  })

  it('recovers when Try again succeeds', async () => {
    let healthy = false
    stub(() => (healthy ? json(library()) : json({ detail: 'down' }, 503)))
    open()
    await screen.findByRole('alert')
    healthy = true
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('region', { name: 'All devotions' })).toBeInTheDocument()
    expect(titles()).toHaveLength(5)
  })

  it('does not treat any 404 as an empty library, even for an empty body', async () => {
    stub(() => new Response('', { status: 404 }))
    open()
    expect(await screen.findByRole('alert')).toHaveTextContent('404 Not Found')
    expect(screen.queryByText('No devotions have been added yet')).not.toBeInTheDocument()
  })
})

describe('no measuring of prayer', () => {
  it('has no streaks, scores, percentages, reminders or analytics, and stores nothing', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    await userEvent.type(screen.getByRole('searchbox'), 'a')
    await userEvent.click(screen.getByRole('button', { name: 'Saints' }))
    expect(document.body.textContent).not.toMatch(/streak|score|completed|completion|\d+\s*%|progress|goal|remind|notification|you missed|keep it up|well done/i)
    expect(Object.keys(window.localStorage)).toEqual([])
    expect(requests.every(request => request.method === 'GET')).toBe(true)  // browsing writes nothing
  })
})

describe('stylesheet (mobile first, themed, accessible)', () => {
  it('lays out one column on a phone and widens only inside min-width queries', () => {
    expect(css).not.toMatch(/max-width\s*:\s*\d+px\)/)
    const base = css.split('@media')[0]
    expect(base).toMatch(/\.devotion-list\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/)
    expect(css).toMatch(/@media \(min-width: 640px\)[\s\S]*repeat\(2/)
    expect(css).toMatch(/@media \(min-width: 1000px\)[\s\S]*repeat\(3/)
  })

  it('uses only design tokens for colour, so light and dark both work', () => {
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(css).not.toMatch(/\brgba?\(/)
  })

  it('has clear focus, comfortable touch targets and a search box that does not zoom a phone', () => {
    expect(css).toMatch(/\.devotion-card:focus-visible\s*\{[^}]*outline:\s*3px solid/)
    expect(css).toMatch(/\.oratory-search input\s*\{[^}]*font-size:\s*16px/)
    for (const rule of ['.oratory-search input', '.oratory-categories button', '.oratory-search button']) {
      const body = css.match(new RegExp(`${rule.replace(/[.]/g, '\\.')}\\s*\\{([^}]*)\\}`))![1]
      expect(Number(/min-height:\s*(\d+)px/.exec(body)![1])).toBeGreaterThanOrEqual(40)
    }
  })

  it('lets categories wrap rather than hide behind a sideways scroll', () => {
    expect(css).toMatch(/\.oratory-categories\s*\{[^}]*flex-wrap:\s*wrap/)
    expect(css).not.toMatch(/overflow-x:\s*(auto|scroll)/)
  })
})

describe('waiting for the list', () => {
  it('shows the welcome and a loading status, not an empty state', async () => {
    stub(() => new Promise<Response>(() => {}))
    open()
    expect(screen.getByRole('heading', { level: 1, name: 'The Oratory' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Loading')
    expect(screen.queryByText('No devotions have been added yet')).not.toBeInTheDocument()
    await waitFor(() => expect(requests.filter(request => request.path === '/devotions')).toHaveLength(1))
  })
})

describe('the Divine Office entrance', () => {
  it('links from The Oratory to the Divine Office', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    expect(screen.getByRole('link', { name: 'The Divine Office' })).toHaveAttribute('href', '/divine-office')
  })
})

describe('no editorial entrance for ordinary readers', () => {
  it('shows no editorial link to a non-owner and never fetches draft data', async () => {
    stub(library())
    open()
    await screen.findByRole('region', { name: 'All devotions' })
    await waitFor(() => expect(requests.some(request => request.path === '/editorial/access')).toBe(true))
    expect(screen.queryByRole('link', { name: /editorial/i })).not.toBeInTheDocument()
    // The server refused the light access probe (403); nothing editorial beyond it was requested.
    expect(requests.filter(request => request.path.includes('editorial')).map(request => request.path)).toEqual(['/editorial/access'])
  })
})
