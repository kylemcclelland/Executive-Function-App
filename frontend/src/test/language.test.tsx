import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { DevotionView } from '../components/devotions/DevotionView'
import { DEFAULT_LANGUAGE, LANGUAGE_KEY, SUPPORTED_LANGUAGES, availableLanguages, groupTexts, languageLabel, resolveLanguage, stepGroups, versionsFor, visibleSteps } from '../lib/devotions'
import type { Devotion, DevotionStep, PrayerText } from '../types/devotions'

// Every wording below is neutral filler for the tests, never a real prayer.
const source = { title: 'A Test Source Book', edition: '1st test edition', translator: null, is_translation: false, attribution: 'Filler attribution line', url: null, license_status: 'public_domain' as const }
const text = (slot: string, language: string, body: string, fields: Partial<PrayerText> = {}): PrayerText => ({ id: `${slot}-${language}`, slot, language, title: null, body, source, ...fields })
const base: Devotion = { id: 'd', slug: 'filler', title: 'Filler Devotion', subtitle: null, category: null, estimated_minutes: null, bookmarked: false, has_text: true, overview: 'Overview filler.', background: null, significance: null, references: [], instructions: [], steps: [], texts: [] }
const bilingual: Devotion = { ...base, texts: [text('main', 'en', 'English filler wording'), text('main', 'la', 'Latin filler wording')] }
const englishOnly: Devotion = { ...base, texts: [text('main', 'en', 'English filler wording')] }

function view(devotion: Devotion) {
  return render(<MemoryRouter><DevotionView devotion={devotion} /></MemoryRouter>)
}
const dropdown = () => screen.getByRole('combobox', { name: 'Language' })
const shown = () => [...document.querySelectorAll<HTMLElement>('.prayer-section .prayer-body')].map(element => [element.getAttribute('lang'), element.textContent])

beforeEach(() => { window.localStorage.clear() })
afterEach(() => { vi.unstubAllGlobals() })

