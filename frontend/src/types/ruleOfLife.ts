/** What a new entry can refer to. */
export type RuleKind = 'office_hour' | 'devotion'
/** What an existing entry may refer to: "saved_office" only on entries made before saved prayers were withdrawn (kept, shown and scheduled, never created). */
export type StoredRuleKind = RuleKind | 'saved_office'
export type RuleRecurrence = 'once' | 'daily' | 'weekly'

/** One prayer in the Rule of Life: a reference to an existing prayer and when it recurs. No prayer text lives here. */
export interface RuleEntry {
  id: string
  kind: StoredRuleKind
  ref: string
  title: string
  local_time: string
  timezone: string
  recurrence: RuleRecurrence
  weekdays: number[]
  start_date: string
  notify: boolean
  active: boolean
  link: string
  available: boolean
}

export interface RuleOccurrence {
  entry_id: string
  title: string
  kind: StoredRuleKind
  date: string
  local_time: string
  start: string
  time_zone: string
  recurrence: RuleRecurrence
  notify: boolean
  link: string
  status: 'completed' | 'skipped' | null
}

export interface RuleDraft {
  kind: RuleKind
  ref: string
  local_time: string
  timezone: string
  recurrence: RuleRecurrence
  weekdays: number[]
  start_date: string | null
  notify: boolean
}
