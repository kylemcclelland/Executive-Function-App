export interface Step {
  id: string
  task_id: string
  title: string
  position: number
  is_completed: boolean
}

export interface Task {
  id: string
  user_id: string
  project_id: string | null
  project_name: string | null
  milestone_id: string | null
  project_position: number | null
  title: string
  description: string | null
  status: TaskStatus
  task_kind: 'checklist' | 'board'
  due_date: string | null
  scheduled_date: string | null
  estimated_minutes: number | null
  next_action: string | null
  previous_status: TaskStatus | null
  blocked_reason: string | null
  waiting_on: string | null
  blocked_follow_up: string | null
  review_notes: string | null
  reviewer_name: string | null
  review_requested_at: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
  steps: Step[]
}

export type TaskStatus = 'todo' | 'in_progress' | 'in_review' | 'blocked' | 'completed'

export interface InboxItem {
  id: string
  content: string
  status: 'unprocessed' | 'processed' | 'archived'
  converted_task_id: string | null
  created_at: string
  updated_at: string
}

export interface TodayData {
  date: string
  timezone: string
  priorities: Task[]
  previous_tasks: Task[]
  completed_tasks: Task[]
  inbox_count: number
  active_projects?: ProjectBrief[]
}

export type ProjectStatus = 'active' | 'paused' | 'someday' | 'completed'

export interface ProjectBrief {
  id: string
  name: string
  next_action: string | null
  next_task_title: string | null
  open_task_count: number
}

export interface Project {
  id: string
  name: string
  description: string | null
  category: string | null
  status: ProjectStatus
  target_date: string | null
  next_action: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
  archived_at: string | null
  open_task_count: number
  completed_task_count: number
  milestone_count: number
  milestones_completed: number
  next_task_title: string | null
}

export interface ProjectUpdate {
  id: string
  project_id: string
  kind: 'progress' | 'session'
  summary: string
  next_step: string | null
  created_at: string
}

export interface ProjectDetail extends Project {
  last_update: ProjectUpdate | null
  last_session?: WorkSession | null
  resume_session?: WorkSession | null
}

export interface Milestone {
  id: string
  project_id: string
  title: string
  description: string | null
  target_date: string | null
  position: number
  completed_at: string | null
  task_count: number
  completed_task_count: number
}

export interface ProjectNote {
  id: string
  project_id: string
  title: string | null
  content: string
  created_at: string
  updated_at: string
}

export interface HistoryEntry {
  id: string
  type: 'task_completed' | 'milestone_completed' | 'progress' | 'session'
  at: string
  title: string
  next_step: string | null
}

export interface WorkSession {
  id: string
  project_id: string
  project_name: string
  task_id: string | null
  task_title: string | null
  intention: string
  status: 'active' | 'finished' | 'interrupted'
  started_at: string
  ended_at: string | null
  planned_minutes: number | null
  elapsed_seconds: number | null
  accomplished: string | null
  resume_note: string | null
}

export interface TagSuggestion {
  tag: string
  count: number
}

export type NoteType = 'general' | 'reading_note' | 'quotation' | 'reflection' | 'research' | 'question'
export type LinkType = 'related_to' | 'supports' | 'contradicts' | 'develops' | 'responds_to'

export interface Book {
  id: string
  title: string
  authors: string[]
  isbn_10: string | null
  isbn_13: string | null
  publication_year: number | null
  publisher: string | null
  edition: string | null
  cover_url: string | null
  goodreads_id: string | null
  description: string | null
  created_at: string
  updated_at: string
  note_count: number
}

export interface NoteBrief {
  id: string
  title: string
  note_type: NoteType
  book_id: string | null
  book_title: string | null
  project_id: string | null
  project_name: string | null
  source_location: string | null
  tags: string[]
  excerpt: string
  updated_at: string
}

export interface LibraryNote extends NoteBrief {
  content: string
  former_book: string | null
  created_at: string
}

export interface Connection {
  id: string
  link_type: LinkType
  direction: 'outgoing' | 'incoming' | 'mutual'
  explanation: string | null
  created_at: string
  note: NoteBrief
}

export interface ImportCounts {
  total_rows: number
  to_add: number
  matched: number
  to_update: number
  duplicates: number
  ambiguous: number
  invalid: number
}

export interface ImportProblem {
  row: number
  title: string | null
  kind: 'invalid' | 'duplicate' | 'ambiguous' | 'warning'
  message: string
}

export interface ImportPreview {
  token: string
  expires_in_seconds: number
  counts: ImportCounts
  warnings: string[]
  problems: ImportProblem[]
  sample_new: { title: string; authors: string[]; year: number | null; goodreads_id: string | null }[]
  sample_matched: { title: string; book_id: string; reason: 'goodreads_id' | 'isbn' | 'title_author'; fills: string[] }[]
}

export interface ImportResult {
  summary: { added: number; matched: number; updated: number; skipped: number; duplicates: number; ambiguous: number; invalid: number }
  problems: ImportProblem[]
  books: { id: string; title: string; action: 'added' | 'updated' | 'matched' }[]
}

export type CoverCooldownReason = 'rate_limited' | 'unavailable'

export interface CoverBatch {
  checked: number
  found: number
  not_found: number
  errors: number
  cached: number
  converted: number
  rate_limited: boolean
  unavailable: boolean
  stopped_early: boolean
  blocked_until: string | null
  retry_after_seconds: number | null
  cooldown_reason: CoverCooldownReason | null
  checked_ids: string[]
  remaining: number
  legacy_remaining: number
}

export interface CoverStatus {
  count: number
  with_covers: number
  found_lookups: number
  not_found_lookups: number
  blocked_until: string | null
  retry_after_seconds: number | null
  cooldown_reason: CoverCooldownReason | null
}

export interface CoverAutoJob {
  exists: boolean
  status: 'running' | 'paused' | 'done' | null
  waiting: boolean
  books_checked: number
  covers_found: number
  without_cover: number
  errors: number
  remaining: number | null
  next_run_at: string | null
  last_progress_at: string | null
  last_error: string | null
}

export type BookSort = 'title' | 'title_desc' | 'recent' | 'year_desc' | 'year_asc'

export interface BookPage {
  items: Book[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface CalendarStatus {
  configured: boolean
  status: 'not_connected' | 'active' | 'needs_reauth'
  account_email: string | null
  connected_at: string | null
  last_successful_sync_at: string | null
}

export interface CalendarEvent {
  id: string
  title: string
  all_day: boolean
  start: string | null
  end: string | null
  time_zone: string | null
  start_date: string | null
  end_date: string | null
  location: string | null
  html_link: string | null
  recurring: boolean
}

export interface CalendarEventsPage {
  events: CalendarEvent[]
  next_page_token: string | null
  time_min: string
  time_max: string
}
