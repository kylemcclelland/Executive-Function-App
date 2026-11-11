import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import { isoDate } from './divineOffice'
import type { RuleEntry, RuleOccurrence } from '../types/ruleOfLife'

export const WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const KIND_LABELS = { saved_office: 'Saved Office prayer (earlier entry)', office_hour: 'Divine Office hour', devotion: 'Devotion' } as const
export const kindLabel = (kind: RuleEntry['kind']) => KIND_LABELS[kind]

export const browserZone = () => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' } catch { return 'UTC' } }

export function useRuleEntries() {
  return useQuery({ queryKey: ['rule-of-life'], queryFn: () => api<RuleEntry[]>('/rule-of-life'), retry: false })
}

/** Occurrences from `start` for `days` days (local dates). */
export function useRuleOccurrences(start: Date, days: number, enabled = true) {
  const from = isoDate(start)
  const to = isoDate(new Date(start.getFullYear(), start.getMonth(), start.getDate() + days - 1))
  return useQuery({ queryKey: ['rule-of-life-occurrences', from, to], queryFn: () => api<RuleOccurrence[]>(`/rule-of-life/occurrences?start=${from}&end=${to}`), enabled, retry: false })
}

export function describeRecurrence(entry: Pick<RuleEntry, 'recurrence' | 'weekdays' | 'start_date'>) {
  if (entry.recurrence === 'once') return `Once, ${entry.start_date}`
  if (entry.recurrence === 'daily') return 'Every day'
  return entry.weekdays.map(day => WEEKDAY_NAMES[day].slice(0, 3)).join(', ')
}

/** 24-hour "HH:MM" as the reader's locale writes a clock time. */
export function clockLabel(hhmm: string) {
  const [hour, minute] = hhmm.split(':').map(Number)
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(2000, 0, 1, hour, minute))
}

/** The place to open an entry today; an Office hour is always opened for the date asked, so its texts are those of that day. */
export function entryLink(entry: Pick<RuleEntry, 'kind' | 'ref' | 'link'>, date = isoDate(new Date())) {
  return entry.kind === 'office_hour' ? `/divine-office?date=${date}&hour=${entry.ref}` : entry.link
}

/** Marks an occurrence completed or skipped (or clears the mark); nothing else is tracked. */
export function useMarkOccurrence() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, date, status }: { entryId: string; date: string; status: 'completed' | 'skipped' | null }) =>
      status ? api(`/rule-of-life/${entryId}/occurrences/${date}`, 'PUT', { status }) : api(`/rule-of-life/${entryId}/occurrences/${date}`, 'DELETE'),
    onSuccess: () => client.invalidateQueries({ queryKey: ['rule-of-life-occurrences'] }),
  })
}
