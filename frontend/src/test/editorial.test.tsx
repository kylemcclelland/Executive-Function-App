import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { languageSummary, rightsSummary, sourceSummary, whyNot } from '../lib/editorial'
import { LANGUAGE_KEY } from '../lib/devotions'
import type { EditorialAccess, EditorialBrief, EditorialDevotion, EditorialEvent, EditorialPreview, EditorialText, PreviewText, TextStatus } from '../types/devotions'
import css from '../components/editorial/editorial.css?raw'

// Neutral filler records that exist only inside these tests (never in the app, a database or a seed).
const stamp = '2026-11-09T12:00:00Z'
const makeText = (fields: Partial<EditorialText> = {}): EditorialText => ({
  id: 't-en', devotion_slug: 'filler', slot: 'main', language: 'en', position: 0, title: null, body: 'English filler wording', has_body: true, is_translation: false, translator: null,
  source_title: 'A Test Source Book', source_authority: 'A Test Authority', source_edition: '1st test edition', source_date: '1885', source_url: 'https://example.org/source', source_retrieved_at: stamp,
  attribution: 'Filler attribution line', license_status: 'public_domain', license_notes: 'Public domain basis: filler note', rights_cleared: true, status: 'proposed', entered_by: 'seed:test',
  source_verified_by: null, source_verified_at: null, approved_by: null, approved_at: null, approval_current: false, problems: [], last_event: null, updated_at: stamp, ...fields,
})
const withheld = (fields: Partial<EditorialText> = {}) => makeText({ id: 't-la', language: 'la', body: '', has_body: false, license_status: 'restricted', rights_cleared: false, source_title: 'A Restricted Source', source_url: 'https://example.org/restricted', problems: ['No wording is held for this text, so it cannot be verified or approved (obtain it from a source whose terms permit reproduction)', 'Reproduction rights are not cleared: the wording may be cited and linked, not republished'], ...fields })
const makeDevotion = (fields: Partial<EditorialDevotion> = {}): EditorialDevotion => ({
  id: 'd1', slug: 'filler', title: 'Filler Devotion', subtitle: 'A short filler description', category: 'Daily Prayer', estimated_minutes: 1, overview: 'Overview filler.\n\nSecond paragraph filler.', background: null, significance: null,
  references: [{ label: 'A filler reference', url: 'https://example.org/ref' }], instructions: ['First instruction filler'], steps: [], choice_label: null, prose_origin: 'ai_draft', status: 'proposed', created_by: 'seed:test',
  source_verified_by: null, source_verified_at: null, approved_by: null, approved_at: null, published_at: null, approval_current: false, problems: [], publication_problems: ['The devotion itself has not been approved yet', 'No prayer text is approved yet: approve at least one (English or Latin)'],
  texts: [makeText(), withheld()], updated_at: stamp, ...fields,
})
const brief = (d: EditorialDevotion): EditorialBrief => ({
  id: d.id, slug: d.slug, title: d.title, category: d.category, status: d.status, prose_origin: d.prose_origin, texts_approved: d.texts.filter(t => t.status === 'approved').length, texts_total: d.texts.length, updated_at: d.updated_at,
  texts: d.texts.map(t => ({ slot: t.slot, language: t.language, status: t.status, license_status: t.license_status, has_body: t.has_body, source_verified: !!t.source_verified_at })),
})

let access: EditorialAccess
let devotions: EditorialDevotion[]
let events: EditorialEvent[]
let requests: { path: string; method: string; body?: Record<string, unknown> }[]
let failWith: { status: number; detail: string } | null
let overrides: Record<string, () => Response | Promise<Response>>
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

function setup(initial: EditorialDevotion[] = [makeDevotion()], roles: EditorialAccess = { is_editor: true, is_approver: true }) {
  devotions = initial; access = roles; events = []; requests = []; failWith = null; overrides = {}
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const path = input.replace('/api', '')
    const method = options?.method ?? 'GET'
    const body = options?.body ? JSON.parse(options.body as string) : undefined
    requests.push({ path, method, body })
    if (overrides[path]) return overrides[path]()
    if (path === '/editorial-access') return json(access)
    if (path === '/devotions') return json([])
    if (path === '/editorial/devotions') return json(devotions.map(brief))
    const match = /^\/editorial\/devotions\/([^/]+)(?:\/(preview|events|texts\/([^/]+)\/transition|transition))?$/.exec(path)
    const found = devotions.find(d => d.id === match?.[1])
    if (!match || !found) return json({ detail: 'Devotion not found' }, 404)
    if (method === 'POST') {
      if (failWith) return json({ detail: failWith.detail }, failWith.status)
      if (match[3]) { const text = found.texts.find(t => t.id === match[3])!; text.status = body!.to as TextStatus; if (body!.to === 'approved') text.approval_current = true; return json(text) }
      found.status = body!.to as EditorialDevotion['status']
      return json(found)
    }
    if (match[2] === 'events') return json(events)
    if (match[2] === 'preview') {
      const preview: EditorialPreview = {
        id: found.id, slug: found.slug, title: found.title, subtitle: found.subtitle, category: found.category, estimated_minutes: found.estimated_minutes, bookmarked: false, has_text: true, overview: found.overview, background: found.background, significance: found.significance,
        references: found.references, instructions: found.instructions, steps: found.steps, choice_label: found.choice_label, devotion_status: found.status, prose_origin: found.prose_origin,
        texts: found.texts.map((t): PreviewText => ({ id: t.id, slot: t.slot, language: t.language, title: t.title, body: t.body, devotion_slug: found.slug, status: t.status, approval_current: t.approval_current, publicly_visible: t.approval_current && found.status === 'published', has_body: t.has_body, rights_cleared: t.rights_cleared, license_notes: t.license_notes, source: { title: t.source_title, authority: t.source_authority, edition: t.source_edition, date: t.source_date, translator: t.translator, is_translation: t.is_translation, attribution: t.attribution, url: t.source_url, license_status: t.license_status } })),
      }
      return json(preview)
    }
    return json(found)
  }))
  return client
}
function open(client: QueryClient, path: string) {
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
}
const posts = () => requests.filter(request => request.method === 'POST')
const review = async (devotion = makeDevotion(), roles?: EditorialAccess) => { const client = setup([devotion], roles); open(client, `/editorial/devotions/${devotion.id}`); await screen.findByRole('heading', { level: 1, name: devotion.title }) }

