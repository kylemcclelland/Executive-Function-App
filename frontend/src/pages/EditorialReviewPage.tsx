import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { ArrowLeft, Columns2 } from 'lucide-react'
import { Button } from '../components/ui'
import { ErrorMessage, Loading } from '../components/common'
import { EditorialGate } from '../components/editorial/EditorialGate'
import { ProseNote, StatusBadge } from '../components/editorial/EditorialParts'
import { TextReview } from '../components/editorial/TextReview'
import { ActivityLog, DevotionDecisions } from '../components/editorial/DevotionDecisions'
import { SequenceOutline } from '../components/devotions/DevotionSections'
import { LanguageSelect } from '../components/devotions/PrayerText'
import { api } from '../services/api'
import { SUPPORTED_LANGUAGES, languageLabel, paragraphs, safeUrl, useReadingPreferences } from '../lib/devotions'
import { describeEditorialError, proseIsUnapproved, workflowLabels, workflowTone } from '../lib/editorial'
import type { EditorialAccess, EditorialBrief, EditorialDevotion, EditorialText } from '../types/devotions'
import '../components/editorial/editorial.css'

function slotName(devotion: EditorialDevotion, slot: string): string {
  const step = devotion.steps.find(candidate => candidate.text_slot === slot && !candidate.devotion_slug && candidate.title)
  return step?.title ?? (slot === 'main' ? devotion.title : slot.replace(/[-_]/g, ' ').replace(/^./, letter => letter.toUpperCase()))
}

function Info({ devotion }: { devotion: EditorialDevotion }) {
  return <section className="editorial-section" aria-labelledby="info-title">
    <h2 id="info-title">Devotion information</h2>
    {proseIsUnapproved(devotion) && <ProseNote />}
    <dl className="devotion-facts">
      <div><dt>Category</dt><dd>{devotion.category ?? '—'}</dd></div>
      <div><dt>Short description</dt><dd>{devotion.subtitle ?? '—'}</dd></div>
      <div><dt>Address</dt><dd><code>/devotions/{devotion.slug}</code></dd></div>
    </dl>
    <h3>Overview</h3>
    <div className="devotion-prose">{paragraphs(devotion.overview).map((part, index) => <p key={index}>{part}</p>)}</div>
    {devotion.background && <><h3>Historical background</h3><div className="devotion-prose">{paragraphs(devotion.background).map((part, index) => <p key={index}>{part}</p>)}</div></>}
    {devotion.significance && <><h3>Spiritual significance</h3><div className="devotion-prose">{paragraphs(devotion.significance).map((part, index) => <p key={index}>{part}</p>)}</div></>}
    {devotion.instructions.length > 0 && <><h3>How to pray</h3><ol className="instruction-list">{devotion.instructions.map((item, index) => <li key={index}>{item}</li>)}</ol></>}
    {devotion.references.length > 0 && <><h3>References</h3><ul className="devotion-references">{devotion.references.map((reference, index) => { const link = safeUrl(reference.url); return <li key={index}>{link ? <a href={link} target="_blank" rel="noopener noreferrer">{reference.label}</a> : reference.label}</li> })}</ul></>}
  </section>
}

/** The structure of a sequence, and which other devotions' prayers it reuses (and whether those are published yet). */
function Structure({ devotion, briefs }: { devotion: EditorialDevotion; briefs: EditorialBrief[] }) {
  if (devotion.steps.length === 0) return null
  const reused = [...new Set(devotion.steps.filter(step => step.devotion_slug && step.text_slot).map(step => `${step.devotion_slug}/${step.text_slot}`))]
  return <section className="editorial-section" aria-labelledby="structure-title">
    <h2 id="structure-title">Structure</h2>
    <p className="decision-intro">{devotion.steps.length} steps. Optional customs are marked; they never hold up publication.</p>
    <SequenceOutline steps={devotion.steps} choiceLabel={devotion.choice_label} />
    {reused.length > 0 && <div className="reused-prayers"><h3>Prayers reused from other devotions</h3><p className="muted">These are shown from their own devotion, never copied. A reused prayer appears to readers only once its own devotion is published and the text approved.</p>
      <ul>{reused.map(key => { const [slug, slot] = key.split('/'); const other = briefs.find(brief => brief.slug === slug); return <li key={key}>{other ? <Link to={`/editorial/devotions/${other.id}`}>{other.title}</Link> : <span>{slug}</span>} <code>{slot}</code> {other ? <StatusBadge label={workflowLabels[other.status]} tone={workflowTone[other.status]} /> : <StatusBadge label="Devotion not found" tone="stop" />}</li> })}</ul></div>}
  </section>
}

