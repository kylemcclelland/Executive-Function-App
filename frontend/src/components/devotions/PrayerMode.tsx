import { useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { Button } from '../ui'
import { groupTexts, languageLabel, stepGroups, stepTextKey, versionsFor, visibleSteps, type TextGroup } from '../../lib/devotions'
import type { Devotion, DevotionStep, PrayerText } from '../../types/devotions'
import { LanguageSelect, LanguageUnavailable, PrayerVersion, TextSizeControl, UnpublishedNotice, type ReadingPreferences } from './PrayerText'

interface VersionsProps { group: TextGroup | undefined; language: string; onChoose: (language: string) => void; response?: boolean; badge?: (text: PrayerText) => ReactNode }

/** One prayer in the reader's language. If that language does not exist for it, it says so; it never shows another. */
function Versions({ group, language, onChoose, response = false, badge }: VersionsProps) {
  if (!group) return <UnpublishedNotice compact />
  const { shown, missing } = versionsFor(group.versions, language)
  return <div className={response ? 'is-response-text' : undefined}>
    {missing && <LanguageUnavailable language={language} available={group.versions.map(version => version.language)} onChoose={onChoose} subject="this prayer" />}
    <div className="prayer-versions">{shown.map(text => <PrayerVersion key={text.id} text={text} showLanguage={false} compact badge={badge?.(text)} />)}</div>
  </div>
}

function StepView({ devotion, step, groups, language, onChoose, badge }: { devotion: Devotion; step: DevotionStep; groups: Map<string, TextGroup>; language: string; onChoose: (language: string) => void; badge?: (text: PrayerText) => ReactNode }) {
  const key = stepTextKey(devotion, step)
  return <div className="prayer-step">
    {step.section && <p className="prayer-step-section">{step.section}</p>}
    {step.title && <h3 className="prayer-step-title">{step.title}</h3>}
    {step.optional && <p className="step-optional">Optional custom</p>}
    {step.instruction && <div className="instruction" role="note"><span className="instruction-label">Instruction</span><p>{step.instruction}</p></div>}
    {step.repeat && step.repeat > 1 ? <p className="repeat-note">Pray this {step.repeat} times</p> : null}
    {step.kind !== 'instruction' && <Versions group={key ? groups.get(key) : undefined} language={language} onChoose={onChoose} response={step.kind === 'response'} badge={badge} />}
  </div>
}

/**
 * A quiet, full-screen way to read the prayer. Steps are moved through with Previous and Next (or the
 * arrow keys). Changing language or text size keeps the reader exactly where they are, and so does
 * choosing between sets (the mysteries) only when it must. It deliberately keeps no record: no counts,
 * no completion, no streaks.
 */
export function PrayerMode({ devotion, prefs, onClose, textBadge }: { devotion: Devotion; prefs: ReadingPreferences; onClose: () => void; textBadge?: (text: PrayerText) => ReactNode }) {
  const choices = useMemo(() => stepGroups(devotion.steps), [devotion.steps])
  const [choice, setChoice] = useState<string | null>(choices[0] ?? null)
  const [index, setIndex] = useState(0)
  const surface = useRef<HTMLDivElement>(null)
  const language = prefs.language
  const groups = useMemo(() => new Map(groupTexts(devotion, devotion.texts).map(group => [group.key, group])), [devotion])
  const steps = useMemo(() => visibleSteps(devotion.steps, choice), [devotion.steps, choice])
  const sequenced = devotion.steps.length > 0
  const last = steps.length - 1
  const go = (direction: 1 | -1) => setIndex(current => Math.min(last, Math.max(0, current + direction)))
  function choose(next: string) {
    const current = steps[index]
    const nextSteps = visibleSteps(devotion.steps, next)
    setChoice(next)
    // Common steps keep their place; from inside a set, begin the new set.
    const kept = current && !current.group ? nextSteps.indexOf(current) : -1
    setIndex(kept >= 0 ? kept : Math.max(0, nextSteps.findIndex(step => step.group === next)))
  }
  function onKeyDown(event: KeyboardEvent) {
    const target = event.target as HTMLElement
    if (!sequenced || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || target.tagName === 'SELECT') return
    if (event.key === 'ArrowRight') { event.preventDefault(); go(1) }
    if (event.key === 'ArrowLeft') { event.preventDefault(); go(-1) }
  }
  const current = steps[Math.min(index, last)]
  return <DialogPrimitive.Root open onOpenChange={open => { if (!open) onClose() }}>
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="prayer-overlay" />
      <DialogPrimitive.Content ref={surface} className="prayer-mode" data-size={prefs.size} aria-describedby={undefined} onKeyDown={onKeyDown} onOpenAutoFocus={event => { event.preventDefault(); surface.current?.focus() }}>
        <div className="prayer-mode-bar">
          <DialogPrimitive.Title className="prayer-mode-title">{devotion.title}</DialogPrimitive.Title>
          <div className="reading-controls">
            {choices.length > 0 && <div className="language-select"><label htmlFor="prayer-mode-choice">{devotion.choice_label ?? 'Choose'}</label><select id="prayer-mode-choice" value={choice ?? ''} onChange={event => choose(event.target.value)}>{choices.map(name => <option key={name} value={name}>{name}</option>)}</select></div>}
            <LanguageSelect value={language} onChange={prefs.setLanguage} />
            <TextSizeControl prefs={prefs} />
            <DialogPrimitive.Close asChild><Button variant="ghost" size="sm"><X size={16} aria-hidden="true" />Leave prayer mode</Button></DialogPrimitive.Close>
          </div>
        </div>
        <div className="prayer-mode-body">
          {sequenced && current
            ? <StepView key={`${choice}-${index}`} devotion={devotion} step={current} groups={groups} language={language} onChoose={prefs.setLanguage} badge={textBadge} />
            : <div className="prayer-step">{[...groups.values()].map(group => <Versions key={group.key} group={group} language={language} onChoose={prefs.setLanguage} badge={textBadge} />)}{groups.size === 0 && <UnpublishedNotice compact />}</div>}
          <p className="sr-only" aria-live="polite">{`Reading in ${languageLabel(language)}.`}</p>
        </div>
        {sequenced && <nav className="prayer-mode-nav" aria-label="Prayer steps">
          <Button variant="outline" onClick={() => go(-1)} disabled={index === 0}><ChevronLeft size={18} aria-hidden="true" />Previous<span className="sr-only"> step</span></Button>
          <p className="prayer-step-count" aria-live="polite">Step {Math.min(index, last) + 1} of {steps.length}</p>
          <Button variant="outline" onClick={() => go(1)} disabled={index >= last}>Next<span className="sr-only"> step</span><ChevronRight size={18} aria-hidden="true" /></Button>
        </nav>}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  </DialogPrimitive.Root>
}
