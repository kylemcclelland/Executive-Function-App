import { Fragment, useId, type ReactNode } from 'react'
import { Feather, Minus, Plus } from 'lucide-react'
import { Button } from '../ui'
import { SUPPORTED_LANGUAGES, isResponseLine, languageLabel, licenseLabels, safeUrl, type useReadingPreferences } from '../../lib/devotions'
import type { LanguageChoice, PrayerText, TextSource } from '../../types/devotions'

export type ReadingPreferences = ReturnType<typeof useReadingPreferences>

/**
 * Prayer wording, shown exactly as approved: every character, space and line break is kept (the text
 * node content equals the stored body). Nothing is trimmed, re-wrapped, translated or corrected here.
 */
export function PrayerBody({ text }: { text: PrayerText }) {
  const lines = text.body.split('\n')
  return <div className="prayer-body" lang={text.language}>{lines.map((line, index) => <Fragment key={index}><span className={isResponseLine(line) ? 'prayer-line is-response' : 'prayer-line'}>{line}</span>{index < lines.length - 1 ? '\n' : ''}</Fragment>)}</div>
}

export function SourceNote({ source }: { source: TextSource }) {
  const rows: { label: string; value: ReactNode }[] = []
  if (source.title) rows.push({ label: 'Source', value: source.title })
  if (source.authority) rows.push({ label: 'Issued by', value: source.authority })
  if (source.edition) rows.push({ label: 'Edition', value: source.edition })
  if (source.date) rows.push({ label: 'Published', value: source.date })
  if (source.is_translation && source.translator) rows.push({ label: 'Translation', value: source.translator })
  if (source.attribution) rows.push({ label: 'Attribution', value: source.attribution })
  const rights = licenseLabels[source.license_status]
  if (rights) rows.push({ label: 'Rights', value: rights })
  const link = safeUrl(source.url)
  if (link) rows.push({ label: 'Link', value: <a href={link} target="_blank" rel="noopener noreferrer">View the source</a> })
  if (!rows.length) return null
  return <dl className="prayer-source">{rows.map(({ label, value }) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
}

/** One language version of a prayer: its title, exact wording and where it came from. */
export function PrayerVersion({ text, showLanguage, compact = false, badge }: { text: PrayerText; showLanguage: boolean; compact?: boolean; badge?: ReactNode }) {
  const withheld = !text.body.trim()
  return <div className="prayer-version">
    {(showLanguage || badge) && <p className="prayer-language">{showLanguage && languageLabel(text.language)}{badge}</p>}
    {text.title && <h3 className="prayer-title" lang={text.language}>{text.title}</h3>}
    {withheld ? <p className="prayer-withheld">No wording is held for this text. See its source.</p> : <PrayerBody text={text} />}
    {compact ? <details className="prayer-source-details"><summary>Source</summary><SourceNote source={text.source} /></details> : <SourceNote source={text.source} />}
  </div>
}

/** Shown wherever approved wording does not exist (yet). It never hints at what the wording is. */
export function UnpublishedNotice({ compact = false }: { compact?: boolean }) {
  return <div className={`prayer-unpublished ${compact ? 'is-compact' : ''}`} role="note">
    <Feather size={compact ? 16 : 22} strokeWidth={1.4} aria-hidden="true" />
    <div><p><strong>The prayer text has not been published yet.</strong></p>{!compact && <p className="muted">Prayer wording appears here only after its source has been verified and the exact text has been approved.</p>}</div>
  </div>
}

/**
 * The compact language dropdown. It lists every supported language, whether or not this prayer has a
 * text in it: choosing one without a text shows a clear message instead (see LanguageUnavailable),
 * and never substitutes another language.
 */
export function LanguageSelect({ value, onChange }: { value: LanguageChoice; onChange: (language: LanguageChoice) => void }) {
  const id = useId()
  return <div className="language-select">
    <label htmlFor={id}>Language</label>
    <select id={id} value={value} onChange={event => onChange(event.target.value)}>{SUPPORTED_LANGUAGES.map(language => <option key={language.code} value={language.code}>{language.label}</option>)}</select>
  </div>
}

/** "Latin text is not yet available for this devotion", with a way to read in a language that exists. */
export function LanguageUnavailable({ language, available, onChoose, subject }: { language: LanguageChoice; available: string[]; onChoose: (language: LanguageChoice) => void; subject: string }) {
  return <div className="language-unavailable" role="note">
    <p><strong>{languageLabel(language)} text is not yet available for {subject}.</strong></p>
    {available.length > 0 && <p className="language-unavailable-actions"><span>Available in:</span>{available.map(code => <Button key={code} variant="outline" size="sm" onClick={() => onChoose(code)}>Read in {languageLabel(code)}</Button>)}</p>}
  </div>
}

export function TextSizeControl({ prefs }: { prefs: ReadingPreferences }) {
  return <div className="reading-toggle" role="group" aria-label="Prayer text size">
    <Button size="sm" variant="ghost" aria-label="Smaller text" disabled={!prefs.canShrink} onClick={prefs.smaller}><Minus size={15} /></Button>
    <span className="reading-size" aria-hidden="true">Aa</span>
    <Button size="sm" variant="ghost" aria-label="Larger text" disabled={!prefs.canGrow} onClick={prefs.larger}><Plus size={15} /></Button>
  </div>
}
