import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../services/api'
import type { WorkSession } from '../types'

/** The session in progress (or null), always read from the server's stored start time. */
export function useActiveSession() {
  return useQuery({ queryKey: ['work-session-active'], queryFn: () => api<WorkSession | null>('/work-sessions/active') })
}

/** Re-renders every second; elapsed time is derived from stored timestamps, never accumulated. */
export function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}
