import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { DevotionView } from '../components/devotions/DevotionView'
import { COLLECTION_PREFIX, splitCollection } from '../lib/devotions'
import type { Devotion, PrayerText } from '../types/devotions'

// Every wording below is neutral filler for the tests, never a real prayer.
const source = { title: 'A Test Document', edition: null, translator: null, is_translation: false, attribution: 'Filler attribution', url: null, license_status: 'unverified' as const }
const text = (slot: string, language: string, body: string, fields: Partial<PrayerText> = {}): PrayerText => ({ id: `${slot}-${language}`, slot, language, title: null, body, source, ...fields })
const pair = (name: string, title: string, latinTitle: string, order: string) => [
  text(`${COLLECTION_PREFIX}${name}`, 'en', `English ${order}\nV. Filler versicle`, { title }),
  text(`${COLLECTION_PREFIX}${name}`, 'la', `Latin ${order}`, { title: latinTitle }),
]
const base: Devotion = { id: 'd', slug: 'filler-rosary', title: 'Filler Rosary', subtitle: null, category: null, estimated_minutes: null, bookmarked: false, has_text: true, overview: 'Overview filler.', background: null, significance: null, references: [], instructions: [], steps: [], texts: [] }
const rosary: Devotion = { ...base, texts: [...pair('first', 'First prayer', 'Prima', 'one'), ...pair('second', 'Second prayer', 'Secunda', 'two'), ...pair('third', 'Third prayer', 'Tertia', 'three')] }
const latinMissing: Devotion = { ...base, texts: [...pair('first', 'First prayer', 'Prima', 'one'), text(`${COLLECTION_PREFIX}second`, 'en', 'English two', { title: 'Second prayer' })] }

const view = (devotion: Devotion) => render(<MemoryRouter><DevotionView devotion={devotion} /></MemoryRouter>)
const collection = () => within(screen.getByRole('region', { name: 'The Prayers of the Rosary' }))
const bodies = () => [...document.querySelectorAll<HTMLElement>('.prayer-collection .prayer-body')].map(element => [element.getAttribute('lang'), element.textContent])

beforeEach(() => { window.localStorage.clear() })

describe('the collection of Rosary prayers', () => {
  it('lists the prayers in the order they were given, with a numbered jump list that links to each', () => {
    view(rosary)
    const links = within(screen.getByRole('navigation', { name: 'The Prayers of the Rosary' })).getAllByRole('link')
    expect(links.map(link => link.textContent)).toEqual(['First prayer', 'Second prayer', 'Third prayer'])
    expect(links.map(link => link.getAttribute('href'))).toEqual(['#prayer-collection-first', '#prayer-collection-second', '#prayer-collection-third'])
    expect(document.getElementById('prayer-collection-second')).toBeInTheDocument()
    expect(collection().getAllByRole('heading', { level: 3 }).map(heading => heading.textContent)).toEqual(['1First prayer', '2Second prayer', '3Third prayer'])
  })

  it('shows English by default and switches to Latin with the Language dropdown, keeping every prayer in order', async () => {
    view(rosary)
    expect(bodies().map(([language]) => language)).toEqual(['en', 'en', 'en'])
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'la')
    expect(bodies()).toEqual([['la', 'Latin one'], ['la', 'Latin two'], ['la', 'Latin three']])
  })

  it('shows Latin and English side by side on request, Latin first, and returns to one language', async () => {
    view(rosary)
    await userEvent.click(collection().getByRole('button', { name: 'Side by side' }))
    expect(bodies()).toEqual([['la', 'Latin one'], ['en', 'English one\nV. Filler versicle'], ['la', 'Latin two'], ['en', 'English two\nV. Filler versicle'], ['la', 'Latin three'], ['en', 'English three\nV. Filler versicle']])
    expect(document.querySelectorAll('.collection-pair')).toHaveLength(3)
    await userEvent.click(collection().getByRole('button', { name: 'English' }))
    expect(bodies().map(([language]) => language)).toEqual(['en', 'en', 'en'])
  })

  it('never puts another language in place of a missing one, in either layout', async () => {
    view(latinMissing)
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'la')
    expect(bodies()).toEqual([['la', 'Latin one']])
    expect(collection().getByText('Latin text is not yet available for this prayer.')).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('English two\n')
    await userEvent.click(collection().getByRole('button', { name: 'Side by side' }))
    expect(collection().getByText('Latin text is not yet available for this prayer.')).toBeInTheDocument()
    expect(bodies()).toEqual([['la', 'Latin one'], ['en', 'English one\nV. Filler versicle'], ['en', 'English two']])
  })

  it('keeps the exact wording, including a verse on its own line', () => {
    view(rosary)
    const body = document.querySelector('.prayer-collection .prayer-body')
    expect(body?.textContent).toBe('English one\nV. Filler versicle')
    expect(body?.querySelector('.is-response')?.textContent).toBe('V. Filler versicle')
  })

  it('is absent when nothing is published, and the Prayer Text section does not contain the collection', () => {
    view({ ...base, texts: [] })
    expect(screen.queryByRole('region', { name: 'The Prayers of the Rosary' })).toBeNull()
    view({ ...base, texts: [text('main', 'en', 'Ordinary filler'), ...pair('first', 'First prayer', 'Prima', 'one')] })
    const ordinary = within(screen.getAllByRole('region', { name: 'Prayer Text' }).at(-1)!)
    expect(ordinary.getByText('Ordinary filler')).toBeInTheDocument()
    expect(ordinary.queryByText('English one', { exact: false })).toBeNull()
  })

  it('splits a devotion\'s texts without losing or duplicating any', () => {
    const reused = text('main', 'en', 'Reused filler', { devotion_slug: 'elsewhere' })
    const reusedWithCollectionName = text(`${COLLECTION_PREFIX}first`, 'en', 'Reused from elsewhere', { devotion_slug: 'elsewhere' })
    const all = [...rosary.texts, text('main', 'en', 'Own filler'), reused, reusedWithCollectionName]
    const { collection: groups, rest } = splitCollection(rosary, all)
    expect(groups.flatMap(group => group.versions)).toHaveLength(6)
    expect(rest.map(item => item.body)).toEqual(['Own filler', 'Reused filler', 'Reused from elsewhere'])    // another devotion's text is never claimed by this collection
    expect(groups.length * 2 + rest.length).toBe(all.length)
  })
})

describe('a library without an approval step', () => {
  it('labels a citation-only record clearly and never shows it as a prayer', () => {
    view({ ...base, texts: [text('main', 'en', 'English filler wording'), text('main', 'la', '', { source: { ...source, title: 'A Cited Edition' } })] })
    expect(screen.queryByText(/approved|published/i)).toBeNull()
    expect(document.querySelectorAll('.prayer-body')).toHaveLength(1)                 // only the English has wording to show
  })

  it('shows a citation-only Latin text as such, with its source, when Latin is chosen', async () => {
    view({ ...base, texts: [text('main', 'en', 'English filler wording'), text('main', 'la', '', { source: { ...source, title: 'A Cited Edition' } })] })
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Language' }), 'la')
    expect(screen.getByText('Citation only.')).toBeInTheDocument()
    expect(screen.getByText(/No wording is held for this text/)).toBeInTheDocument()
    expect(screen.getByText('A Cited Edition')).toBeInTheDocument()
    expect(document.querySelectorAll('.prayer-body')).toHaveLength(0)
  })

  it('shows the Rosary prayers with no approval or publication wording anywhere on the page', () => {
    view(rosary)
    expect(document.body.textContent).not.toMatch(/approv|publish|editorial|review queue/i)
  })
})

