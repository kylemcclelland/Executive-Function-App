import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { DevotionView } from '../components/devotions/DevotionView'
import { LANGUAGE_KEY, SIZE_KEY, isResponseLine, resolveLanguage, safeUrl } from '../lib/devotions'
import { PLACEHOLDER_KINDS, placeholderDevotion } from '../lib/devotionPlaceholders'
import type { Devotion, PrayerText } from '../types/devotions'
import css from '../components/devotions/devotions.css?raw'

// Every wording below is neutral filler for the tests, never a real prayer.
const source = { title: 'A Test Source Book', edition: '1st test edition', translator: null, is_translation: false, attribution: 'Filler attribution line', url: null, license_status: 'public_domain' as const }
const text = (slot: string, language: string, body: string, fields: Partial<PrayerText> = {}): PrayerText => ({ id: `${slot}-${language}`, slot, language, title: null, body, source, ...fields })

function view(devotion: Devotion, props: Partial<Parameters<typeof DevotionView>[0]> = {}) {
  return render(<MemoryRouter><DevotionView devotion={devotion} {...props} /></MemoryRouter>)
}
const heading = (name: string) => screen.queryByRole('heading', { level: 2, name })

beforeEach(() => { window.localStorage.clear() })
afterEach(() => { vi.unstubAllGlobals() })

describe('simple devotion layout', () => {
  it('shows the header, overview, instructions and prayer text, each in its own section', () => {
    view({ ...placeholderDevotion('simple'), bookmarked: false }, { onToggleBookmark: () => {} })
    expect(screen.getByRole('heading', { level: 1, name: 'Prayer Title' })).toBeInTheDocument()
    expect(screen.getByText('Subtitle will appear here')).toBeInTheDocument()
    expect(screen.getByText('Category')).toBeInTheDocument()
    expect(screen.getByText('About 10 minutes')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /The Oratory/ })).toHaveAttribute('href', '/devotions')
    for (const name of ['Overview', 'How to Pray', 'Prayer Text']) expect(heading(name)).toBeInTheDocument()
    expect(screen.getByText('Historical background')).toBeInTheDocument()
    expect(screen.getByText('Spiritual significance')).toBeInTheDocument()
    expect(screen.getByText('Source reference will appear here')).toBeInTheDocument()
    expect(screen.queryByText('The sequence')).not.toBeInTheDocument()       // a simple prayer has no steps
  })

  it('keeps instruction apart from prayer wording', () => {
    view(placeholderDevotion('simple'))
    const howTo = screen.getByRole('region', { name: 'How to Pray' })
    const list = within(howTo).getByRole('list')
    expect(list.tagName).toBe('OL')
    expect(within(list).getAllByRole('listitem').map(item => item.textContent)).toEqual(['Instructions will appear here.', 'A second numbered instruction will appear here.'])
    expect(within(howTo).queryByText(/Verified prayer text/)).not.toBeInTheDocument()
    const prayer = screen.getByRole('region', { name: 'Prayer Text' })
    expect(within(prayer).queryByText(/Instructions will appear here/)).not.toBeInTheDocument()
    expect(within(prayer).getByText(/Verified prayer text will appear here/)).toBeInTheDocument()
  })

  it('shows the source, edition, translator, attribution and rights with the text', () => {
    const translated = text('main', 'en', 'Filler words', { source: { ...source, is_translation: true, translator: 'T. Filler', url: 'https://example.org/source' } })
    view({ ...placeholderDevotion('simple'), texts: [translated] })
    const prayer = screen.getByRole('region', { name: 'Prayer Text' })
    for (const value of ['A Test Source Book', '1st test edition', 'T. Filler', 'Filler attribution line', 'Public domain']) expect(within(prayer).getByText(value)).toBeInTheDocument()
    expect(within(prayer).getByRole('link', { name: 'View the source' })).toHaveAttribute('href', 'https://example.org/source')
  })

  it('never makes a non-web address clickable', () => {
    const unsafe = text('main', 'en', 'Filler words', { source: { ...source, url: 'javascript:alert(1)' } })
    view({ ...placeholderDevotion('simple'), texts: [unsafe], references: [{ label: 'Bad link', url: 'javascript:alert(1)' }] })
    expect(screen.queryByRole('link', { name: 'View the source' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Bad link' })).not.toBeInTheDocument()
    expect(screen.getByText('Bad link')).toBeInTheDocument()
    expect(safeUrl('javascript:alert(1)')).toBeNull()
    expect(safeUrl('https://example.org/a')).toBe('https://example.org/a')
  })
})

describe('complex devotion layout', () => {
  it('outlines the sequence with sections, kinds and repetition, without the wording', () => {
    view(placeholderDevotion('sequence'))
    const howTo = screen.getByRole('region', { name: 'How to Pray' })
    expect(within(howTo).getByText('The sequence')).toBeInTheDocument()
    expect(within(howTo).getAllByRole('heading', { level: 4 }).map(h => h.textContent)).toEqual(['Opening', 'Section 1', 'Closing'])
    expect(within(howTo).getAllByRole('listitem')).toHaveLength(1 + 5)           // one general instruction + five steps
    expect(within(howTo).getByText('Repeat 10 times')).toBeInTheDocument()
    expect(within(howTo).getByText('Instruction for the opening will appear here.')).toBeInTheDocument()
    expect(within(howTo).getAllByText('Response')).not.toHaveLength(0)
    expect(within(howTo).queryByText(/Verified opening text/)).not.toBeInTheDocument()
  })
})

describe('missing optional sections', () => {
  it('omits what is absent and shows the unpublished placeholder instead of prayer text', () => {
    view(placeholderDevotion('minimal'))
    expect(screen.getByRole('heading', { level: 1, name: 'Prayer Title' })).toBeInTheDocument()
    expect(heading('Overview')).toBeInTheDocument()
    expect(heading('How to Pray')).not.toBeInTheDocument()
    for (const hidden of ['Historical background', 'Spiritual significance', 'Sources', 'About 10 minutes', 'Category', 'Subtitle will appear here']) expect(screen.queryByText(hidden)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Save|Saved/ })).not.toBeInTheDocument()   // no bookmark handler, no button
    expect(screen.getByRole('note')).toHaveTextContent('The prayer text has not been published yet.')
    expect(screen.queryByRole('button', { name: 'Enter prayer mode' })).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Language' })).not.toBeInTheDocument()
  })

  it('shows instructions on their own when there are no steps, and steps on their own when there are no instructions', () => {
    const { unmount } = view({ ...placeholderDevotion('simple'), steps: [] })
    expect(within(screen.getByRole('region', { name: 'How to Pray' })).queryByText('The sequence')).not.toBeInTheDocument()
    unmount()
    view({ ...placeholderDevotion('sequence'), instructions: [] })
    const howTo = screen.getByRole('region', { name: 'How to Pray' })
    expect(within(howTo).getByText('The sequence')).toBeInTheDocument()
    expect(howTo.querySelectorAll('.instruction-list')).toHaveLength(0)
  })
})

