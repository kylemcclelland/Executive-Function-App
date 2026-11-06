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
}
