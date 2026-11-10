import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Eye } from 'lucide-react'
import { Button } from '../ui'
import { ErrorMessage } from '../common'
import { api } from '../../services/api'
import { SUPPORTED_LANGUAGES } from '../../lib/devotions'
import { WORKFLOW_ORDER, decisionLabels, formatDate, textStatusLabels, whyNot, workflowLabels, describeEditorialError } from '../../lib/editorial'
import type { DecisionKind, EditorialAccess, EditorialDevotion, EditorialEvent, WorkflowStatus } from '../../types/devotions'
import { ConfirmAction, StatusBadge } from './EditorialParts'

type Role = 'editor' | 'approver' | 'either'
interface Act { key: string; label: string; to: WorkflowStatus; decision?: DecisionKind; role: Role; reason?: string; destructive?: boolean; primary?: boolean; blockedBy?: string | null }

function actionsFor(devotion: EditorialDevotion): Act[] {
  const blockers = devotion.problems.length ? 'Resolve the points listed below first.' : null
  const returning = (role: Role): Act => ({ key: 'return', label: 'Return for further research', to: 'proposed', decision: 'return_for_research', role, reason: 'What needs further research?' })
  switch (devotion.status) {
    case 'proposed': return [{ key: 'verify', label: 'Mark devotion details as verified', to: 'source_verified', role: 'editor', primary: true, blockedBy: blockers }]
    case 'source_verified': return [{ key: 'submit', label: 'Submit devotion for approval', to: 'pending_approval', role: 'editor', primary: true }, returning('editor')]
    case 'pending_approval': return [
      { key: 'approve', label: 'Approve this devotion', to: 'approved', role: 'approver', primary: true },
      { key: 'decline', label: 'Reject approval', to: 'proposed', decision: 'reject_approval', role: 'approver', reason: 'Why is approval being declined?', destructive: true },
      returning('either'),
    ]
    case 'approved': return [
      { key: 'publish', label: 'Publish to The Oratory', to: 'published', role: 'approver', primary: true, blockedBy: devotion.publication_problems.length ? 'Not every condition for publishing is met yet.' : null },
      { key: 'withdraw', label: 'Withdraw approval', to: 'proposed', decision: 'withdraw', role: 'approver', reason: 'Why is approval being withdrawn?', destructive: true },
    ]
    case 'published': return [
      { key: 'unpublish', label: 'Unpublish', to: 'approved', role: 'approver', destructive: true },
      { key: 'withdraw', label: 'Withdraw approval', to: 'proposed', decision: 'withdraw', role: 'approver', reason: 'Why is approval being withdrawn?', destructive: true },
    ]
  }
}

const confirmCopy: Record<string, { title: string; body: string }> = {
  verify: { title: 'Mark the devotion details as verified?', body: 'You are confirming that its overview, instructions, structure and references are in order. This does not verify any prayer text; each text is verified and approved separately.' },
  submit: { title: 'Submit the devotion for approval?', body: 'It goes to an approver. It stays hidden from readers until it is approved and published.' },
  approve: { title: 'Approve this devotion?', body: 'This approves the devotion’s own content (overview, instructions, structure, references). It does not approve any prayer text, and it does not publish anything.' },
  publish: { title: 'Publish to The Oratory?', body: 'Every signed-in reader will be able to open this devotion. Only prayer texts that are individually approved will be shown; the rest stay hidden.' },
  unpublish: { title: 'Unpublish this devotion?', body: 'Readers will no longer see it. Its approvals are kept.' },
  return: { title: 'Return for further research?', body: 'The devotion goes back to proposed and loses its verification.' },
  decline: { title: 'Reject approval?', body: 'The devotion goes back to proposed.' },
  withdraw: { title: 'Withdraw approval?', body: 'The devotion stops being shown to readers and goes back to proposed.' },
}

/** Which languages a reader would see if this devotion were published right now, text by text. */
function ReaderVisibility({ devotion }: { devotion: EditorialDevotion }) {
  return <ul className="reader-visibility" aria-label="What readers would see">{SUPPORTED_LANGUAGES.map(language => {
    const rows = devotion.texts.filter(text => text.language === language.code)
    const shown = rows.filter(text => text.status === 'approved' && text.approval_current).length
    return <li key={language.code}><strong>{language.label}:</strong> {rows.length === 0 ? 'no text entered' : shown === rows.length ? `all ${rows.length} approved: shown` : `${shown} of ${rows.length} approved: the rest stay hidden`}</li>
  })}</ul>
}

