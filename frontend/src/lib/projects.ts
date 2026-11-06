import type { ProjectStatus } from '../types'

export const statusLabels: Record<ProjectStatus, string> = {
  active: 'Active', paused: 'Paused', someday: 'Someday', completed: 'Completed',
}

export const statusOrder: ProjectStatus[] = ['active', 'paused', 'someday', 'completed']

export function formatDateTime(value: string) {
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}