describe('Latin and English', () => {
  const bilingual = () => placeholderDevotion('bilingual')
  const shown = () => [...document.querySelectorAll<HTMLElement>('.prayer-body')].map(el => [el.getAttribute('lang'), el.textContent])

  it('offers the languages that exist, showing English first and one language at a time', async () => {
    view(bilingual())
    const toggle = screen.getByRole('group', { name: 'Language' })
    expect(within(toggle).getAllByRole('button').map(b => b.textContent)).toEqual(['Latin', 'English', 'Both'])
    expect(within(toggle).getByRole('button', { name: 'English' })).toHaveAttribute('aria-pressed', 'true')
    expect(shown().map(([lang]) => lang)).toEqual(['en'])
    await userEvent.click(within(toggle).getByRole('button', { name: 'Latin' }))
    expect(shown().map(([lang]) => lang)).toEqual(['la'])
    expect(shown()[0][1]).toContain('Verified Latin text will appear here.')
    expect(window.localStorage.getItem(LANGUAGE_KEY)).toBe('la')
  })

  it('shows both side by side with Latin first, each marked with its language', async () => {
    view(bilingual())
    await userEvent.click(screen.getByRole('button', { name: 'Both' }))
    expect(shown().map(([lang]) => lang)).toEqual(['la', 'en'])
    expect(document.querySelector('.prayer-versions')).toHaveClass('is-parallel')
    expect(screen.getAllByText(/^(Latin|English)$/, { selector: '.prayer-language' })).toHaveLength(2)
  })

  it('says so, and falls back, when one text lacks the chosen language', () => {
    window.localStorage.setItem(LANGUAGE_KEY, 'la')
    view({ ...placeholderDevotion('simple'), texts: [text('one', 'en', 'English one'), text('one', 'la', 'Latin one'), text('two', 'en', 'English two')] })
    expect(screen.getAllByText('No Latin version of this text has been published yet.')).toHaveLength(1)
    expect(shown()).toEqual([['la', 'Latin one'], ['en', 'English two']])        // the Latin where it exists, the English otherwise
  })

  it('offers no toggle, and no note, when only one language exists at all', () => {
    window.localStorage.setItem(LANGUAGE_KEY, 'la')
    view(placeholderDevotion('simple'))
    expect(screen.queryByRole('group', { name: 'Language' })).not.toBeInTheDocument()
    expect(screen.queryByText(/No Latin version/)).not.toBeInTheDocument()
    expect(shown().map(([lang]) => lang)).toEqual(['en'])
  })

  it('resolves a preference against what is available', () => {
    expect(resolveLanguage('la', ['en'])).toBe('en')
    expect(resolveLanguage('both', ['en'])).toBe('en')
    expect(resolveLanguage('both', ['la', 'en'])).toBe('both')
    expect(resolveLanguage('fr', ['la'])).toBe('la')
  })
})

