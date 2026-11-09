import { useEffect, useRef, type ReactNode } from 'react'
import { RedirectToSignIn, useAuth } from '@clerk/react'
import { useQueryClient } from '@tanstack/react-query'
import { Loading } from '../components/common'
import { AuthFrame } from './AuthPages'

/** Renders the app only for a signed-in user; everyone else is sent to /sign-in and brought back. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, userId } = useAuth()
  const queryClient = useQueryClient()
  const previousUser = useRef(userId)
  useEffect(() => {
    // Never let one account's cached data appear for another in the same browser tab.
    if (previousUser.current !== userId) queryClient.clear()
    previousUser.current = userId
  }, [userId, queryClient])

  if (!isLoaded) return <AuthFrame><Loading /></AuthFrame>
  if (!isSignedIn) return <RedirectToSignIn />
  return <>{children}</>
}