describe('the Language dropdown', () => {
  it('is a compact dropdown labelled Language, near the top of the page, with no flags', () => {
    view(bilingual)
    const select = dropdown()
    expect(select.tagName).toBe('SELECT')
    expect([...select.querySelectorAll('option')].map(option => option.textContent)).toEqual(['English', 'Latin'])
    const title = screen.getByRole('heading', { level: 1 })
    const overview = screen.getByRole('heading', { level: 2, name: 'Overview' })
    expect(title.compareDocumentPosition(select) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()    // after the title...
    expect(select.compareDocumentPosition(overview) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()  // ...and before the Overview
    expect(document.body.textContent).not.toMatch(/[\u{1F1E6}-\u{1F1FF}]/u)                            // no flag emoji
  })

  it('defaults to English', () => {
    view(bilingual)
    expect(dropdown()).toHaveValue('en')
    expect(shown()).toEqual([['en', 'English filler wording']])
    expect(DEFAULT_LANGUAGE).toBe('en')
  })

  it('switches to Latin and back without reloading anything', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    view(bilingual)
    await userEvent.selectOptions(dropdown(), 'la')
    expect(shown()).toEqual([['la', 'Latin filler wording']])
    await userEvent.selectOptions(dropdown(), 'en')
    expect(shown()).toEqual([['en', 'English filler wording']])
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('is operated from the keyboard alone', async () => {
    view(bilingual)
    await userEvent.tab()                                   // the link back to The Oratory
    await userEvent.tab()                                   // then the Language dropdown, with no pointer involved
    expect(dropdown()).toHaveFocus()
    expect(dropdown().tagName).toBe('SELECT')               // a native control: arrow keys, type-ahead and screen readers all work
  })

  it('announces the language in a polite live region for screen readers', async () => {
    view(bilingual)
    const live = document.querySelector('.prayer-section [aria-live="polite"]')!
    expect(live).toHaveTextContent('Showing English.')
    await userEvent.selectOptions(dropdown(), 'la')
    expect(live).toHaveTextContent('Showing Latin.')
  })

  it('marks the language of each text so a screen reader pronounces it correctly', async () => {
    view(bilingual)
    await userEvent.selectOptions(dropdown(), 'la')
    expect(document.querySelector('.prayer-body')).toHaveAttribute('lang', 'la')
  })
})

describe('remembering the language', () => {
  it('remembers the choice across visits', async () => {
    const first = view(bilingual)
    await userEvent.selectOptions(dropdown(), 'la')
    expect(window.localStorage.getItem(LANGUAGE_KEY)).toBe('la')
    first.unmount()
    view(bilingual)
    expect(dropdown()).toHaveValue('la')
    expect(shown()).toEqual([['la', 'Latin filler wording']])
  })

  it('keeps the language when moving from one devotion to another', async () => {
    const first = view(bilingual)
    await userEvent.selectOptions(dropdown(), 'la')
    first.unmount()
    view({ ...bilingual, id: 'e', slug: 'another', title: 'Another Devotion', texts: [text('main', 'en', 'Another English'), text('main', 'la', 'Another Latin')] })
    expect(dropdown()).toHaveValue('la')
    expect(shown()).toEqual([['la', 'Another Latin']])
  })

  it('falls back to English only when the stored value is not a supported language', () => {
    window.localStorage.setItem(LANGUAGE_KEY, 'fr')
    view(bilingual)
    expect(dropdown()).toHaveValue('en')
    expect(resolveLanguage('fr')).toBe('en')
    expect(resolveLanguage('la')).toBe('la')
    expect(resolveLanguage(null)).toBe('en')
  })
})

describe('a language with no text', () => {
  it('says so clearly and does not show English in its place', async () => {
    view(englishOnly)
    await userEvent.selectOptions(dropdown(), 'la')
    expect(screen.getByText('Latin text is not yet available for this devotion.')).toBeInTheDocument()
    expect(document.querySelector('.prayer-body')).toBeNull()                       // not even a trace of the English wording
    expect(screen.queryByText('English filler wording')).not.toBeInTheDocument()
  })

  it('offers a way to switch to a language that exists, and nothing happens until it is used', async () => {
    view(englishOnly)
    await userEvent.selectOptions(dropdown(), 'la')
    const note = screen.getByRole('note')
    expect(dropdown()).toHaveValue('la')
    await userEvent.click(within(note).getByRole('button', { name: 'Read in English' }))
    expect(dropdown()).toHaveValue('en')
    expect(shown()).toEqual([['en', 'English filler wording']])
  })

  it('never translates anything on its own: only stored texts are ever shown', async () => {
    view(englishOnly)
    await userEvent.selectOptions(dropdown(), 'la')
    expect(document.body.textContent).not.toMatch(/filler wording/)                  // neither the English nor an invented Latin
    expect(versionsFor(englishOnly.texts, 'la')).toEqual({ shown: [], missing: 'la' })
  })

  it('treats a single prayer inside a longer devotion the same way', async () => {
    const mixed: Devotion = { ...base, texts: [text('one', 'en', 'One in English'), text('one', 'la', 'One in Latin'), text('two', 'en', 'Two in English only')], steps: [{ kind: 'prayer', text_slot: 'one', title: 'First prayer', instruction: null, repeat: null, section: null }, { kind: 'prayer', text_slot: 'two', title: 'Second prayer', instruction: null, repeat: null, section: null }] }
    view(mixed)
    await userEvent.selectOptions(dropdown(), 'la')
    expect(shown()).toEqual([['la', 'One in Latin']])
    expect(screen.getByText('Latin text is not yet available for this prayer.')).toBeInTheDocument()
    expect(screen.queryByText('Two in English only')).not.toBeInTheDocument()
  })

  it('shows the plain unpublished notice, not a language message, when there is no text at all', () => {
    view(base)
    expect(screen.getByRole('note')).toHaveTextContent('The prayer text has not been published yet.')
    expect(screen.queryByRole('combobox', { name: 'Language' })).not.toBeInTheDocument()
  })
})

describe('extending to more languages later', () => {
  it('is driven by one registry, so a language is one more entry', () => {
    expect(SUPPORTED_LANGUAGES.map(language => language.code)).toEqual(['en', 'la'])
    expect(languageLabel('en')).toBe('English')
    expect(languageLabel('la')).toBe('Latin')
    expect(availableLanguages([{ language: 'en' }, { language: 'la' }, { language: 'en' }])).toEqual(['la', 'en'])
  })

  it('shows no language but English and Latin in this phase', () => {
    view(bilingual)
    expect(within(dropdown()).getAllByRole('option')).toHaveLength(2)
  })
})

// ---- Guided devotions: position survives a change of language -------------------------------------------
const mysteries = ['Joyful', 'Sorrowful']
const sequence: Devotion = {
  ...base, title: 'Sequence Devotion', choice_label: 'Mysteries',
  steps: [
    { kind: 'prayer', title: 'Opening prayer', instruction: null, text_slot: 'opening', repeat: null, section: 'Opening', group: null },
    ...mysteries.flatMap(name => [1, 2, 3].map((number): DevotionStep => ({ kind: 'prayer', title: `${name} ${number}`, instruction: null, text_slot: 'decade', repeat: 10, section: `${name}: decade ${number}`, group: name }))),
    { kind: 'prayer', title: 'Closing prayer', instruction: null, text_slot: 'closing', repeat: null, section: 'Closing', group: null },
  ],
  texts: ['opening', 'decade', 'closing'].flatMap(slot => [text(slot, 'en', `${slot} in English`), text(slot, 'la', `${slot} in Latin`)]),
}
const openPrayerMode = async (devotion: Devotion) => { view(devotion); await userEvent.click(screen.getByRole('button', { name: 'Enter prayer mode' })); return screen.getByRole('dialog') }
const dialogLanguage = (dialog: HTMLElement) => within(dialog).getByRole('combobox', { name: 'Language' })
const counter = (dialog: HTMLElement) => within(dialog).getByText(/^Step \d+ of \d+$/).textContent
const next = (dialog: HTMLElement) => userEvent.click(within(dialog).getByRole('button', { name: /Next/ }))

describe('guided prayer: language and position', () => {
  it('keeps the same step when the language changes, and again when it changes back', async () => {
    const dialog = await openPrayerMode(sequence)
    await next(dialog)
    await next(dialog)
    expect(counter(dialog)).toBe('Step 3 of 5')
    expect(within(dialog).getByText('Joyful 2')).toBeInTheDocument()
    await userEvent.selectOptions(dialogLanguage(dialog), 'la')
    expect(counter(dialog)).toBe('Step 3 of 5')
    expect(within(dialog).getByText('Joyful 2')).toBeInTheDocument()
    expect(within(dialog).getByText('decade in Latin')).toBeInTheDocument()
    await userEvent.selectOptions(dialogLanguage(dialog), 'en')
    expect(counter(dialog)).toBe('Step 3 of 5')
    expect(within(dialog).getByText('decade in English')).toBeInTheDocument()
  })

  it('says a prayer step has no text in the chosen language, offers the others, and keeps the place', async () => {
    const lopsided: Devotion = { ...sequence, texts: sequence.texts.filter(item => !(item.slot === 'decade' && item.language === 'la')) }
    const dialog = await openPrayerMode(lopsided)
    await next(dialog)
    await userEvent.selectOptions(dialogLanguage(dialog), 'la')
    expect(within(dialog).getByText('Latin text is not yet available for this prayer.')).toBeInTheDocument()
    expect(within(dialog).queryByText('decade in English')).not.toBeInTheDocument()
    expect(counter(dialog)).toBe('Step 2 of 5')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Read in English' }))
    expect(within(dialog).getByText('decade in English')).toBeInTheDocument()
    expect(counter(dialog)).toBe('Step 2 of 5')
  })

  it('has the arrow keys ready as soon as it opens, and leaves them alone while the language list has focus', async () => {
    const dialog = await openPrayerMode(sequence)
    await userEvent.keyboard('{ArrowRight}')
    expect(counter(dialog)).toBe('Step 2 of 5')
    dialogLanguage(dialog).focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(counter(dialog)).toBe('Step 2 of 5')               // the dropdown keeps its own arrow keys
  })
})

describe('steps the reader chooses between (the mysteries)', () => {
  it('offers the choice by its own label and walks only the chosen set, with the common steps around it', async () => {
    const dialog = await openPrayerMode(sequence)
    const choice = within(dialog).getByRole('combobox', { name: 'Mysteries' })
    expect([...choice.querySelectorAll('option')].map(option => option.textContent)).toEqual(mysteries)
    const walked: string[] = []
    for (let i = 0; i < 5; i++) { walked.push(dialog.querySelector('.prayer-step-title')!.textContent!); if (i < 4) await next(dialog) }
    expect(walked).toEqual(['Opening prayer', 'Joyful 1', 'Joyful 2', 'Joyful 3', 'Closing prayer'])
    expect(counter(dialog)).toBe('Step 5 of 5')
  })

  it('shows the set that was chosen, not the others', async () => {
    const dialog = await openPrayerMode(sequence)
    await userEvent.selectOptions(within(dialog).getByRole('combobox', { name: 'Mysteries' }), 'Sorrowful')
    await next(dialog)
    const step = dialog.querySelector('.prayer-step')! as HTMLElement
    expect(within(step).getByText('Sorrowful 1')).toBeInTheDocument()
    expect(within(step).queryByText(/Joyful/)).not.toBeInTheDocument()
  })

  it('keeps the chosen set and decade when the language changes', async () => {
    const dialog = await openPrayerMode(sequence)
    await userEvent.selectOptions(within(dialog).getByRole('combobox', { name: 'Mysteries' }), 'Sorrowful')
    await next(dialog)
    await next(dialog)
    expect(within(dialog).getByText('Sorrowful 2')).toBeInTheDocument()
    await userEvent.selectOptions(dialogLanguage(dialog), 'la')
    expect(within(dialog).getByRole('combobox', { name: 'Mysteries' })).toHaveValue('Sorrowful')
    expect(within(dialog).getByText('Sorrowful 2')).toBeInTheDocument()
    expect(within(dialog).getByText('decade in Latin')).toBeInTheDocument()
    expect(counter(dialog)).toBe('Step 3 of 5')
  })

  it('keeps the opening prayers in place when a set is chosen from within them, and starts the set when chosen from inside another', async () => {
    const dialog = await openPrayerMode(sequence)
    await userEvent.selectOptions(within(dialog).getByRole('combobox', { name: 'Mysteries' }), 'Sorrowful')
    expect(counter(dialog)).toBe('Step 1 of 5')                                       // still on the opening prayer
    await next(dialog)
    await next(dialog)
    await userEvent.selectOptions(within(dialog).getByRole('combobox', { name: 'Mysteries' }), 'Joyful')
    expect(within(dialog).getByText('Joyful 1')).toBeInTheDocument()                  // from inside a set, the new set begins
  })

  it('never asks the reader to track completion', async () => {
    const dialog = await openPrayerMode(sequence)
    expect(dialog.querySelector('input[type="checkbox"]')).toBeNull()
    expect(dialog.textContent).not.toMatch(/complete|completed|streak|progress|done/i)
  })

  it('knows its sets and their steps from the data alone', () => {
    expect(stepGroups(sequence.steps)).toEqual(mysteries)
    expect(visibleSteps(sequence.steps, 'Joyful')).toHaveLength(5)
    expect(visibleSteps(sequence.steps, null)).toHaveLength(2)
  })
})

describe('reusing a prayer kept in another devotion', () => {
  it('finds each reused prayer by its own devotion and slot, so same-named slots never collide', async () => {
    const reusing: Devotion = {
      ...base, slug: 'outer', title: 'Outer Devotion',
      steps: [
        { kind: 'prayer', title: 'Reused first', instruction: null, text_slot: 'main', devotion_slug: 'inner-a', repeat: null, section: null },
        { kind: 'prayer', title: 'Reused second', instruction: null, text_slot: 'main', devotion_slug: 'inner-b', repeat: 3, section: null },
        { kind: 'prayer', title: 'Own prayer', instruction: null, text_slot: 'main', repeat: null, section: null },
      ],
      texts: [text('main', 'en', 'from A', { id: 'a', devotion_slug: 'inner-a' }), text('main', 'en', 'from B', { id: 'b', devotion_slug: 'inner-b' }), text('main', 'en', 'from outer itself', { id: 'o', devotion_slug: 'outer' })],
    }
    const dialog = await openPrayerMode(reusing)
    expect(within(dialog).getByText('from A')).toBeInTheDocument()
    await next(dialog)
    expect(within(dialog).getByText('from B')).toBeInTheDocument()
    expect(within(dialog).getByText('Pray this 3 times')).toBeInTheDocument()
    await next(dialog)
    expect(within(dialog).getByText('from outer itself')).toBeInTheDocument()
    expect(groupTexts(reusing, reusing.texts).map(group => group.key)).toEqual(['inner-a/main', 'inner-b/main', 'outer/main'])
  })

  it('shows the unpublished notice for a reused prayer the server has not released', async () => {
    const reusing: Devotion = { ...base, slug: 'outer', steps: [{ kind: 'prayer', title: 'Reused', instruction: null, text_slot: 'main', devotion_slug: 'inner', repeat: null, section: null }], texts: [text('other', 'en', 'something else', { devotion_slug: 'outer' })] }
    const dialog = await openPrayerMode(reusing)
    expect(within(dialog).getByRole('note')).toHaveTextContent('The prayer text has not been published yet.')
  })
})

describe('optional customs', () => {
  it('are labelled as optional in the outline and in prayer mode', async () => {
    const withCustom: Devotion = { ...base, texts: [text('core', 'en', 'core words'), text('custom', 'en', 'custom words')], steps: [{ kind: 'prayer', title: 'Core prayer', instruction: null, text_slot: 'core', repeat: null, section: null }, { kind: 'prayer', title: 'A traditional custom', instruction: null, text_slot: 'custom', repeat: null, section: null, optional: true }] }
    view(withCustom)
    const outline = screen.getByRole('region', { name: 'How to Pray' })
    expect(within(outline).getAllByText('Optional custom')).toHaveLength(1)
    await userEvent.click(screen.getByRole('button', { name: 'Enter prayer mode' }))
    const dialog = screen.getByRole('dialog')
    await next(dialog)
    expect(within(dialog).getByText('Optional custom')).toBeInTheDocument()
  })

  it('collapses the steps a reader chooses between in the outline, and numbers the common steps straight through', () => {
    view(sequence)
    const outline = screen.getByRole('region', { name: 'How to Pray' })
    const sets = outline.querySelectorAll('details.sequence-choice')
    expect([...sets].map(set => set.querySelector('summary')!.textContent)).toEqual(mysteries)
    expect([...outline.querySelectorAll('details')].every(set => !set.hasAttribute('open'))).toBe(true)
    const common = [...outline.querySelectorAll('.sequence > .sequence-group ol')].map(list => list.getAttribute('start'))
    expect(common).toEqual(['1', '2'])
  })
})

describe('a prayer with Latin only (Regina Caeli, whose English is unavailable)', () => {
  const latinOnly: Devotion = { ...base, title: 'Latin-only Devotion', texts: [text('main', 'la', 'Latin filler wording')] }

  it('shows English, the default, as unavailable rather than substituting the Latin, and offers the Latin', async () => {
    view(latinOnly)
    expect(dropdown()).toHaveValue('en')
    expect(screen.getByText('English text is not yet available for this devotion.')).toBeInTheDocument()
    expect(document.querySelector('.prayer-body')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Read in Latin' }))
    expect(dropdown()).toHaveValue('la')
    expect(shown()).toEqual([['la', 'Latin filler wording']])
  })

  it('shows supplied wording character for character: CRLF line endings, a soft hyphen and a trailing space included', () => {
    const body = 'Ave Maria, gratia plena\r\n\r\nbenedicta tu in mulieri\u00adbus, \r\n\r\nAmen '
    window.localStorage.setItem(LANGUAGE_KEY, 'la')
    view({ ...base, texts: [text('main', 'la', body)] })
    expect(document.querySelector('.prayer-body')!.textContent).toBe(body)
  })
})
