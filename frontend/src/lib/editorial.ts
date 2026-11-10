import { useQuery } from '@tanstack/react-query'
import { ApiError, api } from '../services/api'
import type { DecisionKind, EditorialAccess, EditorialBrief, LicenseStatus, TextStatus, TextSummary, WorkflowStatus } from '../types/devotions'

// ---- Who may do what -------------------------------------------------------------------------
/** The caller's own editorial roles. Both false for an ordinary account; this grants nothing. */
export function useEditorialAccess() {
  return useQuery({ queryKey: ['editorial-access'], queryFn: () => api<EditorialAccess>('/editorial-access'), staleTime: 5 * 60_000 })
}

// ---- Statuses, in words (never colour alone: every status has a label and an icon) --------------------
export type Tone = 'neutral' | 'progress' | 'attention' | 'good' | 'stop'

export const workflowLabels: Record<WorkflowStatus, string> = {
  proposed: 'Proposed', source_verified: 'Source verified', pending_approval: 'Awaiting approval', approved: 'Approved', published: 'Published',
}
export const textStatusLabels: Record<TextStatus, string> = {
  proposed: 'Proposed', source_verified: 'Source verified', pending_approval: 'Awaiting approval', approved: 'Approved',
}
export const workflowTone: Record<WorkflowStatus, Tone> = { proposed: 'neutral', source_verified: 'progress', pending_approval: 'attention', approved: 'good', published: 'good' }
export const WORKFLOW_ORDER: WorkflowStatus[] = ['proposed', 'source_verified', 'pending_approval', 'approved', 'published']

export const decisionLabels: Record<DecisionKind | 'transition', string> = {
  return_for_research: 'Returned for further research', reject_text: 'Text rejected', reject_approval: 'Approval declined', withdraw: 'Approval withdrawn', transition: 'Moved',
}

// ---- The review queue: one line per devotion, English and Latin kept apart ------------------------------
export interface LanguageSummary { label: string; tone: Tone; detail: string | null }

/** How one language stands for a devotion: the least advanced of its texts, and whether wording is withheld. */
export function languageSummary(brief: EditorialBrief, language: string): LanguageSummary {
  const rows = brief.texts.filter(text => text.language === language)
  if (rows.length === 0) return { label: 'No text', tone: 'neutral', detail: null }
  const order: TextStatus[] = ['proposed', 'source_verified', 'pending_approval', 'approved']
  const least = rows.reduce((low, row) => (order.indexOf(row.status) < order.indexOf(low.status) ? row : low))
  const withheld = rows.some(row => !row.has_body)
  if (withheld && least.status === 'proposed') return { label: 'Wording withheld', tone: 'stop', detail: 'Citation and link only' }
  return { label: textStatusLabels[least.status], tone: workflowTone[least.status], detail: rows.length > 1 ? `${rows.length} prayers` : null }
}

export function sourceSummary(rows: TextSummary[]): LanguageSummary {
  if (rows.length === 0) return { label: 'No texts', tone: 'neutral', detail: null }
  const verified = rows.filter(row => row.source_verified).length
  if (verified === rows.length) return { label: 'Verified', tone: 'good', detail: null }
  return { label: verified ? 'Partly verified' : 'Not verified', tone: verified ? 'progress' : 'attention', detail: `${verified} of ${rows.length}` }
}

export function rightsSummary(rows: TextSummary[]): LanguageSummary {
  if (rows.length === 0) return { label: '—', tone: 'neutral', detail: null }
  const statuses = new Set<LicenseStatus>(rows.map(row => row.license_status))
  if (statuses.has('restricted')) return { label: 'Restricted', tone: 'stop', detail: 'Wording withheld' }
  if (statuses.has('unverified')) return { label: 'Not yet checked', tone: 'attention', detail: null }
  return { label: 'Cleared', tone: 'good', detail: null }
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

// ---- Errors: each kind is told apart ------------------------------------------------------------------------
export type EditorialErrorKind = 'unauthenticated' | 'forbidden' | 'missing' | 'unavailable' | 'server' | 'network' | 'other'

export function describeEditorialError(error: unknown): { kind: EditorialErrorKind; message: string } {
  if (error instanceof ApiError) {
    if (error.status === 401) return { kind: 'unauthenticated', message: 'Your session couldn’t be verified. Please sign in again.' }
    if (error.status === 403) return { kind: 'forbidden', message: 'Your account doesn’t hold the editorial role this needs.' }
    if (error.status === 404) return { kind: error.message === 'Not Found' ? 'unavailable' : 'missing', message: error.message === 'Not Found' ? 'The editorial service isn’t available on this server yet (404 Not Found). The server probably needs to be updated.' : error.message }
    if (error.status >= 500) return { kind: 'server', message: `The editorial service is temporarily unavailable (server error ${error.status}). Please try again in a moment.` }
    return { kind: 'other', message: error.message }
  }
  return { kind: 'network', message: 'We couldn’t reach the server. Check your connection and try again.' }
}

/** Why an action is not available to this person right now, or null when it is. */
export function whyNot(access: EditorialAccess | undefined, role: 'editor' | 'approver' | 'either'): string | null {
  if (!access) return null
  const ok = role === 'editor' ? access.is_editor : role === 'approver' ? access.is_approver : access.is_editor || access.is_approver
  if (ok) return null
  return role === 'approver' ? 'Only an approver can do this.' : role === 'editor' ? 'Only an editor can do this.' : 'This needs an editorial role.'
}

/** True while the explanatory prose was drafted with AI assistance and nobody has approved it yet. */
export const proseIsUnapproved = (devotion: { prose_origin: string | null; status: WorkflowStatus }) => devotion.prose_origin === 'ai_draft' && devotion.status !== 'approved' && devotion.status !== 'published'