/** The devotion's own approval (separate from each text's), what it needs, and the actions open to this reviewer. */
export function DevotionDecisions({ devotion, access }: { devotion: EditorialDevotion; access: EditorialAccess }) {
  const [pending, setPending] = useState<Act | null>(null)
  const actions = actionsFor(devotion)
  const notes = [...new Set(actions.map(act => whyNot(access, act.role)).filter((note): note is string => !!note))]
  const copy = pending ? confirmCopy[pending.key] : null
  const current = WORKFLOW_ORDER.indexOf(devotion.status)
  return <section className="editorial-section" aria-labelledby="decisions-title">
    <h2 id="decisions-title">Devotion status and publication</h2>
    <ol className="workflow-steps" aria-label="Workflow">{WORKFLOW_ORDER.map((status, index) => <li key={status} className={index < current ? 'is-done' : index === current ? 'is-current' : ''} aria-current={index === current ? 'step' : undefined}><span>{workflowLabels[status]}</span></li>)}</ol>
    <p className="decision-intro">The devotion’s own approval is separate from the approval of each prayer text. Publishing needs both.</p>
    {devotion.problems.length > 0 && <div className="text-problems"><p><strong>Before the devotion can be verified</strong></p><ul>{devotion.problems.map(problem => <li key={problem}>{problem}</li>)}</ul></div>}
    <div className="publication-checks">
      <h3>Conditions for publishing</h3>
      {devotion.publication_problems.length === 0 ? <p><StatusBadge label="All conditions are met" tone="good" /></p>
        : <ul>{devotion.publication_problems.map(problem => <li key={problem}><StatusBadge label="Not yet" tone="attention" /> {problem}</li>)}</ul>}
      <ReaderVisibility devotion={devotion} />
    </div>
    <div className="text-actions" role="group" aria-label="Devotion actions">
      {actions.map(act => {
        const blocked = whyNot(access, act.role) ?? act.blockedBy ?? null
        return <Button key={act.key} variant={act.primary ? 'default' : 'outline'} disabled={!!blocked} title={blocked ?? undefined} onClick={() => setPending(act)}>{act.label}</Button>
      })}
      <Button asChild variant="outline"><Link to={`/editorial/devotions/${devotion.id}/preview`}><Eye size={16} aria-hidden="true" />Preview as readers will see it</Link></Button>
    </div>
    {notes.length > 0 && <p className="action-note">{notes.join(' ')}</p>}
    {pending && copy && <ConfirmAction title={copy.title} description={copy.body} confirmLabel={pending.label} destructive={pending.destructive} reasonLabel={pending.reason}
      onConfirm={reason => api(`/editorial/devotions/${devotion.id}/transition`, 'POST', { to: pending.to, note: reason, decision: pending.decision })} onClose={() => setPending(null)}>
      {pending.key === 'publish' && <ReaderVisibility devotion={devotion} />}
    </ConfirmAction>}
  </section>
}

function eventLabel(event: EditorialEvent): string {
  if (event.action in decisionLabels && event.action !== 'transition') return decisionLabels[event.action as DecisionKind]
  const labels: Record<string, string> = { created: 'Created', seeded: 'Draft record created', updated: 'Edited', text_created: 'Text added', text_updated: 'Text edited', text_deleted: 'Text removed' }
  if (event.action in labels) return labels[event.action]
  const to = event.to_status
  return to ? `Moved to ${(workflowLabels as Record<string, string>)[to] ?? (textStatusLabels as Record<string, string>)[to] ?? to}` : 'Moved'
}

/** Who did what, and when. Wording is never in the log, only field names and reasons. */
export function ActivityLog({ devotion }: { devotion: EditorialDevotion }) {
  const events = useQuery({ queryKey: ['editorial-events', devotion.id, devotion.updated_at], queryFn: () => api<EditorialEvent[]>(`/editorial/devotions/${devotion.id}/events`) })
  const names = new Map(devotion.texts.map(text => [text.id, `${text.language.toUpperCase()} · ${text.slot}`]))
  return <details className="editorial-section activity-log"><summary><h2>Activity</h2></summary>
    {events.isPending ? <p className="muted">Loading…</p> : events.isError ? <ErrorMessage message={describeEditorialError(events.error).message} />
      : events.data.length === 0 ? <p className="muted">Nothing has been recorded yet.</p>
      : <ol>{[...events.data].reverse().map(event => <li key={event.id}><span className="activity-when">{formatDate(event.created_at)}</span> <strong>{eventLabel(event)}</strong>{event.text_id && names.get(event.text_id) && <> · {names.get(event.text_id)}</>}<span className="activity-who"> · {event.actor}</span>{event.note && <> — <q>{event.note}</q></>}</li>)}</ol>}
  </details>
}

