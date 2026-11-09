import { Fragment, type ReactNode } from 'react'
import { Feather, Minus, Plus } from 'lucide-react'
import { Button } from '../ui'
import { isResponseLine, languageLabel, licenseLabels, safeUrl, type useReadingPreferences } from '../../lib/devotions'
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
  if (source.edition) rows.push({ label: 'Edition', value: source.edition })
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
export function PrayerVersion({ text, showLanguage, compact = false }: { text: PrayerText; showLanguage: boolean; compact?: boolean }) {
  return <div className="prayer-version">
    {showLanguage && <p className="prayer-language">{languageLabel(text.language)}</p>}
    {text.title && <h3 className="prayer-title" lang={text.language}>{text.title}</h3>}
    <PrayerBody text={text} />
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

export function LanguageToggle({ languages, value, onChange }: { languages: string[]; value: LanguageChoice; onChange: (choice: LanguageChoice) => void }) {
  if (languages.length < 2) return null
  const options = [...languages.map(code => ({ value: code, label: languageLabel(code) })), { value: 'both', label: 'Both' }]
  return <div className="reading-toggle" role="group" aria-label="Language">{options.map(option => <Button key={option.value} size="sm" variant={value === option.value ? 'default' : 'ghost'} aria-pressed={value === option.value} onClick={() => onChange(option.value)}>{option.label}</Button>)}</div>
}

export function TextSizeControl({ prefs }: { prefs: ReadingPreferences }) {
  return <div className="reading-toggle" role="group" aria-label="Prayer text size">
    <Button size="sm" variant="ghost" aria-label="Smaller text" disabled={!prefs.canShrink} onClick={prefs.smaller}><Minus size={15} /></Button>
    <span className="reading-size" aria-hidden="true">Aa</span>
    <Button size="sm" variant="ghost" aria-label="Larger text" disabled={!prefs.canGrow} onClick={prefs.larger}><Plus size={15} /></Button>
  </div>
}
