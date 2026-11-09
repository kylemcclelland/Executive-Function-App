import type { ReactNode } from 'react'
import { ClerkProvider } from '@clerk/react'
import { useNavigate } from 'react-router-dom'
import { clerkAppearanceFor } from './appearance'
import { useTheme } from '../theme/theme'
import { ClerkSetupNotice } from './AuthPages'

const publishableKey: string | undefined = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY || undefined

/**
 * The single ClerkProvider, wrapping the whole app from main.tsx. It sits inside the router so Clerk
 * navigates with it: sign-in, sign-up and sign-out never reload the page.
 */
export function ClerkRoot({ children, clerkKey = publishableKey }: { children: ReactNode; clerkKey?: string }) {
  const navigate = useNavigate()
  const { resolved } = useTheme()
  if (!clerkKey) return <ClerkSetupNotice />
  return <ClerkProvider publishableKey={clerkKey} appearance={clerkAppearanceFor(resolved)}
    routerPush={to => navigate(to)} routerReplace={to => navigate(to, { replace: true })}
    signInUrl="/sign-in" signUpUrl="/sign-up" signInFallbackRedirectUrl="/" signUpFallbackRedirectUrl="/" afterSignOutUrl="/sign-in">
    {children}
  </ClerkProvider>
}