describe('exact wording', () => {
  const body = '  Leading spaces kept  \n\n\tTabbed line\n\n\nThree blank lines above\n℣. A versicle line\n℟. A response line\nPlain line\n'

  it('renders every character, space and line break exactly as stored', () => {
    view({ ...placeholderDevotion('simple'), texts: [text('main', 'en', body)] })
    const element = document.querySelector('.prayer-body')!
    expect(element.textContent).toBe(body)
    expect(getComputedStyle(element).whiteSpace).toBe('pre-wrap')
  })

  it('marks versicle and response lines for styling without changing them', () => {
    view({ ...placeholderDevotion('simple'), texts: [text('main', 'en', body)] })
    const responses = [...document.querySelectorAll('.prayer-line.is-response')].map(el => el.textContent)
    expect(responses).toEqual(['℣. A versicle line', '℟. A response line'])
    expect(isResponseLine('R. Reply')).toBe(true)
    expect(isResponseLine('℟')).toBe(true)
    expect(isResponseLine('V.')).toBe(true)
    expect(isResponseLine('Rest in peace')).toBe(false)
    expect(isResponseLine('R.Kelly')).toBe(false)
  })

  it('does not interpret prayer text as markup', () => {
    view({ ...placeholderDevotion('simple'), texts: [text('main', 'en', '<b>bold</b> <script>alert(1)</script> **stars**')] })
    expect(document.querySelector('.prayer-body b')).toBeNull()
    expect(document.querySelector('.prayer-body')!.textContent).toBe('<b>bold</b> <script>alert(1)</script> **stars**')
  })
})

