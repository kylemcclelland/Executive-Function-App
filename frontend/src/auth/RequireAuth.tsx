import { useLayoutEffect, useRef, type ReactNode } from 'react'
import { RedirectToSignIn, useAuth } from '@clerk/react'
import { useQueryClient } from '@tanstack/react-query'
import { Loading } from '../components/common'
import { AuthFrame } from './AuthPages'

/** Renders the app only for a signed-in user; everyone else is sent to /sign-in and brought back. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, userId } = useAuth()
  const queryClient = useQueryClient()
  const previousUser = useRef(userId)
  // Never let one account's cached data appear for another in the same browser tab: clear the cache when a
  // signed-in account changes or signs out. Two details matter. First, going from "Clerk still loading"
  // (no user yet) to the first signed-in user is NOT a change: clearing then wipes the queries the page
  // has only just started, and they can stay on "Loading…" forever. Second, this is a layout effect so
  // the clear happens before the page's queries start fetching, not after.
  useLayoutEffect(() => {
    if (previousUser.current && previousUser.current !== userId) queryClient.clear()
    previousUser.current = userId
  }, [userId, queryClient])

  if (!isLoaded) return <AuthFrame><Loading /></AuthFrame>
  if (!isSignedIn) return <RedirectToSignIn />
  return <>{children}</>
}
