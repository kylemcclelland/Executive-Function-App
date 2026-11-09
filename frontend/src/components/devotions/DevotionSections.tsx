import { ArrowLeft, Bookmark, Clock } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '../ui'
import { availableLanguages, durationLabel, groupBySlot, hasHowToPray, paragraphs, resolveLanguage, safeUrl, versionsFor, languageLabel } from '../../lib/devotions'
import type { Devotion, DevotionStep } from '../../types/devotions'
import { LanguageToggle, PrayerVersion, TextSizeControl, UnpublishedNotice, type ReadingPreferences } from './PrayerText'

function Paragraphs({ text, className }: { text: string; className?: string }) {
  return <>{paragraphs(text).map((part, index) => <p key={index} className={className}>{part}</p>)}</>
}

export function DevotionHeader({ devotion, backTo, onToggleBookmark, bookmarkPending }: { devotion: Devotion; backTo: string; onToggleBookmark?: (next: boolean) => void; bookmarkPending?: boolean }) {
  const duration = durationLabel(devotion.estimated_minutes)
  return <header className="devotion-header">
    <Link to={backTo} className="devotion-back"><ArrowLeft size={16} aria-hidden="true" /> The Oratory</Link>
    <div className="devotion-title-row">
      <div className="devotion-titles">
        <h1 id="devotion-title">{devotion.title}</h1>
        {devotion.subtitle && <p className="devotion-subtitle">{devotion.subtitle}</p>}
        {(devotion.category || duration) && <p className="devotion-meta">{devotion.category && <span className="tag">{devotion.category}</span>}{duration && <span className="devotion-duration"><Clock size={14} aria-hidden="true" />{duration}</span>}</p>}
      </div>
      {onToggleBookmark && <Button variant="outline" aria-pressed={devotion.bookmarked} disabled={bookmarkPending} onClick={() => onToggleBookmark(!devotion.bookmarked)}><Bookmark size={16} aria-hidden="true" fill={devotion.bookmarked ? 'currentColor' : 'none'} />{devotion.bookmarked ? 'Saved' : 'Save'}</Button>}
    </div>
  </header>
}

/** Commentary about the devotion. It is never prayer wording and is kept visually apart from it. */
export function Overview({ devotion }: { devotion: Devotion }) {
  const references = devotion.references
  return <section className="devotion-section" aria-labelledby="overview-heading">
    <h2 id="overview-heading">Overview</h2>
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
  if (step.kind === 'instruction') return step.instruction ?? ''
  return step.title ?? (step.kind === 'response' ? 'Response' : 'Prayer')
}

/** The steps as an outline: what comes in which order, how often, and under which heading. The wording itself is not here. */
function SequenceOutline({ steps }: { steps: DevotionStep[] }) {
  const groups: { section: string | null; steps: DevotionStep[]; start: number }[] = []
  steps.forEach((step, index) => {
    const last = groups[groups.length - 1]
    if (last && last.section === step.section) last.steps.push(step)
    else groups.push({ section: step.section, steps: [step], start: index + 1 })
  })
  return <div className="sequence"><h3>The sequence</h3>{groups.map(group => <div className="sequence-group" key={group.start}>
    {group.section && <h4>{group.section}</h4>}
    <ol start={group.start} className="sequence-steps">{group.steps.map((step, index) => <li key={index} className={`sequence-step is-${step.kind}`}>
      <span className="step-kind">{step.kind === 'instruction' ? 'Instruction' : step.kind === 'response' ? 'Response' : 'Prayer'}</span>
      <span className="step-summary">{stepSummary(step)}</span>
      {step.kind !== 'instruction' && step.instruction && <span className="step-note">{step.instruction}</span>}
      {step.repeat && step.repeat > 1 ? <span className="step-repeat">Repeat {step.repeat} times</span> : null}
    </li>)}</ol>
  </div>)}</div>
}

/** Instruction for praying. Hidden entirely when the devotion has none. */
export function HowToPray({ devotion }: { devotion: Devotion }) {
  if (!hasHowToPray(devotion)) return null
  return <section className="devotion-section" aria-labelledby="howto-heading">
    <h2 id="howto-heading">How to Pray</h2>
    <p className="instruction-lead">Guidance only. The words of the prayer are in the Prayer Text below.</p>
    {devotion.instructions.length > 0 && <ol className="instruction-list">{devotion.instructions.map((item, index) => <li key={index}>{item}</li>)}</ol>}
    {devotion.steps.length > 0 && <SequenceOutline steps={devotion.steps} />}
  </section>
}

export function PrayerTextSection({ devotion, prefs, onEnterPrayerMode }: { devotion: Devotion; prefs: ReadingPreferences; onEnterPrayerMode: () => void }) {
  const languages = availableLanguages(devotion.texts)
  const choice = resolveLanguage(prefs.language, languages)
  const slots = groupBySlot(devotion.texts)
  return <section className="devotion-section prayer-section" aria-labelledby="prayer-text-heading" data-size={prefs.size}>
    <div className="devotion-section-head">
      <h2 id="prayer-text-heading">Prayer Text</h2>
      {slots.length > 0 && <div className="reading-controls"><LanguageToggle languages={languages} value={choice} onChange={prefs.setLanguage} /><TextSizeControl prefs={prefs} /><Button variant="outline" onClick={onEnterPrayerMode}>Enter prayer mode</Button></div>}
    </div>
    {slots.length === 0 ? <UnpublishedNotice /> : slots.map(({ slot, versions }) => {
      const { shown, missing } = versionsFor(versions, choice)
      return <div className="prayer-slot" key={slot}>
        {missing && <p className="prayer-note" role="note">No {languageLabel(missing)} version of this text has been published yet.</p>}
        <div className={`prayer-versions ${shown.length > 1 ? 'is-parallel' : ''}`}>{shown.map(text => <PrayerVersion key={text.id} text={text} showLanguage={languages.length > 1} />)}</div>
      </div>
    })}
  </section>
}
