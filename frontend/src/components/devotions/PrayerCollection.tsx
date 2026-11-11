import { useState, type ReactNode } from 'react'
import { Button } from '../ui'
import { languageLabel, versionsFor, type TextGroup } from '../../lib/devotions'
import type { PrayerText } from '../../types/devotions'
import { LanguageUnavailable, PrayerVersion, TextSizeControl, type ReadingPreferences } from './PrayerText'

type Layout = 'one' | 'both'

const titleOf = (group: TextGroup) => (group.versions.find(version => version.language === 'en') ?? group.versions[0]).title ?? group.slot
const anchorOf = (group: TextGroup) => `prayer-${group.slot}`

/**
 * A devotion's ordered collection of prayers (for the Rosary: from the Sign of the Cross to the closing prayers). Each prayer is shown in the
 * reader's language, or, on request, Latin and English side by side (stacked on a narrow screen). A language a prayer does not have is
 * stated, never replaced by another. It shows nothing when the devotion holds no collection.
 */
export function PrayerCollection({ groups, prefs, textBadge, heading = 'The Prayers of the Rosary' }: { groups: TextGroup[]; prefs: ReadingPreferences; textBadge?: (text: PrayerText) => ReactNode; heading?: string }) {
  const [layout, setLayout] = useState<Layout>('one')
  if (groups.length === 0) return null
  const language = prefs.language
  return <section className="devotion-section prayer-section prayer-collection" aria-labelledby="collection-heading" data-size={prefs.size}>
    <div className="devotion-section-head">
      <h2 id="collection-heading">{heading}</h2>
      <div className="reading-controls">
        <div className="reading-toggle" role="group" aria-label="Layout">
          <Button size="sm" variant={layout === 'one' ? 'secondary' : 'ghost'} aria-pressed={layout === 'one'} onClick={() => setLayout('one')}>{languageLabel(language)}</Button>
          <Button size="sm" variant={layout === 'both' ? 'secondary' : 'ghost'} aria-pressed={layout === 'both'} onClick={() => setLayout('both')}>Side by side</Button>
        </div>
        <TextSizeControl prefs={prefs} />
      </div>
    </div>
    <nav className="collection-nav" aria-label={heading}>
      <ol>{groups.map(group => <li key={group.key}><a href={`#${anchorOf(group)}`}>{titleOf(group)}</a></li>)}</ol>
    </nav>
    {groups.map((group, index) => <article className="collection-prayer" id={anchorOf(group)} key={group.key} aria-labelledby={`${anchorOf(group)}-title`}>
      <h3 className="collection-prayer-title" id={`${anchorOf(group)}-title`}><span className="collection-number" aria-hidden="true">{index + 1}</span>{titleOf(group)}</h3>
      {layout === 'one' ? <Single group={group} prefs={prefs} textBadge={textBadge} /> : <Pair group={group} textBadge={textBadge} />}
    </article>)}
  </section>
}

function Single({ group, prefs, textBadge }: { group: TextGroup; prefs: ReadingPreferences; textBadge?: (text: PrayerText) => ReactNode }) {
  const { shown, missing } = versionsFor(group.versions, prefs.language)
  return <>
    {missing && <LanguageUnavailable language={prefs.language} available={group.versions.map(version => version.language)} onChoose={prefs.setLanguage} subject="this prayer" />}
    {shown.map(text => <PrayerVersion key={text.id} text={{ ...text, title: null }} showLanguage={false} compact badge={textBadge?.(text)} />)}
  </>
}

/** Latin and English together, each in its own column. A missing language leaves a stated gap, never the other language's wording. */
function Pair({ group, textBadge }: { group: TextGroup; textBadge?: (text: PrayerText) => ReactNode }) {
  return <div className="collection-pair">
    {['la', 'en'].map(code => {
      const { shown } = versionsFor(group.versions, code)
      return <div className="collection-column" key={code} lang={code}>
        {shown.length ? shown.map(text => <PrayerVersion key={text.id} text={{ ...text, title: null }} showLanguage compact badge={textBadge?.(text)} />)
          : <div className="language-unavailable" role="note"><p><strong>{languageLabel(code)} text is not yet available for this prayer.</strong></p></div>}
      </div>
    })}
  </div>
}
