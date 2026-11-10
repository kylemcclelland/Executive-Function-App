import { useState, type ReactNode } from 'react'
import { ExternalLink } from 'lucide-react'
import { Button } from '../ui'
import { PrayerBody } from '../devotions/PrayerText'
import { api } from '../../services/api'
import { languageLabel, rightsLabels, safeUrl } from '../../lib/devotions'
import { decisionLabels, formatDate, textStatusLabels, whyNot, workflowTone, type Tone } from '../../lib/editorial'
import type { DecisionKind, EditorialAccess, EditorialDevotion, EditorialText, TextStatus } from '../../types/devotions'
import { ConfirmAction, StatusBadge } from './EditorialParts'

type Role = 'editor' | 'approver' | 'either'
interface Act { key: string; label: string; to: TextStatus; decision?: DecisionKind; role: Role; reason?: string; confirm: boolean; destructive?: boolean; primary?: boolean; blockedBy?: string | null }

const returnForResearch = (role: Role): Act => ({ key: 'return', label: 'Return for further research', to: 'proposed', decision: 'return_for_research', role, reason: 'What needs further research?', confirm: true })
const rejectText: Act = { key: 'reject', label: 'Reject this text', to: 'proposed', decision: 'reject_text', role: 'either', reason: 'Why is this text being rejected?', confirm: true, destructive: true }

/** What can be done to a text from where it stands. The server enforces order and roles again on every request. */
function actionsFor(text: EditorialText): Act[] {
  switch (text.status) {
    case 'proposed': return [
      { key: 'verify', label: 'Mark source as verified', to: 'source_verified', role: 'editor', confirm: true, primary: true, blockedBy: text.problems.length ? 'Resolve the points listed above first.' : null },
      rejectText,
    ]
    case 'source_verified': return [
      { key: 'submit', label: 'Submit for approval', to: 'pending_approval', role: 'editor', confirm: true, primary: true },
      returnForResearch('editor'), rejectText,
    ]
    case 'pending_approval': return [
      { key: 'approve', label: 'Approve this text', to: 'approved', role: 'approver', confirm: true, primary: true },
      { key: 'decline', label: 'Reject approval', to: 'proposed', decision: 'reject_approval', role: 'approver', reason: 'Why is approval being declined?', confirm: true, destructive: true },
      returnForResearch('either'),
    ]
    case 'approved': return [
      { key: 'withdraw', label: 'Withdraw approval', to: 'proposed', decision: 'withdraw', role: 'approver', reason: 'Why is approval being withdrawn?', confirm: true, destructive: true },
    ]
  }
}

const confirmCopy: Record<string, { title: string; body: (text: EditorialText, label: string) => string }> = {
  verify: { title: 'Mark this source as verified?', body: (text, label) => `You are confirming that the ${languageLabel(text.language)} wording of “${label}” matches its cited source exactly, and that its rights allow it to be shown.` },
  submit: { title: 'Submit for approval?', body: (text, label) => `The ${languageLabel(text.language)} text of “${label}” will go to an approver. It stays hidden from readers until it is approved.` },
  approve: { title: 'Approve this exact text?', body: (text, label) => `Approving the ${languageLabel(text.language)} text of “${label}” lets it appear in the Oratory once its devotion is published. The approval applies to exactly this wording and these source details; changing any of them cancels it.` },
  return: { title: 'Return for further research?', body: (text, label) => `The ${languageLabel(text.language)} text of “${label}” goes back to proposed and loses its verification. Say what needs checking.` },
  reject: { title: 'Reject this text?', body: (text, label) => `The ${languageLabel(text.language)} text of “${label}” stays unpublished. The reason is kept in the log.` },
  decline: { title: 'Reject approval?', body: (text, label) => `The ${languageLabel(text.language)} text of “${label}” goes back to proposed. Say what was wrong.` },
  withdraw: { title: 'Withdraw approval?', body: (text, label) => `The ${languageLabel(text.language)} text of “${label}” stops being shown to readers at once. Say why.` },
}

function textAsPrayer(text: EditorialText) {
  return {
    id: text.id, slot: text.slot, language: text.language, title: text.title, body: text.body,
    source: { title: text.source_title, edition: text.source_edition, translator: text.translator, is_translation: text.is_translation, attribution: text.attribution, url: text.source_url, license_status: text.license_status },
  }
}

/** Why there is no wording to show, in terms of its rights, so the reason is never a mystery. */
function Withheld({ text }: { text: EditorialText }) {
  const link = safeUrl(text.source_url)
  const why = text.license_status === 'restricted' ? 'Its owner’s terms do not clearly permit republishing it, so only the citation and a link are kept.'
    : text.license_status === 'unverified' ? 'No wording is held, and its reproduction rights have not been checked yet.'
    : 'No wording has been obtained yet.'
  return <div className="withheld-box" role="note"><strong>Wording withheld.</strong> <span>{why}</span>{link && <a href={link} target="_blank" rel="noopener noreferrer">Read it at the source <ExternalLink size={14} aria-hidden="true" /></a>}</div>
}

