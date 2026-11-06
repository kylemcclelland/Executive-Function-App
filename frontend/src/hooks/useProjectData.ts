import { useQuery } from '@tanstack/react-query'
import { api } from '../services/api'
import type { Milestone, Task } from '../types'

export function useProjectTasks(projectId: string) {
  return useQuery({ queryKey: ['project-tasks', projectId], queryFn: () => api<Task[]>(`/projects/${projectId}/tasks`) })
}

export function useProjectMilestones(projectId: string) {
  return useQuery({ queryKey: ['project-milestones', projectId], queryFn: () => api<Milestone[]>(`/projects/${projectId}/milestones`) })
}