beforeEach(() => { window.localStorage.clear() })
afterEach(() => { vi.unstubAllGlobals() })

// ---- Access -------------------------------------------------------------------------------------------
describe('access to the editorial area', () => {
  it('tells a signed-in person with no role that the area is private, and asks the server for nothing else', async () => {
    const client = setup([makeDevotion()], { is_editor: false, is_approver: false })
    open(client, '/editorial/devotions')
    expect(await screen.findByRole('heading', { level: 1, name: 'Editorial review is private' })).toBeInTheDocument()
    expect(screen.getByText(/Signing in does not grant one/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to The Oratory' })).toHaveAttribute('href', '/devotions')
    expect(requests.map(request => request.path)).toEqual(['/editorial-access'])                   // the queue is never even requested
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it.each([['an editor', { is_editor: true, is_approver: false }], ['an approver', { is_editor: false, is_approver: true }]])('lets %s in', async (_who, roles) => {
    const client = setup([makeDevotion()], roles)
    open(client, '/editorial/devotions')
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })

  it.each([
    [401, 'Authentication required', /session couldn’t be verified/, true],
    [403, 'Forbidden', /doesn’t hold the editorial role/, false],
    [404, 'Not Found', /editorial service isn’t available on this server yet \(404 Not Found\)/, true],
    [500, 'Internal Server Error', /server error 500/, true],
  ])('treats a %s from the roles check as an error with its own message', async (status, detail, message, retry) => {
    const client = setup()
    overrides['/editorial-access'] = () => json({ detail }, status)
    open(client, '/editorial/devotions')
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.queryByRole('button', { name: 'Try again' }) !== null).toBe(retry)
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText('Editorial review is private')).not.toBeInTheDocument()
  })

  it('treats a network failure as its own error', async () => {
    const client = setup()
    overrides['/editorial-access'] = () => { throw new TypeError('Failed to fetch') }
    open(client, '/editorial/devotions')
    expect(await screen.findByRole('alert')).toHaveTextContent('couldn’t reach the server')
  })

  it('explains in plain words why an action is not available', () => {
    expect(whyNot({ is_editor: true, is_approver: false }, 'approver')).toBe('Only an approver can do this.')
    expect(whyNot({ is_editor: false, is_approver: true }, 'editor')).toBe('Only an editor can do this.')
    expect(whyNot({ is_editor: true, is_approver: false }, 'editor')).toBeNull()
    expect(whyNot({ is_editor: true, is_approver: false }, 'either')).toBeNull()
  })
})

// ---- The queue ----------------------------------------------------------------------------------------
const approvedText = (fields: Partial<EditorialText> = {}) => makeText({ status: 'approved', approval_current: true, source_verified_at: stamp, source_verified_by: 'user_a', approved_at: stamp, approved_by: 'user_b', ...fields })
const queueData = () => [
  makeDevotion({ id: 'a', slug: 'alpha', title: 'Alpha Prayer', category: 'Daily Prayer', status: 'published', texts: [approvedText({ id: 'a-en' }), withheld({ id: 'a-la' })] }),
  makeDevotion({ id: 'b', slug: 'beta', title: 'Beta Prayer', category: 'Our Lady', status: 'proposed', texts: [makeText({ id: 'b-en' })] }),
  makeDevotion({ id: 'c', slug: 'gamma', title: 'Gamma Prayer', category: 'Mystery', status: 'pending_approval', texts: [] }),
]

describe('the review queue', () => {
  it('lists every devotion with its category, status, each language, source, rights, date and a review link', async () => {
    const client = setup(queueData())
    open(client, '/editorial/devotions')
    const table = await screen.findByRole('table', { name: 'Devotions awaiting editorial review' })
    expect(within(table).getAllByRole('columnheader').map(header => header.textContent)).toEqual(['Devotion', 'Category', 'Status', 'English text', 'Latin text', 'Source', 'Rights', 'Updated', 'Review'])
    const alpha = within(table).getByRole('row', { name: /Alpha Prayer/ })
    expect(within(alpha).getByRole('link', { name: 'Alpha Prayer' })).toHaveAttribute('href', '/editorial/devotions/a')
    expect(within(alpha).getByText('Daily Prayer')).toBeInTheDocument()
    expect(within(alpha).getByText('Published')).toBeInTheDocument()
    expect(within(alpha).getByRole('link', { name: 'Review Alpha Prayer' })).toBeInTheDocument()
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 3)
  })

  it('shows English and Latin separately, including wording that is withheld', async () => {
    const client = setup(queueData())
    open(client, '/editorial/devotions')
    const alpha = within(await screen.findByRole('row', { name: /Alpha Prayer/ }))
    const cells = alpha.getAllByRole('cell')
    const byLabel = Object.fromEntries(cells.map(cell => [cell.getAttribute('data-label'), cell.textContent]))
    expect(byLabel['English text']).toContain('Approved')
    expect(byLabel['Latin text']).toContain('Wording withheld')
    expect(byLabel['Rights']).toContain('Restricted')
    expect(byLabel['Source']).toContain('Partly verified')
    const gamma = within(screen.getByRole('row', { name: /Gamma Prayer/ })).getAllByRole('cell')
    expect(Object.fromEntries(gamma.map(cell => [cell.getAttribute('data-label'), cell.textContent]))['English text']).toContain('No text')
  })

  it('files an unrecognised category under its library category in the filter', async () => {
    const client = setup(queueData())
    open(client, '/editorial/devotions?category=other')
    const table = await screen.findByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(1 + 1)
    expect(within(table).getByText('Gamma Prayer')).toBeInTheDocument()
  })

  it('filters by workflow status and by category, together, and clears them', async () => {
    const client = setup(queueData())
    open(client, '/editorial/devotions')
    await screen.findByRole('table')
    const status = screen.getByRole('combobox', { name: 'Workflow status' })
    const category = screen.getByRole('combobox', { name: 'Category' })
    await userEvent.selectOptions(status, 'proposed')
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(2)
    expect(screen.getByRole('status')).toHaveTextContent('Showing 1 of 3')
    await userEvent.selectOptions(category, 'our-lady')
    expect(within(screen.getByRole('table')).getByText('Beta Prayer')).toBeInTheDocument()
    await userEvent.selectOptions(category, 'saints')
    expect(screen.getByText('Nothing matches these filters')).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: 'Clear filters' })[0])
    expect(within(await screen.findByRole('table')).getAllByRole('row')).toHaveLength(4)
  })

  it('offers every workflow status as a filter', async () => {
    const client = setup(queueData())
    open(client, '/editorial/devotions')
    await screen.findByRole('table')
    const options = [...screen.getByRole('combobox', { name: 'Workflow status' }).querySelectorAll('option')].map(option => option.textContent)
    expect(options).toEqual(['All statuses', 'Proposed', 'Source verified', 'Awaiting approval', 'Approved', 'Published'])
  })

  it('has a calm empty state when nothing has been drafted, and says drafts are never made from this page', async () => {
    const client = setup([])
    open(client, '/editorial/devotions')
    expect(await screen.findByText('The review queue is empty')).toBeInTheDocument()
    expect(screen.getByText(/never from this page/)).toBeInTheDocument()
  })

  it('reports a failed queue as an error, never as an empty queue', async () => {
    const client = setup(queueData())
    overrides['/editorial/devotions'] = () => json({ detail: 'down' }, 503)
    open(client, '/editorial/devotions')
    expect(await screen.findByRole('alert')).toHaveTextContent('server error 503')
    expect(screen.queryByText('The review queue is empty')).not.toBeInTheDocument()
  })

  it('summarises languages, sources and rights from the texts alone', () => {
    const [alpha, beta, gamma] = queueData().map(brief)
    expect(languageSummary(alpha, 'en')).toMatchObject({ label: 'Approved', tone: 'good' })
    expect(languageSummary(alpha, 'la')).toMatchObject({ label: 'Wording withheld', tone: 'stop' })
    expect(languageSummary(gamma, 'en')).toMatchObject({ label: 'No text' })
    expect(sourceSummary(beta.texts).label).toBe('Not verified')
    expect(rightsSummary(alpha.texts)).toMatchObject({ label: 'Restricted' })
    expect(rightsSummary(beta.texts)).toMatchObject({ label: 'Cleared' })
    expect(rightsSummary([])).toMatchObject({ label: '—' })
  })
})

