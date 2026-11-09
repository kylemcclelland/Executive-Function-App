import type { ReactNode } from 'react'
import { SignIn, SignUp } from '@clerk/react'
import { Feather } from 'lucide-react'
import { BrandLockup } from '../components/brand/Brand'

export function AuthFrame({ children }: { children: ReactNode }) {
  return <main className="auth-page">
    <div className="auth-column">
      <BrandLockup className="auth-lockup" />
      {children}
      <p className="auth-footnote"><Feather size={13} /> <span lang="la">Unum est necessarium.</span> One thing is necessary.</p>
    </div>
  </main>
}

export function SignInPage() {
  return <AuthFrame><SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" fallbackRedirectUrl="/" /></AuthFrame>
}

export function SignUpPage() {
  return <AuthFrame><SignUp routing="path" path="/sign-up" signInUrl="/sign-in" fallbackRedirectUrl="/" /></AuthFrame>
}

/** Shown instead of the app when the frontend has no Clerk publishable key. */
export function ClerkSetupNotice() {
  return <AuthFrame>
    <section className="card auth-notice" role="alert">
      <h1>Sign-in isn’t set up yet</h1>
      <p className="page-description">Optima Pars needs a Clerk publishable key. Copy <code>frontend/.env.example</code> to <code>frontend/.env.local</code>, set <code>VITE_CLERK_PUBLISHABLE_KEY</code>, then restart the dev server.</p>
    </section>
  </AuthFrame>
}
