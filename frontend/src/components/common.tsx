import type { ReactNode } from 'react'
import { Feather, LoaderCircle } from 'lucide-react'
import { useAction } from '../hooks/useAction'
import { Button, Dialog } from './ui'

export function ErrorMessage({ message }: { message: string }) {
  return message ? <p className="error-message" role="alert">{message}</p> : null
}

export function Loading() {
  return <div className="loading" role="status"><LoaderCircle className="spin" size={22} /> Loading…</div>
}

export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return <div className="empty"><span className="empty-icon"><Feather size={24} /></span><h3>{title}</h3><p>{children}</p></div>
}

export function PageHeader({ eyebrow, title, children, action }: { eyebrow: string; title: string; children: ReactNode; action?: ReactNode }) {
  return <header className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-description">{children}</p></div>{action}</header>
}

export function ConfirmDelete({ title, onDelete, onClose }: { title: string; onDelete: () => Promise<unknown>; onClose: () => void }) {
  const action = useAction()
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title="Delete for good?" description={`“${title}” will be permanently deleted. This cannot be undone.`}>
    <ErrorMessage message={action.error} /><div className="dialog-actions"><Button variant="outline" onClick={onClose} disabled={action.pending}>Keep it</Button><Button variant="destructive" disabled={action.pending} onClick={() => void action.run(onDelete, onClose)}>{action.pending ? 'Deleting…' : 'Delete permanently'}</Button></div>
  </Dialog>
}
