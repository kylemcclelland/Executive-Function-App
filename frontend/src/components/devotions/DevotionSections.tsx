import type { ReactNode } from 'react'
import { ArrowLeft, Bookmark, Clock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '../ui'
import { availableLanguages, durationLabel, groupTexts, hasHowToPray, languageLabel, paragraphs, safeUrl, textGroupTitle, versionsFor } from '../../lib/devotions'
import type { Devotion, DevotionStep, PrayerText } from '../../types/devotions'
import { LanguageUnavailable, PrayerVersion, TextSizeControl, NoTextNotice, type ReadingPreferences } from './PrayerText'

function Paragraphs({ text, className }: { text: string; className?: string }) {
  return <>{paragraphs(text).map((part, index) => <p key={index} className={className}>{part}</p>)}</>
}

export function DevotionHeader({ devotion, backTo, backLabel = 'The Oratory', controls, onToggleBookmark, bookmarkPending }: { devotion: Devotion; backTo: string; backLabel?: string; controls?: ReactNode; onToggleBookmark?: (next: boolean) => void; bookmarkPending?: boolean }) {
  const duration = durationLabel(devotion.estimated_minutes)
  return <header className="devotion-header">
    <Link to={backTo} className="devotion-back"><ArrowLeft size={16} aria-hidden="true" /> {backLabel}</Link>
    <div className="devotion-title-row">
      <div className="devotion-titles">
        <h1 id="devotion-title">{devotion.title}</h1>
        {devotion.subtitle && <p className="devotion-subtitle">{devotion.subtitle}</p>}
        {(devotion.category || duration) && <p className="devotion-meta">{devotion.category && <span className="tag">{devotion.category}</span>}{duration && <span className="devotion-duration"><Clock size={14} aria-hidden="true" />{duration}</span>}</p>}
      </div>
      {onToggleBookmark && <Button variant="outline" aria-pressed={devotion.bookmarked} disabled={bookmarkPending} onClick={() => onToggleBookmark(!devotion.bookmarked)}><Bookmark size={16} aria-hidden="true" fill={devotion.bookmarked ? 'currentColor' : 'none'} />{devotion.bookmarked ? 'Saved' : 'Save'}</Button>}
    </div>
    {controls && <div className="devotion-controls">{controls}</div>}
  </header>
}

/** Commentary about the devotion. It is never prayer wording and is kept visually apart from it. */
export function Overview({ devotion, proseNote }: { devotion: Devotion; proseNote?: ReactNode }) {
  const references = devotion.references
  return <section className="devotion-section" aria-labelledby="overview-heading">
    <h2 id="overview-heading">Overview</h2>
    {proseNote}
    <div className="devotion-prose"><Paragraphs text={devotion.overview} /></div>
    {devotion.background && <div className="devotion-commentary"><h3>Historical background</h3><div className="devotion-prose"><Paragraphs text={devotion.background} /></div></div>}
    {devotion.significance && <div className="devotion-commentary"><h3>Spiritual significance</h3><div className="devotion-prose"><Paragraphs text={devotion.significance} /></div></div>}
    {references.length > 0 && <div className="devotion-commentary"><h3>Sources</h3><ul className="devotion-references">{references.map((reference, index) => {
      const link = safeUrl(reference.url)
      return <li key={index}>{link ? <a href={link} target="_blank" rel="noopener noreferrer">{reference.label}</a> : reference.label}</li>
    })}</ul></div>}
  </section>
}

function stepSummary(step: DevotionStep): string {
  if (step.kind === 'instruction') return step.title ?? step.instruction ?? ''
  return step.title ?? (step.kind === 'response' ? 'Response' : 'Prayer')
}

/** Steps in order, under their section headings. Numbering starts at ``from``. */
function OutlineList({ steps, from }: { steps: DevotionStep[]; from: number }) {
  const sections: { section: string | null; steps: DevotionStep[]; start: number }[] = []
  steps.forEach((step, index) => {
    const last = sections[sections.length - 1]
    if (last && last.section === step.section) last.steps.push(step)
    else sections.push({ section: step.section, steps: [step], start: from + index })
  })
  return <>{sections.map(group => <div className="sequence-group" key={group.start}>
    {group.section && <h4>{group.section}</h4>}
    <ol start={group.start} className="sequence-steps">{group.steps.map((step, index) => <li key={index} className={`sequence-step is-${step.kind}`}>
      <span className="step-kind">{step.kind === 'instruction' ? 'Instruction' : step.kind === 'response' ? 'Response' : 'Prayer'}</span>
      {step.optional && <span className="step-optional">Optional custom</span>}
      <span className="step-summary">{stepSummary(step)}</span>
      {step.kind !== 'instruction' && step.instruction && <span className="step-note">{step.instruction}</span>}
      {step.kind === 'instruction' && step.title && step.instruction && <span className="step-note">{step.instruction}</span>}
      {step.repeat && step.repeat > 1 ? <span className="step-repeat">Repeat {step.repeat} times</span> : null}
    </li>)}</ol>
  </div>)}</>
}

/**
 * The steps as an outline: what comes in which order, how often, under which heading, and which are
 * optional customs. Steps the reader chooses between (a set of mysteries) each sit in their own
 * collapsed block. The wording itself is not here.
 */
export function SequenceOutline({ steps, choiceLabel }: { steps: DevotionStep[]; choiceLabel?: string | null }) {
  type Block = { group: string | null; steps: DevotionStep[]; from: number }
  const blocks: Block[] = []
  let common = 0
  for (const step of steps) {
    const group = step.group ?? null
    const found = group ? blocks.find(block => block.group === group) : blocks[blocks.length - 1]?.group === null ? blocks[blocks.length - 1] : undefined
    if (found) found.steps.push(step)
    else blocks.push({ group, steps: [step], from: group ? 1 : common + 1 })
    if (!group) common += 1
  }
  return <div className="sequence"><h3>The sequence</h3>
    {choiceLabel && blocks.some(block => block.group) && <p className="sequence-choice-note">Choose which {choiceLabel.toLowerCase()} to pray; the steps below them are common to all.</p>}
    {blocks.map((block, index) => block.group
      ? <details className="sequence-choice" key={index}><summary>{block.group}</summary><OutlineList steps={block.steps} from={1} /></details>
      : <OutlineList key={index} steps={block.steps} from={block.from} />)}
  </div>
}

/** Instruction for praying. Hidden entirely when the devotion has none. */
export function HowToPray({ devotion }: { devotion: Devotion }) {
  if (!hasHowToPray(devotion)) return null
  return <section className="devotion-section" aria-labelledby="howto-heading">
    <h2 id="howto-heading">How to Pray</h2>
    <p className="instruction-lead">Guidance only. The words of the prayer are in the Prayer Text below.</p>
    {devotion.instructions.length > 0 && <ol className="instruction-list">{devotion.instructions.map((item, index) => <li key={index}>{item}</li>)}</ol>}
    {devotion.steps.length > 0 && <SequenceOutline steps={devotion.steps} choiceLabel={devotion.choice_label} />}
  </section>
}

/**
 * The wording, in the reader's language. If a prayer has no text in that language the page says so
 * and offers the languages that exist; it never shows another language in its place.
 */
export function PrayerTextSection({ devotion, prefs, onEnterPrayerMode, textBadge }: { devotion: Devotion; prefs: ReadingPreferences; onEnterPrayerMode: () => void; textBadge?: (text: PrayerText) => ReactNode }) {
  const available = availableLanguages(devotion.texts)
  const language = prefs.language
  const groups = groupTexts(devotion, devotion.texts)
  const readable = groups.length > 0 && available.includes(language)
  return <section className="devotion-section prayer-section" aria-labelledby="prayer-text-heading" data-size={prefs.size}>
    <div className="devotion-section-head">
      <h2 id="prayer-text-heading">Prayer Text</h2>
      {groups.length > 0 && <div className="reading-controls"><TextSizeControl prefs={prefs} /><Button variant="outline" onClick={onEnterPrayerMode}>Enter prayer mode</Button></div>}
    </div>
    {groups.length === 0 ? <NoTextNotice />
      : !readable ? <LanguageUnavailable language={language} available={available} onChoose={prefs.setLanguage} subject="this devotion" />
      : groups.map(group => {
        const { shown, missing } = versionsFor(group.versions, language)
        const title = textGroupTitle(devotion, group)
        return <div className="prayer-slot" key={group.key}>
          {groups.length > 1 && title && <h3 className="prayer-slot-title">{title}</h3>}
          {missing && <LanguageUnavailable language={language} available={group.versions.map(version => version.language)} onChoose={prefs.setLanguage} subject="this prayer" />}
          <div className="prayer-versions">{shown.map(text => <PrayerVersion key={text.id} text={text} showLanguage={false} badge={textBadge?.(text)} />)}</div>
        </div>
      })}
    <p className="sr-only" aria-live="polite">{readable ? `Showing ${languageLabel(language)}.` : ''}</p>
  </section>
}
