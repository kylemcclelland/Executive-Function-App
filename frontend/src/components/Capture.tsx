import { useState, type FormEvent } from 'react'
import { Check, Plus, Sparkles } from 'lucide-react'
import { api } from '../services/api'
import { useAction } from '../hooks/useAction'
import { Button, Card, Input } from './ui'
import { ErrorMessage } from './common'

export function Capture() {
  const [content, setContent] = useState('')
  const [saved, setSaved] = useState(false)
  const action = useAction()
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!content.trim()) return
    void action.run(() => api('/inbox', 'POST', { content: content.trim() }), () => { setContent(''); setSaved(true) })
  }
  return <Card className="capture-card"><div className="section-title"><span className="small-icon"><Sparkles size={18} /></span><h2>Set it down</h2></div>
    <p className="muted">A thought, a to-do, a reminder. Write it here and sort it out later.</p>
    <form onSubmit={submit} className="capture-form"><Input aria-label="Capture a thought" placeholder="What’s on your mind?" value={content} disabled={action.pending} maxLength={10000} onChange={event => { setContent(event.target.value); setSaved(false) }} />
      <Button disabled={action.pending || !content.trim()}><Plus size={17} />{action.pending ? 'Saving…' : 'Capture'}</Button></form>
    <div aria-live="polite">{saved && <p className="success-message"><Check size={14} /> Saved to your inbox. You can let it go for now.</p>}</div><ErrorMessage message={action.error} />
  </Card>
}
