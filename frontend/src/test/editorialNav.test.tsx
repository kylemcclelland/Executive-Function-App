/** The owner-only Editorial sidebar entry, tested in the ACTUAL application layout (AppRoutes →
 * AppLayout → sidebar), including the real RequireAuth gate with Clerk auth loading first. */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

const clerk = vi.hoisted(() => ({
  auth: { isLoaded: true, isSignedIn: true, userId: 'user_a' as string | null | undefined },
}))

vi.mock('@clerk/react', () => ({
  useAuth: () => clerk.auth,
  RedirectToSignIn: () => <p>redirecting to sign-in</p>,
  ClerkProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SignIn: () => <p>Clerk sign-in</p>,
  SignUp: () => <p>Clerk sign-up</p>,
  Show: ({ when, children }: { when: 'signed-in' | 'signed-out'; children: React.ReactNode }) => (when === 'signed-in') === clerk.auth.isSignedIn ? <>{children}</> : null,
  UserButton: () => <button type="button">Clerk user button</button>,
  SignInButton: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  SignUpButton: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  getToken: async () => 'test-token',
}))

const { AppRoutes } = await import('../App')
const { RequireAuth } = await import('../auth/RequireAuth')

let requests: { path: string; method: string }[]
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

/** `accessResponses` answers /editorial/access call by call; the last entry repeats. */
function stubFetch(accessResponses: number[]) {
  requests = []
  let call = 0
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const path = input.replace('/api', '')
    requests.push({ path, method: options?.method ?? 'GET' })
    if (path === '/editorial/access') {
      const status = accessResponses[Math.min(call++, accessResponses.length - 1)]
      return status === 200 ? json({ owner: true }) : json({ detail: 'nope' }, status)
    }
    if (path === '/editorial/devotions') return json({ summary: { total: 0, proposed: 0 }, devotions: [] })
    if (path === '/devotions') return json([])
    if (path === '/rule-of-life') return json([])
    if (path.startsWith('/rule-of-life/occurrences')) return json([])
    return json({})
  }))
}

function openApp(accessResponses: number[], path = '/devotions', withAuthGate = false) {
  stubFetch(accessResponses)
  const client = new QueryClient({ defaultOptions: { queries: { gcTime: 0 }, mutations: { retry: false } } })
  const routes = withAuthGate ? <RequireAuth><AppRoutes /></RequireAuth> : <AppRoutes />
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>{routes}</MemoryRouter></QueryClientProvider>)
}

afterEach(() => { vi.unstubAllGlobals(); clerk.auth = { isLoaded: true, isSignedIn: true, userId: 'user_a' } })

describe('the Editorial sidebar entry in the real layout', () => {
  it('appears in the sidebar for the owner and opens the dashboard', async () => {
    openApp([200])
    const navigation = await screen.findByRole('navigation', { name: 'Main navigation' })
    const link = await within(navigation).findByRole('link', { name: /editorial/i })
    expect(link).toHaveAttribute('href', '/editorial')
    expect(within(navigation).getByRole('link', { name: 'Preferences' })).toHaveAttribute('href', '/settings')
    await userEvent.click(link)
    expect(await screen.findByRole('heading', { level: 1, name: 'Editorial Dashboard' })).toBeInTheDocument()
  })

  it('stays hidden for an ordinary user (403), with no draft data fetched and no retry', async () => {
    openApp([403])
    await screen.findByRole('heading', { level: 1, name: 'The Oratory' })
    await waitFor(() => expect(requests.some(r => r.path === '/editorial/access')).toBe(true))
    expect(screen.queryByRole('link', { name: /editorial/i })).not.toBeInTheDocument()
    const preferences = within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: 'Preferences' })
    await userEvent.click(preferences)
    expect(await screen.findByRole('heading', { level: 1, name: 'Preferences' })).toBeInTheDocument()
    expect(requests.filter(r => r.path.includes('editorial')).map(r => r.path)).toEqual(['/editorial/access'])
  })

  it('keeps the link while the owner moves between The Oratory and the Rule of Life', async () => {
    openApp([200])
    await screen.findByRole('heading', { level: 1, name: 'The Oratory' })
    const navigation = await screen.findByRole('navigation', { name: 'Main navigation' })
    await within(navigation).findByRole('link', { name: /editorial/i })
    await userEvent.click(within(navigation).getByRole('link', { name: 'Rule of Life' }))
    await screen.findByRole('heading', { level: 1, name: 'Rule of Life' })
    expect(within(navigation).getByRole('link', { name: /editorial/i })).toBeInTheDocument()
    await userEvent.click(within(navigation).getByRole('link', { name: 'The Oratory' }))
    await screen.findByRole('heading', { level: 1, name: 'The Oratory' })
    expect(within(navigation).getByRole('link', { name: /editorial/i })).toBeInTheDocument()
  })

  it('is not permanently hidden by initial authentication loading: Clerk loads, a raced 401 is retried, the link appears', async () => {
    clerk.auth = { isLoaded: false, isSignedIn: false, userId: undefined }
    const view = openApp([401, 200], '/devotions', true)
    expect(screen.queryByRole('navigation', { name: 'Main navigation' })).not.toBeInTheDocument()   // RequireAuth still waiting
    clerk.auth = { isLoaded: true, isSignedIn: true, userId: 'user_a' }
    view.rerender(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { gcTime: 0 } } })}>
      <MemoryRouter initialEntries={['/devotions']}><RequireAuth><AppRoutes /></RequireAuth></MemoryRouter></QueryClientProvider>)
    await screen.findByRole('heading', { level: 1, name: 'The Oratory' })
    expect(await screen.findByRole('link', { name: /editorial/i }, { timeout: 5000 })).toBeInTheDocument()
    expect(requests.filter(r => r.path === '/editorial/access').length).toBeGreaterThanOrEqual(2)   // the 401 was retried, not cached
  })
})
