import { Show, SignInButton, SignUpButton, UserButton } from '@clerk/react'

/**
 * Account controls for the sidebar. Signed in: Clerk's avatar menu (manage account, sign out;
 * signing out returns to /sign-in). Signed out: links to our own /sign-in and /sign-up pages. The
 * app shell is only rendered for signed-in users, so the signed-out branch is a safety net for
 * the moment a session ends, just before RequireAuth redirects.
 */
export function AccountControls() {
  return <div className="account-controls">
    <Show when="signed-in"><UserButton showName userProfileMode="modal" /></Show>
    <Show when="signed-out">
      <SignInButton mode="redirect"><button type="button" className="button button-outline button-small">Sign in</button></SignInButton>
      <SignUpButton mode="redirect"><button type="button" className="button button-ghost button-small">Create account</button></SignUpButton>
    </Show>
  </div>
}
