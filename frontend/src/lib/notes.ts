import type { Connection, LinkType, NoteType } from '../types'

export const noteTypes: { value: NoteType; label: string; hint: string }[] = [
  { value: 'general', label: 'General', hint: 'Anything else worth keeping.' },
  { value: 'reading_note', label: 'Reading Note', hint: 'Your summary or paraphrase of an author’s argument.' },
  { value: 'quotation', label: 'Quotation', hint: 'The author’s exact words, attributed to a source.' },
  { value: 'reflection', label: 'Reflection', hint: 'Your own analysis or response.' },
  { value: 'research', label: 'Research', hint: 'Material collected for further inquiry.' },
  { value: 'question', label: 'Question', hint: 'Something you want to investigate.' },
]

export const noteTypeLabel = (value: NoteType) => noteTypes.find(type => type.value === value)?.label ?? value

// Related to and Contradicts are mutual. The others have a direction: "A develops B" is not "B develops A".
export const linkTypes: { value: LinkType; outgoing: string; incoming: string; symmetric: boolean }[] = [
  { value: 'related_to', outgoing: 'Related to', incoming: 'Related to', symmetric: true },
  { value: 'supports', outgoing: 'Supports', incoming: 'Supported by', symmetric: false },
  { value: 'contradicts', outgoing: 'Contradicts', incoming: 'Contradicts', symmetric: true },
  { value: 'develops', outgoing: 'Develops', incoming: 'Developed by', symmetric: false },
  { value: 'responds_to', outgoing: 'Responds to', incoming: 'Responded to by', symmetric: false },
]

export function connectionLabel(connection: Pick<Connection, 'link_type' | 'direction'>) {
  const type = linkTypes.find(item => item.value === connection.link_type)
  if (!type) return connection.link_type
  return connection.direction === 'incoming' ? type.incoming : type.outgoing
}

export const authorLine = (authors: string[]) => authors.join(', ')

export const isHttpUrl = (value: string | null): value is string => !!value && /^https?:\/\//i.test(value)
