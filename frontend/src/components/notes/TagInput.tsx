import { useId, useRef, useState, type KeyboardEvent } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { api } from '../../services/api'
import { MAX_TAGS, normalizeTag } from '../../lib/tags'
import type { TagSuggestion } from '../../types'

const SUGGESTIONS = 8

type Option = { tag: string; count?: number; isNew?: boolean }

/**
 * Tags as removable chips, with autocomplete from every tag used on the user's notes.
 * Reuses an existing tag's spelling, never adds a tag twice (any capitalization), and lets a
 * genuinely new tag be created. The server enforces the same rules when the note is saved.
 */
export function TagInput({ value, onChange, label = 'Tags' }: { value: string[]; onChange: (tags: string[]) => void; label?: string }) {
  const id = useId()
  const listId = `${id}-suggestions`
  const input = useRef<HTMLInputElement>(null)
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const term = normalizeTag(text)
  const query = useQuery({
    queryKey: ['note-tags', term], enabled: open, retry: false, placeholderData: keepPreviousData,
    queryFn: () => api<TagSuggestion[]>(`/notes/tags?limit=${SUGGESTIONS}${term ? `&q=${encodeURIComponent(term)}` : ''}`),
  })
  const known = query.data ?? []
  const taken = new Set(value.map(tag => tag.toLowerCase()))
  const lower = term.toLowerCase()
  const options: Option[] = known.filter(item => !taken.has(item.tag.toLowerCase())).map(item => ({ tag: item.tag, count: item.count }))
  const spelledAlready = known.some(item => item.tag.toLowerCase() === lower)
  if (term && !spelledAlready && !taken.has(lower)) options.push({ tag: term, isNew: true })
  const duplicate = term !== '' && taken.has(lower)
  const full = value.length >= MAX_TAGS

  function add(raw: string, spelling?: string) {
    const tag = normalizeTag(raw)
    if (!tag) return
    const existing = spelling ?? known.find(item => item.tag.toLowerCase() === tag.toLowerCase())?.tag   // reuse the existing capitalization
    const chosen = existing ?? tag
    setText('')
    setActive(-1)
    setOpen(false)   // typing again reopens the suggestions
    if (taken.has(chosen.toLowerCase()) || full) return
    onChange([...value, chosen])
  }
  function remove(tag: string) {
    onChange(value.filter(item => item !== tag))
    input.current?.focus()
  }
  function changeText(next: string) {
    if (!next.includes(',')) { setText(next); setOpen(true); setActive(-1); return }
    const parts = next.split(',')
    const pending = parts.pop() ?? ''
    let current = value
    for (const part of parts) {
      const tag = normalizeTag(part)
      if (tag && !current.some(item => item.toLowerCase() === tag.toLowerCase()) && current.length < MAX_TAGS) current = [...current, known.find(item => item.tag.toLowerCase() === tag.toLowerCase())?.tag ?? tag]
    }
    if (current !== value) onChange(current)
    setText(pending)
    setActive(-1)
  }
  function keyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) { setOpen(true); return }
      if (options.length === 0) return
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActive(current => current === -1 ? (step === 1 ? 0 : options.length - 1) : (current + step + options.length) % options.length)
    } else if (event.key === 'Enter') {
      if (open && active >= 0 && options[active]) { event.preventDefault(); add(options[active].tag, options[active].isNew ? undefined : options[active].tag) }
      else if (term) { event.preventDefault(); add(text) }   // no option highlighted: add what was typed
    } else if (event.key === 'Escape') {
      if (open) { setOpen(false); setActive(-1) }
    } else if (event.key === 'Backspace' && text === '' && value.length > 0) {
      onChange(value.slice(0, -1))
    }
  }
  const shown = open && options.length > 0
  return <div className="tag-field">
    <label htmlFor={id}>{label}</label>
    <div className="input tag-input" onClick={() => input.current?.focus()}>
      <ul className="tag-chips" aria-label="Selected tags">{value.map(tag => <li className="tag-chip" key={tag.toLowerCase()}><span>{tag}</span><button type="button" aria-label={`Remove tag ${tag}`} onClick={event => { event.stopPropagation(); remove(tag) }}><X size={12} /></button></li>)}</ul>
      <input ref={input} id={id} role="combobox" aria-expanded={shown} aria-controls={listId} aria-autocomplete="list" aria-activedescendant={shown && active >= 0 ? `${id}-option-${active}` : undefined} autoComplete="off" value={text} disabled={full && text === ''}
        placeholder={value.length ? '' : 'Type to find or add a tag'} onChange={event => changeText(event.target.value)} onKeyDown={keyDown} onFocus={() => undefined}
        onBlur={() => { add(text); setOpen(false); setActive(-1) }} />
    </div>
    {shown && <ul id={listId} role="listbox" aria-label="Tag suggestions" className="tag-suggestions" onMouseDown={event => event.preventDefault()}>{options.map((option, index) => <li key={`${option.isNew ? 'new' : 'tag'}-${option.tag}`} id={`${id}-option-${index}`} role="option" aria-selected={index === active} className={`tag-option ${index === active ? 'is-active' : ''} ${option.isNew ? 'is-new' : ''}`} onMouseMove={() => setActive(index)} onClick={() => add(option.tag, option.isNew ? undefined : option.tag)}>
      {option.isNew ? <span>Create “{option.tag}”</span> : <><span>{option.tag}</span><small>{option.count} {option.count === 1 ? 'note' : 'notes'}</small></>}
    </li>)}</ul>}
    <p className="muted small tag-hint" aria-live="polite">{duplicate ? `“${term}” is already added.` : full ? `That’s the limit of ${MAX_TAGS} tags.` : 'Press Enter or comma to add a tag. Existing tags are suggested as you type.'}</p>
  </div>
}