/** The facts a reviewer needs to check one text against its source. */
export function TextFacts({ text }: { text: EditorialText }) {
  const link = safeUrl(text.source_url)
  const rows: { label: string; value: ReactNode }[] = [
    { label: 'Source', value: text.source_title ?? <em>Not recorded</em> },
    { label: 'Issued by', value: text.source_authority ?? <em>Not recorded</em> },
    { label: 'Edition', value: text.source_edition ?? <em>Not recorded</em> },
    { label: 'Published', value: text.source_date ?? <em>Not recorded</em> },
    { label: 'Link', value: link ? <a href={link} target="_blank" rel="noopener noreferrer">{link} <ExternalLink size={13} aria-hidden="true" /></a> : <em>None</em> },
    { label: 'Translation', value: text.is_translation ? `Translated by ${text.translator ?? '(translator not recorded)'}` : 'Original-language text, not a translation' },
    { label: 'Attribution', value: text.attribution ?? <em>Not recorded</em> },
    { label: 'Reproduction rights', value: <>{rightsLabels[text.license_status]}{text.license_notes && <details className="fact-details"><summary>Basis and evidence</summary><p>{text.license_notes}</p></details>}</> },
    { label: 'Copied from the source', value: text.source_retrieved_at ? formatDate(text.source_retrieved_at) : <em>Not recorded</em> },
    { label: 'Entered by', value: text.entered_by },
    { label: 'Source verified', value: text.source_verified_at ? `${formatDate(text.source_verified_at)} by ${text.source_verified_by}` : 'Not yet' },
    { label: 'Approved', value: text.approved_at ? `${formatDate(text.approved_at)} by ${text.approved_by}` : 'Not yet' },
  ]
  return <dl className="text-facts">{rows.map(({ label, value }) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
}

export function TextStatusBadges({ text }: { text: EditorialText }) {
  const rightsTone: Tone = text.license_status === 'restricted' ? 'stop' : text.rights_cleared ? 'good' : 'attention'
  return <span className="badge-row">
    <StatusBadge label={textStatusLabels[text.status]} tone={workflowTone[text.status]} />
    <StatusBadge label={rightsLabels[text.license_status]} tone={rightsTone} />
    {!text.has_body && <StatusBadge label="No wording held" tone="stop" />}
    {text.status === 'approved' && !text.approval_current && <StatusBadge label="Approval no longer matches" tone="attention" />}
  </span>
}

function LastDecision({ text }: { text: EditorialText }) {
  const event = text.last_event
  if (!event || !(event.action in decisionLabels) || event.action === 'transition' && !event.note) return null
  const label = event.action === 'transition' ? `Moved to ${textStatusLabels[event.to_status as TextStatus] ?? event.to_status}` : decisionLabels[event.action as DecisionKind]
  return <p className="last-decision"><strong>{label}</strong> · {formatDate(event.created_at)} · {event.actor}{event.note && <> — <q>{event.note}</q></>}</p>
}

interface Props { devotion: EditorialDevotion; text: EditorialText; label: string; access: EditorialAccess; readOnly?: boolean }

/** One prayer text in one language, with its source, rights, history and the actions open to this reviewer. */
export function TextReview({ devotion, text, label, access, readOnly = false }: Props) {
  const [pending, setPending] = useState<Act | null>(null)
  const actions = readOnly ? [] : actionsFor(text)
  const notes = [...new Set(actions.map(act => whyNot(access, act.role)).filter((note): note is string => !!note))]
  const copy = pending ? confirmCopy[pending.key] : null
  return <article className="text-review" aria-label={`${languageLabel(text.language)} text: ${label}`}>
    <header><h3>{label}</h3><TextStatusBadges text={text} /></header>
    {text.has_body ? <div className="wording-box" lang={text.language}><PrayerBody text={textAsPrayer(text)} /></div> : <Withheld text={text} />}
    <TextFacts text={text} />
    <LastDecision text={text} />
    {text.problems.length > 0 && text.status === 'proposed' && <div className="text-problems"><p><strong>Before this can be verified</strong></p><ul>{text.problems.map(problem => <li key={problem}>{problem}</li>)}</ul></div>}
    {actions.length > 0 && <div className="text-actions" role="group" aria-label={`Actions for the ${languageLabel(text.language)} text of ${label}`}>
      {actions.map(act => {
        const blocked = whyNot(access, act.role) ?? act.blockedBy ?? null
        return <Button key={act.key} variant={act.primary ? 'default' : act.destructive ? 'outline' : 'outline'} disabled={!!blocked} title={blocked ?? undefined} onClick={() => setPending(act)}>{act.label}</Button>
      })}
    </div>}
    {notes.length > 0 && <p className="action-note">{notes.join(' ')}</p>}
    {pending && copy && <ConfirmAction title={copy.title} description={copy.body(text, label)} confirmLabel={pending.label} destructive={pending.destructive} reasonLabel={pending.reason}
      onConfirm={reason => api(`/editorial/devotions/${devotion.id}/texts/${text.id}/transition`, 'POST', { to: pending.to, note: reason, decision: pending.decision })} onClose={() => setPending(null)}>
      <dl className="confirm-facts"><div><dt>Source</dt><dd>{text.source_title ?? '—'}{text.source_edition ? `, ${text.source_edition}` : ''}</dd></div><div><dt>Rights</dt><dd>{rightsLabels[text.license_status]}</dd></div></dl>
    </ConfirmAction>}
  </article>
}
