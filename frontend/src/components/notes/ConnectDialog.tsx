import { useState, type FormEvent } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../../services/api'
import { useAction } from '../../hooks/useAction'
import { linkTypes, noteTypeLabel } from '../../lib/notes'
import type { Connection, LinkType, NoteBrief } from '../../types'
import { Button, Dialog, Input } from '../ui'
import { Empty, ErrorMessage, Loading } from '../common'

/** What the chosen relationship says, so a directional link can't be misread. */
function sentence(from: string, to: string, type: LinkType) {
  const info = linkTypes.find(item => item.value === type)!
  const mutual: Partial<Record<LinkType, string>> = { related_to: 'are related to one another', contradicts: 'contradict one another' }
  return info.symmetric ? `“${from}” and “${to}” ${mutual[type]}. This reads the same from both notes.` : `“${from}” ${info.outgoing.toLowerCase()} “${to}”. This does not say the reverse.`
}

export function ConnectDialog({ note, connections, onClose }: { note: NoteBrief; connections: Connection[]; onClose: () => void }) {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<NoteBrief | null>(null)
  const [linkType, setLinkType] = useState<LinkType>('related_to')
  const [explanation, setExplanation] = useState('')
  const action = useAction()
  const term = search.trim()
  const results = useQuery({ queryKey: ['note-search', term], queryFn: () => api<NoteBrief[]>(`/notes?limit=20${term ? `&q=${encodeURIComponent(term)}` : ''}`), placeholderData: keepPreviousData })
  const candidates = results.data?.filter(item => item.id !== note.id) ?? []
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    void action.run(() => api(`/notes/${note.id}/connections`, 'POST', { target_note_id: selected.id, link_type: linkType, explanation: explanation.trim() || null }), onClose)
  }
  const alreadyConnected = selected ? connections.some(item => item.note.id === selected.id && item.link_type === linkType && (item.direction !== 'incoming' || linkTypes.find(t => t.value === linkType)?.symmetric)) : false
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title="Connect an idea" description={`Link “${note.title}” to another note you have written.`}>
    <form onSubmit={submit} className="connect-form">
      {!selected ? <>
        <label>Search your notes<Input autoFocus value={search} onChange={e => setSearch(e.target.value)} placeholder="Title, text, source or tag" /></label>
        <div className="connect-results" role="group" aria-label="Notes to connect">
          {results.isPending ? <Loading /> : results.isError ? <ErrorMessage message={results.error.message} /> : candidates.length ? candidates.map(item => <button type="button" key={item.id} className="task-choice" onClick={() => setSelected(item)}><span><strong>{item.title}</strong><small>{noteTypeLabel(item.note_type)}{item.book_title ? ` · ${item.book_title}` : ''}</small></span></button>) : <Empty title={term ? 'No notes match' : 'No other notes yet'}>{term ? 'Try another word.' : 'Write another note first, then connect them.'}</Empty>}
        </div>
      </> : <>
        <p className="connect-selected"><span className="muted small">Connecting to</span><strong>{selected.title}</strong><Button type="button" size="sm" variant="ghost" onClick={() => setSelected(null)}>Choose a different note</Button></p>
        <label>Relationship<select className="input" value={linkType} onChange={e => setLinkType(e.target.value as LinkType)}>{linkTypes.map(type => <option key={type.value} value={type.value}>{type.outgoing}</option>)}</select></label>
        <p className="muted connect-sentence">{sentence(note.title, selected.title, linkType)}</p>
        <label>Why are they connected? (optional)<textarea className="input" rows={3} maxLength={5000} value={explanation} onChange={e => setExplanation(e.target.value)} /></label>
        {alreadyConnected && <p className="muted">These notes are already connected this way.</p>}
      </>}
      <ErrorMessage message={action.error} />
      <div className="dialog-actions"><Button variant="outline" type="button" onClick={onClose} disabled={action.pending}>Cancel</Button><Button disabled={!selected || action.pending || alreadyConnected}>{action.pending ? 'Saving…' : 'Save connection'}</Button></div>
    </form>
  </Dialog>
}

export function RemoveConnectionDialog({ label, title, linkId, onClose }: { label: string; title: string; linkId: string; onClose: () => void }) {
  const action = useAction()
  return <Dialog open onOpenChange={open => { if (!open && !action.pending) onClose() }} title="Remove this connection?" description={`“${label} ${title}” will be removed. Neither note is changed or deleted.`}>
    <ErrorMessage message={action.error} />
    <div className="dialog-actions"><Button variant="outline" onClick={onClose} disabled={action.pending}>Keep it</Button><Button variant="destructive" disabled={action.pending} onClick={() => void action.run(() => api(`/note-links/${linkId}`, 'DELETE'), onClose)}>{action.pending ? 'Removing…' : 'Remove connection'}</Button></div>
  </Dialog>
}