describe('reading preferences', () => {
  it('makes the prayer text larger or smaller, remembers it, and stops at the ends', async () => {
    view(placeholderDevotion('simple'))
    const section = screen.getByRole('region', { name: 'Prayer Text' })
    expect(section).toHaveAttribute('data-size', 'normal')
    expect(screen.getByRole('button', { name: 'Smaller text' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Larger text' }))
    expect(section).toHaveAttribute('data-size', 'large')
    await userEvent.click(screen.getByRole('button', { name: 'Larger text' }))
    expect(section).toHaveAttribute('data-size', 'xlarge')
    expect(screen.getByRole('button', { name: 'Larger text' })).toBeDisabled()
    expect(window.localStorage.getItem(SIZE_KEY)).toBe('xlarge')
  })

  it('starts from the remembered size', () => {
    window.localStorage.setItem(SIZE_KEY, 'large')
    view(placeholderDevotion('simple'))
    expect(screen.getByRole('region', { name: 'Prayer Text' })).toHaveAttribute('data-size', 'large')
  })
})

describe('bookmark', () => {
  it('reflects and toggles the saved state', async () => {
    const toggle = vi.fn()
    view({ ...placeholderDevotion('simple'), bookmarked: true }, { onToggleBookmark: toggle })
    const button = screen.getByRole('button', { name: 'Saved' })
    expect(button).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(button)
    expect(toggle).toHaveBeenCalledWith(false)
  })
})

describe('prayer mode', () => {
  const open = async (devotion: Devotion) => { view(devotion); await userEvent.click(screen.getByRole('button', { name: 'Enter prayer mode' })); return screen.getByRole('dialog') }

  it('reads a simple prayer in a quiet full-screen view and leaves on request', async () => {
    const dialog = await open(placeholderDevotion('simple'))
    expect(within(dialog).getByRole('heading', { name: 'Prayer Title' })).toBeInTheDocument()
    expect(within(dialog).getByText(/Verified prayer text will appear here/)).toBeInTheDocument()
    expect(within(dialog).queryByRole('navigation', { name: 'Prayer steps' })).not.toBeInTheDocument()   // no steps, no stepper
    expect(within(dialog).queryByText(/Historical background|Overview/)).not.toBeInTheDocument()          // nothing but the prayer
    await userEvent.click(within(dialog).getByRole('button', { name: /Leave prayer mode/ }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes with Escape', async () => {
    await open(placeholderDevotion('simple'))
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('moves through a sequence one step at a time with Previous and Next', async () => {
    const dialog = await open(placeholderDevotion('sequence'))
    const count = () => within(dialog).getByText(/^Step \d+ of \d+$/).textContent
    const previous = within(dialog).getByRole('button', { name: /Previous/ })
    const next = within(dialog).getByRole('button', { name: /Next/ })
    expect(count()).toBe('Step 1 of 5')
    expect(previous).toBeDisabled()
    expect(within(dialog).getByText('Instruction for the opening will appear here.')).toBeInTheDocument()
    await userEvent.click(next)
    expect(count()).toBe('Step 2 of 5')
    expect(within(dialog).getByText('Verified opening text will appear here.')).toBeInTheDocument()
    await userEvent.click(next)
    expect(within(dialog).getByText('Pray this 10 times')).toBeInTheDocument()
    expect(within(dialog).getByText('A note about how to pray it will appear here.')).toBeInTheDocument()
    await userEvent.click(previous)
    expect(count()).toBe('Step 2 of 5')
  })

  it('sets instruction apart from prayer wording, and styles responses', async () => {
    const dialog = await open(placeholderDevotion('sequence'))
    expect(dialog.querySelector('.instruction')).not.toBeNull()
    expect(dialog.querySelector('.prayer-body')).toBeNull()                 // the first step is instruction only
    await userEvent.click(within(dialog).getByRole('button', { name: /Next/ }))
    await userEvent.click(within(dialog).getByRole('button', { name: /Next/ }))
    await userEvent.click(within(dialog).getByRole('button', { name: /Next/ }))
    expect(dialog.querySelector('.is-response-text .prayer-body')).not.toBeNull()
    expect(dialog.querySelectorAll('.prayer-line.is-response')).toHaveLength(2)
  })

  it('uses the arrow keys, and stops at the first and last steps', async () => {
    const dialog = await open(placeholderDevotion('sequence'))
    await userEvent.keyboard('{ArrowLeft}')
    expect(within(dialog).getByText('Step 1 of 5')).toBeInTheDocument()
    for (let i = 0; i < 7; i++) await userEvent.keyboard('{ArrowRight}')
    expect(within(dialog).getByText('Step 5 of 5')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: /Next/ })).toBeDisabled()
    await userEvent.keyboard('{ArrowLeft}')
    expect(within(dialog).getByText('Step 4 of 5')).toBeInTheDocument()
  })

  it('shows the unpublished placeholder for a step whose wording is not approved', async () => {
    const dialog = await open(placeholderDevotion('sequence'))
    for (let i = 0; i < 4; i++) await userEvent.click(within(dialog).getByRole('button', { name: /Next/ }))
    expect(within(dialog).getByText('Step 5 of 5')).toBeInTheDocument()
    expect(within(dialog).getByRole('note')).toHaveTextContent('The prayer text has not been published yet.')
  })

  it('follows the language and size choices made in the dialog', async () => {
    const dialog = await open(placeholderDevotion('bilingual'))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Latin' }))
    expect(dialog.querySelector('.prayer-body')).toHaveAttribute('lang', 'la')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Larger text' }))
    expect(dialog).toHaveAttribute('data-size', 'large')
  })

  it('keeps no record of prayer: no requests, no stored activity, no streaks or completion language', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    const dialog = await open(placeholderDevotion('sequence'))
    for (let i = 0; i < 4; i++) await userEvent.click(within(dialog).getByRole('button', { name: /Next/ }))
    await userEvent.keyboard('{Escape}')
    expect(fetcher).not.toHaveBeenCalled()
    expect(Object.keys(window.localStorage).filter(key => ![SIZE_KEY, LANGUAGE_KEY].includes(key))).toEqual([])
    expect(document.body.textContent).not.toMatch(/streak|completed|completion|well done|keep it up|you missed|goal|score|congratulations/i)
  })
})

describe('placeholder data', () => {
  it('is neutral, labelled placeholder text, with no real prayer', () => {
    for (const kind of PLACEHOLDER_KINDS) {
      const devotion = placeholderDevotion(kind)
      expect(devotion.id).toBe('placeholder')
      for (const prayer of devotion.texts) expect(prayer.body).toMatch(/will appear here/)
      for (const field of [devotion.overview, devotion.background, ...devotion.instructions]) if (field) expect(field).toMatch(/will appear here/)
    }
  })
})

// ---- The pages, with a stubbed API -------------------------------------------------------------
const published: Devotion = { ...placeholderDevotion('simple'), id: 'd1', slug: 'test-devotion', texts: [text('main', 'en', 'Test filler wording')] }
let requests: { path: string; method: string }[]
let queryClient: QueryClient
const json = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

function stubApi(devotions: Devotion[]) {
  requests = []
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const path = input.replace('/api', '')
    const method = options?.method ?? 'GET'
    requests.push({ path, method })
    if (path === '/devotions') return json(devotions.map(({ overview: _o, background: _b, significance: _s, references: _r, instructions: _i, steps: _t, texts, ...brief }) => ({ ...brief, has_text: texts.length > 0 })))
    const match = /^\/devotions\/([^/]+)(\/bookmark)?$/.exec(path)
    const found = devotions.find(d => d.slug === match?.[1])
    if (!found) return json({ detail: 'Devotion not found' }, 404)
    if (match?.[2]) { found.bookmarked = method === 'PUT'; return json({ bookmarked: found.bookmarked }) }
    return json(found)
  }))
}
function app(path: string) {
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
}

describe('devotion page', () => {
  it('renders a published devotion from the API and toggles its bookmark', async () => {
    stubApi([structuredClone(published)])
    app('/devotions/test-devotion')
    expect(await screen.findByText('Test filler wording', { selector: '.prayer-line' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(requests).toContainEqual({ path: '/devotions/test-devotion/bookmark', method: 'PUT' }))
    expect(await screen.findByRole('button', { name: 'Saved' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Saved' }))
    await waitFor(() => expect(requests).toContainEqual({ path: '/devotions/test-devotion/bookmark', method: 'DELETE' }))
  })

  it('shows the unpublished placeholder when the server sends no approved text', async () => {
    stubApi([{ ...published, texts: [], has_text: false }])
    app('/devotions/test-devotion')
    expect(await screen.findByRole('note')).toHaveTextContent('The prayer text has not been published yet.')
    expect(screen.queryByRole('button', { name: 'Enter prayer mode' })).not.toBeInTheDocument()
  })

  it('says a devotion is unavailable when it is not published', async () => {
    stubApi([])
    app('/devotions/draft')
    expect(await screen.findByText('This devotion isn’t available')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to The Oratory' })).toHaveAttribute('href', '/devotions')
  })
})

describe('layout preview page', () => {
  it('is clearly labelled as placeholder content, and the kinds can be switched', async () => {
    stubApi([])
    app('/devotions/preview')
    expect(screen.getByText(/Layout preview\./)).toBeInTheDocument()
    expect(screen.getByText(/contains no real prayer/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Prayer Title' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('link', { name: 'Multi-step devotion' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Devotion Title' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('link', { name: 'Missing optional sections' }))
    expect(await screen.findByText('The prayer text has not been published yet.')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 2, name: 'How to Pray' })).not.toBeInTheDocument()
    expect(requests.filter(r => r.path.startsWith('/devotions'))).toEqual([])          // never touches the API
  })

  it('sends an unknown kind back to the default preview', () => {
    stubApi([])
    app('/devotions/preview/nonsense')
    expect(screen.getByRole('heading', { level: 1, name: 'Prayer Title' })).toBeInTheDocument()
  })
})

describe('stylesheet (mobile first, themed, accessible)', () => {
  it('is mobile first: wider layouts only ever appear inside min-width queries', () => {
    expect(css).not.toMatch(/max-width\s*:\s*\d+px\)/)             // no desktop-first overrides
    const base = css.split('@media')[0]
    expect(base).not.toMatch(/grid-template-columns:\s*repeat\(2/)  // phones get one column
    expect(css).toMatch(/@media \(min-width: 760px\)[\s\S]*is-parallel[\s\S]*repeat\(2/)
  })

  it('uses only design tokens for colour, so light and dark both work', () => {
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(css).not.toMatch(/\brgba?\(/)
  })

  it('keeps wording exact, wrapped and readable, with touch-sized controls', () => {
    expect(css).toMatch(/\.prayer-body\s*\{[^}]*white-space:\s*pre-wrap/)
    expect(css).toMatch(/\.prayer-body\s*\{[^}]*overflow-wrap:\s*anywhere/)
    expect(css).toMatch(/\.prayer-body\s*\{[^}]*max-width:\s*62ch/)
    expect(css).toMatch(/\.prayer-mode-nav button\s*\{[^}]*min-height:\s*46px/)
    expect(css).toMatch(/\.reading-toggle button\s*\{[^}]*min-height:\s*40px/)
  })
})
