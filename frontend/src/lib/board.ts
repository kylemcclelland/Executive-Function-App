import type { TaskStatus } from '../types'

/** The board's five columns, in working order. Done maps to the one existing 'completed' status. */
export const COLUMNS: { status: TaskStatus; label: string }[] = [
  { status: 'todo', label: 'To Do' },
  { status: 'in_progress', label: 'In Progress' },
  { status: 'in_review', label: 'In Review' },
  { status: 'blocked', label: 'Blocked' },
  { status: 'completed', label: 'Done' },
]

export const STATUS_LABELS = Object.fromEntries(COLUMNS.map(c => [c.status, c.label])) as Record<TaskStatus, string>