// ---- The review screen --------------------------------------------------------------------------------
describe('reviewing one devotion', () => {
  it('shows the devotion information, with its prose labelled as unapproved', async () => {
    await review()
    expect(screen.getByText('A short filler description')).toBeInTheDocument()
    expect(screen.getByText('Overview filler.')).toBeInTheDocument()
    expect(screen.getByText('First instruction filler')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'A filler reference' })).toHaveAttribute('href', 'https://example.org/ref')
    const info = screen.getByRole('region', { name: 'Devotion information' })
    expect(within(info).getByRole('note')).toHaveTextContent('Unapproved editorial prose')
    expect(within(info).getByRole('note')).toHaveTextContent('drafted with AI assistance')
  })

  it.each(['approved', 'published'] as const)('drops the unapproved label once the devotion is %s', async status => {
    await review(makeDevotion({ status }))
    expect(within(screen.getByRole('region', { name: 'Devotion information' })).queryByRole('note')).not.toBeInTheDocument()
  })

  it('does not label prose that was not AI-drafted', async () => {
    await review(makeDevotion({ prose_origin: null }))
    expect(within(screen.getByRole('region', { name: 'Devotion information' })).queryByRole('note')).not.toBeInTheDocument()
  })

  it('shows the English text with its exact wording, source, edition, rights and history', async () => {
    await review()
    const text = screen.getByRole('article', { name: 'English text: Filler Devotion' })
    expect(within(text).getByText('English filler wording')).toBeInTheDocument()
    for (const fact of ['A Test Source Book', 'A Test Authority', '1st test edition', '1885', 'Public domain', 'Public domain basis: filler note', 'seed:test']) expect(within(text).getAllByText(new RegExp(fact)).length).toBeGreaterThan(0)
    expect(within(text).getByRole('link', { name: /example\.org\/source/ })).toHaveAttribute('href', 'https://example.org/source')
    expect(within(text).getByText('Original-language text, not a translation')).toBeInTheDocument()
  })

  it('shows translation attribution, including when the source names no translator', async () => {
    await review(makeDevotion({ texts: [makeText({ is_translation: true, translator: 'Translator not named in the source' })] }))
    expect(screen.getByText('Translated by Translator not named in the source')).toBeInTheDocument()
  })

  it('never makes a non-web address clickable', async () => {
    await review(makeDevotion({ texts: [makeText({ source_url: 'javascript:alert(1)' })] }))
    expect(screen.queryByRole('link', { name: /javascript/ })).not.toBeInTheDocument()
  })

  it('shows a missing source field as not recorded rather than hiding it', async () => {
    await review(makeDevotion({ texts: [makeText({ source_authority: null, source_edition: null, source_date: null })] }))
    expect(screen.getAllByText('Not recorded').length).toBeGreaterThanOrEqual(3)
  })

  it('explains withheld wording instead of showing an empty box, and points to the source', async () => {
    await review()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'la')
    const text = screen.getByRole('article', { name: 'Latin text: Filler Devotion' })
    expect(within(text).getByRole('note')).toHaveTextContent('Wording withheld.')
    expect(within(text).getByRole('note')).toHaveTextContent('only the citation and a link are kept')
    expect(within(text).getByRole('link', { name: /Read it at the source/ })).toHaveAttribute('href', 'https://example.org/restricted')
    expect(text.querySelector('.prayer-body')).toBeNull()
    expect(within(text).getAllByText('Rights not cleared: wording withheld').length).toBeGreaterThan(0)
    expect(within(text).getByText('No wording held')).toBeInTheDocument()
  })

  it('lists exactly what stands between a proposed text and verification', async () => {
    await review()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'la')
    const text = screen.getByRole('article', { name: 'Latin text: Filler Devotion' })
    const list = within(text).getByText('Before this can be verified').closest('div')!
    expect(within(list).getAllByRole('listitem')).toHaveLength(2)
  })
})