function Texts({ devotion, access }: { devotion: EditorialDevotion; access: EditorialAccess }) {
  const prefs = useReadingPreferences()
  const [compare, setCompare] = useState(false)
  const slots = [...new Set(devotion.texts.map(text => text.slot))]
  const pair = (slot: string) => SUPPORTED_LANGUAGES.map(language => devotion.texts.find(text => text.slot === slot && text.language === language.code))
  return <section className="editorial-section" aria-labelledby="texts-title">
    <div className="editorial-section-head">
      <h2 id="texts-title">Prayer texts</h2>
      <div className="editorial-controls">
        <LanguageSelect value={prefs.language} onChange={prefs.setLanguage} />
        <Button variant={compare ? 'default' : 'outline'} aria-pressed={compare} onClick={() => setCompare(value => !value)}><Columns2 size={16} aria-hidden="true" />Compare languages side by side</Button>
      </div>
    </div>
    <p className="decision-intro">English and Latin are reviewed, approved and rejected separately. Changing the language here changes only what you are looking at, never a status.</p>
    {slots.length === 0 && <p className="muted">This devotion holds no prayer texts of its own{devotion.steps.some(step => step.devotion_slug) ? '; it reuses prayers from other devotions (see Structure)' : ''}.</p>}
    {slots.map(slot => {
      const label = slotName(devotion, slot)
      const [latin, english] = [pair(slot)[SUPPORTED_LANGUAGES.findIndex(language => language.code === 'la')], pair(slot)[SUPPORTED_LANGUAGES.findIndex(language => language.code === 'en')]]
      const chosen = devotion.texts.find(text => text.slot === slot && text.language === prefs.language)
      const others = devotion.texts.filter(text => text.slot === slot && text.language !== prefs.language)
      return <div className="text-slot" key={slot}>
        {compare
          ? <div className="compare-grid">{[latin, english].map((text, index) => text
            ? <div key={text.id} className="compare-column"><TextReview devotion={devotion} text={text} label={label} access={access} readOnly /><Button variant="ghost" size="sm" onClick={() => { prefs.setLanguage(text.language); setCompare(false) }}>Review the {languageLabel(text.language)} text to act on it</Button></div>
            : <div key={index} className="compare-column"><div className="withheld-box" role="note"><strong>No {languageLabel(index === 0 ? 'la' : 'en')} text entered</strong> <span>for “{label}”.</span></div></div>)}</div>
          : chosen ? <TextReview devotion={devotion} text={chosen as EditorialText} label={label} access={access} />
          : <div className="withheld-box" role="note"><strong>No {languageLabel(prefs.language)} text has been entered for “{label}”.</strong>{others.length > 0 && <span> It exists in {others.map(text => languageLabel(text.language)).join(', ')}: switch the language above to review it.</span>}</div>}
      </div>
    })}
  </section>
}

function Review({ id, access }: { id: string; access: EditorialAccess }) {
  const devotion = useQuery({ queryKey: ['editorial-devotion', id], queryFn: () => api<EditorialDevotion>(`/editorial/devotions/${id}`) })
  const queue = useQuery({ queryKey: ['editorial-devotions'], queryFn: () => api<EditorialBrief[]>('/editorial/devotions') })
  if (devotion.isPending) return <Loading />
  if (devotion.isError) {
    const problem = describeEditorialError(devotion.error)
    return <div className="editorial-problem"><ErrorMessage message={problem.message} /><div className="editorial-problem-actions">{problem.kind !== 'forbidden' && problem.kind !== 'missing' && <Button variant="outline" onClick={() => void devotion.refetch()}>Try again</Button>}<Button asChild variant="ghost"><Link to="/editorial/devotions">Back to the review queue</Link></Button></div></div>
  }
  const data = devotion.data
  return <>
    <nav aria-label="Breadcrumb"><Link className="devotion-back" to="/editorial/devotions"><ArrowLeft size={16} aria-hidden="true" /> Review queue</Link></nav>
    <header className="review-header"><h1>{data.title}</h1><p className="review-meta"><StatusBadge label={workflowLabels[data.status]} tone={workflowTone[data.status]} />{data.category && <span className="tag">{data.category}</span>}</p></header>
    <Info devotion={data} />
    <Structure devotion={data} briefs={queue.data ?? []} />
    <Texts devotion={data} access={access} />
    <DevotionDecisions devotion={data} access={access} />
    <ActivityLog devotion={data} />
  </>
}

/** The detailed review of one devotion: its information, structure, every text with its source and rights, and the decisions. */
export function EditorialReviewPage() {
  const { id = '' } = useParams()
  return <div className="editorial"><EditorialGate>{access => <Review id={id} access={access} />}</EditorialGate></div>
}
