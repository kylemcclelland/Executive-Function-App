import { useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Ban, CircleCheck, CircleDashed, Clock, TriangleAlert, type LucideIcon } from 'lucide-react'
import { Button, Dialog } from '../ui'
import { ErrorMessage } from '../common'
import type { Tone } from '../../lib/editorial'

const icons: Record<Tone, LucideIcon> = { neutral: CircleDashed, progress: Clock, attention: TriangleAlert, good: CircleCheck, stop: Ban }

/** A status in words and an icon, never colour alone. */
export function StatusBadge({ label, tone, detail }: { label: string; tone: Tone; detail?: string | null }) {
  const Icon = icons[tone]
  return <span className={`status-badge is-${tone}`}><Icon size={14} aria-hidden="true" /><span>{label}</span>{detail && <small>{detail}</small>}</span>
}

interface ConfirmProps {
  title: string
  description: string
  confirmLabel: string
  destructive?: boolean
  /** Asks for a reason, recorded in the editorial log. Required for any decision that turns something down. */
  reasonLabel?: string
  children?: ReactNode
  onConfirm: (reason: string | undefined) => Promise<unknown>
  onClose: () => void
}

/** A confirmation for a consequential step. Nothing happens until the person confirms in this dialog. */
export function ConfirmAction({ title, description, confirmLabel, destructive = false, reasonLabel, children, onConfirm, onClose }: ConfirmProps) {
  const client = useQueryClient()
  const [reason, setReason] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  async function submit() {
    if (reasonLabel && !reason.trim()) { setError('Please give a reason: it is kept in the editorial log.'); return }
    setPending(true)
    setError('')
    try {
      await onConfirm(reason.trim() || undefined)
      await client.invalidateQueries()
      onClose()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Something went wrong. Please try again.')
    } finally { setPending(false) }
  }
  return <Dialog open onOpenChange={open => { if (!open && !pending) onClose() }} title={title} description={description}>
    {children}
    {reasonLabel && <label className="confirm-reason"><span>{reasonLabel}</span><textarea className="input" value={reason} onChange={event => setReason(event.target.value)} rows={3} maxLength={2000} /></label>}
    <ErrorMessage message={error} />
    <div className="dialog-actions"><Button variant="outline" onClick={onClose} disabled={pending}>Cancel</Button><Button variant={destructive ? 'destructive' : 'default'} onClick={() => void submit()} disabled={pending}>{pending ? 'Working…' : confirmLabel}</Button></div>
  </Dialog>
}

/** Marks explanatory prose that was drafted with AI assistance and has not been approved. */
export function ProseNote() {
  return <p className="prose-note" role="note"><strong>Unapproved editorial prose.</strong> This explanation was drafted with AI assistance and has not been reviewed. It becomes approved only when you approve the devotion. It is not an official Church text and is not a quotation.</p>
}
