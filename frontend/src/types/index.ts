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
  status: 'todo' | 'in_progress' | 'completed'
  due_date: string | null
  scheduled_date: string | null
  estimated_minutes: number | null
  next_action: string | null
  created_at: string
  updated_at: string
  completed_at: string | null
  steps: Step[]
}

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