describe('English and Latin in the editorial interface', () => {
  it('has the same language dropdown, English by default, and switching it changes nothing on the server', async () => {
    await review()
    const select = screen.getByRole('combobox', { name: 'Language' })
    expect(select).toHaveValue('en')
    expect(screen.getByRole('article', { name: 'English text: Filler Devotion' })).toBeInTheDocument()
    await userEvent.selectOptions(select, 'la')
    expect(screen.getByRole('article', { name: 'Latin text: Filler Devotion' })).toBeInTheDocument()
    expect(screen.queryByRole('article', { name: 'English text: Filler Devotion' })).not.toBeInTheDocument()
    expect(window.localStorage.getItem(LANGUAGE_KEY)).toBe('la')
    expect(posts()).toEqual([])                                                      // a language change never touches a status
    expect(devotions[0].texts.map(t => t.status)).toEqual(['proposed', 'proposed'])
  })

  it('says so, and never invents a text, when a language has none for a prayer', async () => {
    await review(makeDevotion({ texts: [makeText()] }))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'la')
    const note = screen.getByText(/No Latin text has been entered for/)
    expect(note).toBeInTheDocument()
    expect(screen.getByText(/It exists in English: switch the language above to review it\./)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('English filler wording')
  })

  it('compares English and Latin side by side, each with its own source and status, and offers no actions there', async () => {
    await review(makeDevotion({ texts: [makeText(), withheld({ license_status: 'public_domain', rights_cleared: true, body: 'Latin filler wording', has_body: true, source_title: 'A Latin Source' })] }))
    await userEvent.click(screen.getByRole('button', { name: /Compare languages side by side/ }))
    const english = screen.getByRole('article', { name: 'English text: Filler Devotion' })
    const latin = screen.getByRole('article', { name: 'Latin text: Filler Devotion' })
    expect(within(english).getByText('English filler wording')).toBeInTheDocument()
    expect(within(latin).getByText('Latin filler wording')).toBeInTheDocument()
    expect(within(english).getByText('A Test Source Book')).toBeInTheDocument()
    expect(within(latin).getByText('A Latin Source')).toBeInTheDocument()
    expect(english.parentElement!.parentElement).toHaveClass('compare-grid')
    expect(within(english).queryByRole('button')).not.toBeInTheDocument()            // read-only: act from the single-language view
    expect(screen.getByRole('button', { name: /Compare languages side by side/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('says plainly in a comparison when one language has no text', async () => {
    await review(makeDevotion({ texts: [makeText()] }))
    await userEvent.click(screen.getByRole('button', { name: /Compare languages side by side/ }))
    expect(screen.getByText(/No Latin text entered/)).toBeInTheDocument()
  })

  it('lets a reviewer jump from the comparison to acting on one language', async () => {
    await review()
    await userEvent.click(screen.getByRole('button', { name: /Compare languages side by side/ }))
    await userEvent.click(screen.getByRole('button', { name: /Review the Latin text to act on it/ }))
    expect(screen.getByRole('combobox', { name: 'Language' })).toHaveValue('la')
    expect(screen.getByRole('button', { name: /Compare languages side by side/ })).toHaveAttribute('aria-pressed', 'false')
  })
})

// ---- Actions, roles and confirmation ----------------------------------------------------------------------
const enText = () => screen.getByRole('article', { name: /English text/ })
const actions = (scope: HTMLElement) => within(scope).queryAllByRole('button').map(button => button.textContent)

describe('actions on a prayer text', () => {
  it('offers the actions that fit where the text stands, and nothing else', async () => {
    await review()
    expect(actions(enText())).toEqual(['Mark source as verified', 'Reject this text'])
    for (const [status, expected] of [['source_verified', ['Submit for approval', 'Return for further research', 'Reject this text']], ['pending_approval', ['Approve this text', 'Reject approval', 'Return for further research']], ['approved', ['Withdraw approval']]] as const) {
      document.body.innerHTML = ''
      await review(makeDevotion({ texts: [makeText({ status })] }))
      expect(actions(enText())).toEqual(expected)
    }
  })

  it('lets an editor mark a verifiable source as verified only after confirming', async () => {
    await review()
    await userEvent.click(within(enText()).getByRole('button', { name: 'Mark source as verified' }))
    const dialog = screen.getByRole('dialog', { name: 'Mark this source as verified?' })
    expect(within(dialog).getByText(/matches its cited source exactly/)).toBeInTheDocument()
    expect(within(dialog).getByText(/A Test Source Book, 1st test edition/)).toBeInTheDocument()
    expect(posts()).toEqual([])                                                      // opening the dialog changes nothing
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(posts()).toEqual([])
    await userEvent.click(within(enText()).getByRole('button', { name: 'Mark source as verified' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Mark source as verified' }))
    await waitFor(() => expect(posts()).toEqual([{ path: '/editorial/devotions/d1/texts/t-en/transition', method: 'POST', body: { to: 'source_verified' } }]))
  })

  it('will not offer verification while something is unresolved, and says what', async () => {
    await review(makeDevotion({ texts: [makeText({ problems: ['Name the translator'] })] }))
    const button = within(enText()).getByRole('button', { name: 'Mark source as verified' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', 'Resolve the points listed above first.')
    expect(within(enText()).getByText('Name the translator')).toBeInTheDocument()
  })

  it('keeps approval for approvers: an editor sees why it is unavailable', async () => {
    await review(makeDevotion({ texts: [makeText({ status: 'pending_approval' })] }), { is_editor: true, is_approver: false })
    const approve = within(enText()).getByRole('button', { name: 'Approve this text' })
    expect(approve).toBeDisabled()
    expect(within(enText()).getByText(/Only an approver can do this\./)).toBeInTheDocument()
    await userEvent.click(approve)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(posts()).toEqual([])
  })

  it('keeps editing steps for editors: an approver cannot verify', async () => {
    await review(makeDevotion(), { is_editor: false, is_approver: true })
    expect(within(enText()).getByRole('button', { name: 'Mark source as verified' })).toBeDisabled()
    expect(within(enText()).getByText(/Only an editor can do this\./)).toBeInTheDocument()
  })

  it('asks an approver to confirm the exact version before approving, and approves only on confirmation', async () => {
    await review(makeDevotion({ texts: [makeText({ status: 'pending_approval', source_verified_at: stamp, source_verified_by: 'user_a' })] }))
    await userEvent.click(within(enText()).getByRole('button', { name: 'Approve this text' }))
    const dialog = screen.getByRole('dialog', { name: 'Approve this exact text?' })
    expect(within(dialog).getByText(/Approving the English text of “Filler Devotion”/)).toBeInTheDocument()
    expect(within(dialog).getByText(/applies to exactly this wording and these source details; changing any of them cancels it/)).toBeInTheDocument()
    expect(posts()).toEqual([])
    await userEvent.click(within(dialog).getByRole('button', { name: 'Approve this text' }))
    await waitFor(() => expect(posts()).toEqual([{ path: '/editorial/devotions/d1/texts/t-en/transition', method: 'POST', body: { to: 'approved' } }]))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it.each([
    ['proposed', 'Reject this text', 'proposed', 'reject_text', 'Not the right edition'],
    ['source_verified', 'Return for further research', 'proposed', 'return_for_research', 'Check the edition'],
    ['pending_approval', 'Reject approval', 'proposed', 'reject_approval', 'Wording differs from the source'],
    ['approved', 'Withdraw approval', 'proposed', 'withdraw', 'Found an error'],
  ] as const)('requires a reason to turn down a text that is %s, and records the decision', async (status, label, to, decision, reason) => {
    await review(makeDevotion({ texts: [makeText({ status })] }))
    await userEvent.click(within(enText()).getByRole('button', { name: label }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: label }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Please give a reason')       // nothing is sent without one
    expect(posts()).toEqual([])
    await userEvent.type(within(dialog).getByRole('textbox'), reason)
    await userEvent.click(within(dialog).getByRole('button', { name: label }))
    await waitFor(() => expect(posts()).toEqual([{ path: '/editorial/devotions/d1/texts/t-en/transition', method: 'POST', body: { to, note: reason, decision } }]))
  })

  it('shows the server’s answer in the dialog if an action is refused, and keeps the dialog open', async () => {
    await review(makeDevotion({ texts: [makeText({ status: 'pending_approval' })] }))
    failWith = { status: 409, detail: 'Reproduction rights are not cleared' }
    await userEvent.click(within(enText()).getByRole('button', { name: 'Approve this text' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve this text' }))
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent('Reproduction rights are not cleared')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('shows the latest decision and its reason on the text', async () => {
    const last: EditorialEvent = { id: 'e1', text_id: 't-en', actor: 'user_reviewer', action: 'return_for_research', from_status: 'source_verified', to_status: 'proposed', note: 'Check the edition', created_at: stamp }
    await review(makeDevotion({ texts: [makeText({ last_event: last })] }))
    expect(within(enText()).getByText('Returned for further research')).toBeInTheDocument()
    expect(within(enText()).getByText(/Check the edition/)).toBeInTheDocument()
    expect(within(enText()).getByText(/user_reviewer/)).toBeInTheDocument()
  })

  it('warns when an approval no longer matches the content', async () => {
    await review(makeDevotion({ texts: [makeText({ status: 'approved', approval_current: false })] }))
    expect(within(enText()).getByText('Approval no longer matches')).toBeInTheDocument()
  })
})

describe('the devotion’s own approval and publication', () => {
  it('keeps the devotion’s approval separate from its texts, and lists what publishing still needs', async () => {
    await review(makeDevotion({ status: 'approved' }))
    const section = screen.getByRole('region', { name: 'Devotion status and publication' })
    expect(within(section).getByText(/separate from the approval of each prayer text/)).toBeInTheDocument()
    expect(within(section).getByText('No prayer text is approved yet: approve at least one (English or Latin)')).toBeInTheDocument()
    expect(within(section).getByRole('button', { name: 'Publish to The Oratory' })).toBeDisabled()
    expect(within(section).getByRole('list', { name: 'Workflow' })).toBeInTheDocument()
    expect(within(section).getByText('Approved', { selector: 'li span' }).closest('li')).toHaveAttribute('aria-current', 'step')
  })

  it('shows which languages readers would see, text by text', async () => {
    await review(makeDevotion({ status: 'approved', publication_problems: [], texts: [approvedText(), withheld()] }))
    const visibility = screen.getByRole('list', { name: 'What readers would see' })
    expect(within(visibility).getByText(/English:/).parentElement).toHaveTextContent('all 1 approved: shown')
    expect(within(visibility).getByText(/Latin:/).parentElement).toHaveTextContent('0 of 1 approved: the rest stay hidden')
  })

  it('publishes only after a confirmation that says what readers will and will not see', async () => {
    await review(makeDevotion({ status: 'approved', publication_problems: [], texts: [approvedText(), withheld()] }))
    await userEvent.click(screen.getByRole('button', { name: 'Publish to The Oratory' }))
    const dialog = screen.getByRole('dialog', { name: 'Publish to The Oratory?' })
    expect(within(dialog).getByText(/Only prayer texts that are individually approved will be shown/)).toBeInTheDocument()
    expect(within(dialog).getByText(/0 of 1 approved: the rest stay hidden/)).toBeInTheDocument()
    expect(posts()).toEqual([])
    await userEvent.click(within(dialog).getByRole('button', { name: 'Publish to The Oratory' }))
    await waitFor(() => expect(posts()).toEqual([{ path: '/editorial/devotions/d1/transition', method: 'POST', body: { to: 'published' } }]))
  })

  it('keeps publishing for approvers, and says so', async () => {
    await review(makeDevotion({ status: 'approved', publication_problems: [], texts: [approvedText()] }), { is_editor: true, is_approver: false })
    expect(screen.getByRole('button', { name: 'Publish to The Oratory' })).toBeDisabled()
    expect(screen.getByRole('region', { name: 'Devotion status and publication' })).toHaveTextContent('Only an approver can do this.')
  })

  it('says when every condition for publishing is met', async () => {
    await review(makeDevotion({ status: 'approved', publication_problems: [], texts: [approvedText()] }))
    expect(screen.getByText('All conditions are met')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Publish to The Oratory' })).toBeEnabled()
  })

  it('offers to unpublish or withdraw a published devotion, withdrawing only with a reason', async () => {
    await review(makeDevotion({ status: 'published', publication_problems: [], texts: [approvedText()] }))
    expect(actions(screen.getByRole('group', { name: 'Devotion actions' }))).toEqual(['Unpublish', 'Withdraw approval'])
    await userEvent.click(within(screen.getByRole('group', { name: 'Devotion actions' })).getByRole('button', { name: 'Withdraw approval' }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Withdraw approval' }))
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Please give a reason')
  })

  it('lists what stops the devotion being verified', async () => {
    await review(makeDevotion({ problems: ['Cite at least one source for the background'] }))
    const section = screen.getByRole('region', { name: 'Devotion status and publication' })
    expect(within(section).getByText('Cite at least one source for the background')).toBeInTheDocument()
    expect(within(section).getByRole('button', { name: 'Mark devotion details as verified' })).toBeDisabled()
  })

  it('links to the private preview', async () => {
    await review()
    expect(screen.getByRole('link', { name: /Preview as readers will see it/ })).toHaveAttribute('href', '/editorial/devotions/d1/preview')
  })
})

describe('the structure of a complex devotion', () => {
  const rosary = () => makeDevotion({
    id: 'r', slug: 'rosary', title: 'Filler Rosary', choice_label: 'Mysteries', texts: [makeText({ id: 'r-en', devotion_slug: 'rosary', slot: 'closing' })],
    steps: [
      { kind: 'prayer', title: 'Opening prayer', instruction: null, text_slot: 'main', devotion_slug: 'inner', repeat: null, section: 'Opening', group: null, optional: false },
      { kind: 'instruction', title: '1. First set', instruction: 'Recall it.', text_slot: null, repeat: null, section: 'Set A', group: 'Set A', optional: false },
      { kind: 'instruction', title: '1. Second set', instruction: 'Recall it.', text_slot: null, repeat: null, section: 'Set B', group: 'Set B', optional: false },
      { kind: 'prayer', title: 'A custom', instruction: null, text_slot: 'custom', repeat: null, section: 'Closing', group: null, optional: true },
      { kind: 'prayer', title: 'Closing prayer', instruction: null, text_slot: 'closing', repeat: null, section: 'Closing', group: null, optional: false },
    ],
  })

  it('shows the outline with each choice collapsed and the optional custom marked', async () => {
    const client = setup([rosary(), makeDevotion({ id: 'i', slug: 'inner', title: 'Inner Prayer', status: 'published', texts: [approvedText()] })])
    open(client, '/editorial/devotions/r')
    const structure = await screen.findByRole('region', { name: 'Structure' })
    expect(within(structure).getByText('5 steps. Optional customs are marked; they never hold up publication.')).toBeInTheDocument()
    expect([...structure.querySelectorAll('details.sequence-choice summary')].map(summary => summary.textContent)).toEqual(['Set A', 'Set B'])
    expect(within(structure).getByText('Optional custom')).toBeInTheDocument()
  })

  it('lists the prayers it reuses from other devotions with their own status, linking to them', async () => {
    const client = setup([rosary(), makeDevotion({ id: 'i', slug: 'inner', title: 'Inner Prayer', status: 'published', texts: [approvedText()] })])
    open(client, '/editorial/devotions/r')
    const reused = (await screen.findByRole('region', { name: 'Structure' })).querySelector('.reused-prayers') as HTMLElement
    expect(within(reused).getByRole('link', { name: 'Inner Prayer' })).toHaveAttribute('href', '/editorial/devotions/i')
    expect(within(reused).getByText('Published')).toBeInTheDocument()
    expect(within(reused).getByText(/shown from their own devotion, never copied/)).toBeInTheDocument()
  })

  it('flags a reused prayer whose devotion does not exist', async () => {
    const client = setup([rosary()])
    open(client, '/editorial/devotions/r')
    const reused = (await screen.findByRole('region', { name: 'Structure' })).querySelector('.reused-prayers') as HTMLElement
    expect(within(reused).getByText('Devotion not found')).toBeInTheDocument()
  })

  it('says a devotion that only reuses prayers holds none of its own', async () => {
    const reusing = rosary()
    reusing.texts = []
    const client = setup([reusing])
    open(client, '/editorial/devotions/r')
    expect(await screen.findByText(/holds no prayer texts of its own; it reuses prayers from other devotions/)).toBeInTheDocument()
  })

  it('has no structure section for a simple prayer', async () => {
    await review()
    expect(screen.queryByRole('region', { name: 'Structure' })).not.toBeInTheDocument()
  })
})

describe('activity and errors on the review screen', () => {
  it('shows who did what and why, newest first, with the wording never in it', async () => {
    const client = setup()
    events = [
      { id: '1', text_id: null, actor: 'seed:devotion-drafts-v1', action: 'seeded', from_status: null, to_status: 'proposed', note: 'DEV-001', created_at: stamp },
      { id: '2', text_id: 't-en', actor: 'user_reviewer', action: 'return_for_research', from_status: 'source_verified', to_status: 'proposed', note: 'Check the edition', created_at: stamp },
    ]
    open(client, '/editorial/devotions/d1')
    await screen.findByRole('heading', { level: 1, name: 'Filler Devotion' })
    await userEvent.click(screen.getByText('Activity'))
    const items = await within(document.querySelector('.activity-log')!).findAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Returned for further research')
    expect(items[0]).toHaveTextContent('EN · main')
    expect(items[0]).toHaveTextContent('Check the edition')
    expect(items[1]).toHaveTextContent('Draft record created')
    expect(document.querySelector('.activity-log')!.textContent).not.toContain('English filler wording')
  })

  it.each([[404, 'Devotion not found', /Devotion not found/], [403, 'Forbidden', /doesn’t hold the editorial role/], [500, 'boom', /server error 500/]])('treats a %s on the devotion as its own error', async (status, detail, message) => {
    const client = setup()
    overrides['/editorial/devotions/d1'] = () => json({ detail }, status)
    open(client, '/editorial/devotions/d1')
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.getByRole('link', { name: 'Back to the review queue' })).toHaveAttribute('href', '/editorial/devotions')
  })
})

// ---- The private preview ----------------------------------------------------------------------------------
describe('the private preview', () => {
  const preview = async (devotion = makeDevotion(), roles?: EditorialAccess) => {
    const client = setup([devotion], roles)
    open(client, `/editorial/devotions/${devotion.id}/preview`)
    await screen.findByRole('heading', { level: 1, name: devotion.title })
  }

  it('is plainly an unpublished preview for editors, and reuses the public components', async () => {
    await preview()
    const banner = screen.getByText(/Unpublished preview\./).closest('aside')!
    expect(banner).toHaveTextContent('Only editors and approvers can see this page')
    expect(banner).toHaveTextContent('Nothing here is public')
    expect(within(banner).getByText('Proposed')).toBeInTheDocument()
    expect(banner).toHaveTextContent('It is not visible to readers.')
    for (const name of ['Overview', 'How to Pray', 'Prayer Text']) expect(screen.getByRole('heading', { level: 2, name })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Review/ })).toHaveAttribute('href', '/editorial/devotions/d1')
  })

  it('shows unapproved wording, each text marked as not visible to readers', async () => {
    await preview()
    expect(screen.getByText('English filler wording')).toBeInTheDocument()
    expect(screen.getByText('Proposed: not visible to readers')).toBeInTheDocument()
  })

  it('marks what readers would see once published', async () => {
    await preview(makeDevotion({ status: 'published', texts: [approvedText(), withheld({ license_status: 'public_domain', rights_cleared: true, body: 'Latin filler wording', has_body: true })] }))
    expect(screen.getByText('Approved: visible to readers')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'la')
    expect(screen.getByText('Proposed: not visible to readers')).toBeInTheDocument()
  })

  it('supports English and Latin through the same dropdown, with the missing-language message', async () => {
    await preview(makeDevotion({ texts: [makeText()] }))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'la')
    expect(screen.getByText('Latin text is not yet available for this devotion.')).toBeInTheDocument()
    expect(screen.queryByText('English filler wording')).not.toBeInTheDocument()
  })

  it('shows withheld wording as withheld, not as an empty prayer', async () => {
    await preview()
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'la')
    expect(screen.getByText('No wording is held for this text. See its source.')).toBeInTheDocument()
  })

  it('labels AI-drafted prose as unapproved until the devotion is approved', async () => {
    await preview()
    expect(screen.getAllByRole('note').some(note => /Unapproved editorial prose/.test(note.textContent ?? ''))).toBe(true)
  })

  it('does not label approved prose', async () => {
    await preview(makeDevotion({ status: 'approved' }))
    expect(screen.queryByText(/Unapproved editorial prose/)).not.toBeInTheDocument()
  })

  it('is closed to a signed-in person with no editorial role', async () => {
    const client = setup([makeDevotion()], { is_editor: false, is_approver: false })
    open(client, '/editorial/devotions/d1/preview')
    expect(await screen.findByRole('heading', { name: 'Editorial review is private' })).toBeInTheDocument()
    expect(requests.some(request => request.path.endsWith('/preview'))).toBe(false)
  })

  it('treats a missing devotion as its own error', async () => {
    const client = setup([makeDevotion()])
    open(client, '/editorial/devotions/nope/preview')
    expect(await screen.findByRole('alert')).toHaveTextContent('Devotion not found')
  })

  it('does not appear in the public Oratory', async () => {
    const client = setup([makeDevotion({ status: 'published' })])
    open(client, '/devotions')
    expect(await screen.findByText('No devotions have been added yet')).toBeInTheDocument()
  })
})

// ---- Look and feel -----------------------------------------------------------------------------------------
describe('stylesheet (mobile first, themed, accessible)', () => {
  it('stacks the queue into cards on a phone and becomes a table only inside a min-width query', () => {
    expect(css).not.toMatch(/max-width\s*:\s*\d+px\)/)
    const base = css.split('@media')[0]
    expect(base).toMatch(/\.review-queue tr\s*\{[^}]*border-top:\s*3px solid var\(--gold\)/)
    expect(base).toMatch(/\.review-queue td::before\s*\{\s*content:\s*attr\(data-label\)/)
    expect(css).toMatch(/@media \(min-width: 1240px\)[\s\S]*\.review-queue\s*\{\s*display:\s*table/)
    expect(css).toMatch(/@media \(min-width: 760px\)[\s\S]*\.compare-grid\s*\{\s*grid-template-columns:\s*repeat\(2/)
  })

  it('compares languages in one column on a phone', () => {
    expect(css.split('@media')[0]).toMatch(/\.compare-grid\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/)
  })

  it('uses only design tokens for colour, so light and dark both work', () => {
    expect(css).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
    expect(css).not.toMatch(/\brgba?\(/)
  })

  it('gives every status badge a distinct treatment, with a label and an icon, never colour alone', async () => {
    for (const tone of ['progress', 'good', 'attention', 'stop']) expect(css).toMatch(new RegExp(`\\.status-badge\\.is-${tone}\\s*\\{`))
    await review()
    const badges = [...document.querySelectorAll('.status-badge')]
    expect(badges.length).toBeGreaterThan(0)
    for (const badge of badges) {
      expect(badge.textContent!.trim().length).toBeGreaterThan(0)
      expect(badge.querySelector('svg')).not.toBeNull()
    }
  })

  it('keeps action buttons touch-sized', () => {
    expect(css).toMatch(/\.text-actions button, \.text-actions a\s*\{[^}]*min-height:\s*44px/)
    expect(css).toMatch(/\.editorial select, \.language-select select\s*\{[^}]*min-height:\s*40px/)
  })
})
