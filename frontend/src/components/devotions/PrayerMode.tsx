import { useMemo, useState, type KeyboardEvent } from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { Button } from '../ui'
import { availableLanguages, groupBySlot, languageLabel, resolveLanguage, versionsFor } from '../../lib/devotions'
import type { Devotion, DevotionStep, PrayerText } from '../../types/devotions'
import { LanguageToggle, PrayerVersion, TextSizeControl, UnpublishedNotice, type ReadingPreferences } from './PrayerText'

function Versions({ versions, choice, languages, response = false }: { versions: PrayerText[]; choice: string; languages: string[]; response?: boolean }) {
  if (versions.length === 0) return <UnpublishedNotice compact />
  const { shown, missing } = versionsFor(versions, choice)
  return <div className={response ? 'is-response-text' : undefined}>
    {missing && <p className="prayer-note" role="note">No {languageLabel(missing)} version of this text has been published yet.</p>}
    <div className={`prayer-versions ${shown.length > 1 ? 'is-parallel' : ''}`}>{shown.map(text => <PrayerVersion key={text.id} text={text} showLanguage={languages.length > 1} compact />)}</div>
  </div>
}

function StepView({ step, slots, choice, languages }: { step: DevotionStep; slots: Map<string, PrayerText[]>; choice: string; languages: string[] }) {
  return <div className="prayer-step">
    {step.section && <p className="prayer-step-section">{step.section}</p>}
    {step.title && <h3 className="prayer-step-title">{step.title}</h3>}
    {step.instruction && <div className="instruction" role="note"><span className="instruction-label">Instruction</span><p>{step.instruction}</p></div>}
    {step.repeat && step.repeat > 1 ? <p className="repeat-note">Pray this {step.repeat} times</p> : null}
    {step.kind !== 'instruction' && <Versions versions={step.text_slot ? slots.get(step.text_slot) ?? [] : []} choice={choice} languages={languages} response={step.kind === 'response'} />}
  </div>
}

/**
 * A quiet, full-screen way to read the prayer. Steps are moved through with Previous and Next (or the
 * arrow keys). It deliberately keeps no record: no counts, no completion, no streaks.
 */
export function PrayerMode({ devotion, prefs, onClose }: { devotion: Devotion; prefs: ReadingPreferences; onClose: () => void }) {
  const [index, setIndex] = useState(0)
  const languages = useMemo(() => availableLanguages(devotion.texts), [devotion.texts])
  const choice = resolveLanguage(prefs.language, languages)
  const slots = useMemo(() => new Map(groupBySlot(devotion.texts).map(group => [group.slot, group.versions])), [devotion.texts])
  const steps = devotion.steps
  const sequenced = steps.length > 0
  const last = steps.length - 1
  const go = (direction: 1 | -1) => setIndex(current => Math.min(last, Math.max(0, current + direction)))
  function onKeyDown(event: KeyboardEvent) {
    if (!sequenced || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
    if (event.key === 'ArrowRight') { event.preventDefault(); go(1) }
    if (event.key === 'ArrowLeft') { event.preventDefault(); go(-1) }
  }
  return <DialogPrimitive.Root open onOpenChange={open => { if (!open) onClose() }}>
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="prayer-overlay" />
      <DialogPrimitive.Content className="prayer-mode" data-size={prefs.size} aria-describedby={undefined} onKeyDown={onKeyDown}>
        <div className="prayer-mode-bar">
          <DialogPrimitive.Title className="prayer-mode-title">{devotion.title}</DialogPrimitive.Title>
          <div className="reading-controls"><LanguageToggle languages={languages} value={choice} onChange={prefs.setLanguage} /><TextSizeControl prefs={prefs} />
            <DialogPrimitive.Close asChild><Button variant="ghost" size="sm"><X size={16} aria-hidden="true" />Leave prayer mode</Button></DialogPrimitive.Close></div>
        </div>
        <div className="prayer-mode-body">
          {sequenced
            ? <StepView key={index} step={steps[index]} slots={slots} choice={choice} languages={languages} />
            : <div className="prayer-step">{[...slots.values()].map(versions => <Versions key={versions[0].slot} versions={versions} choice={choice} languages={languages} />)}</div>}
        </div>
        {sequenced && <nav className="prayer-mode-nav" aria-label="Prayer steps">
          <Button variant="outline" onClick={() => go(-1)} disabled={index === 0}><ChevronLeft size={18} aria-hidden="true" />Previous<span className="sr-only"> step</span></Button>
          <p className="prayer-step-count" aria-live="polite">Step {index + 1} of {steps.length}</p>
          <Button variant="outline" onClick={() => go(1)} disabled={index === last}>Next<span className="sr-only"> step</span><ChevronRight size={18} aria-hidden="true" /></Button>
        </nav>}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  </DialogPrimitive.Root>
}
