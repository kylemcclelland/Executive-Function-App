import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { api, apiUpload, setTokenSource } from '../services/api'

const clerk = vi.hoisted(() => ({
  auth: { isLoaded: true, isSignedIn: true, userId: 'user_a' as string | null | undefined },
}))

vi.mock('@clerk/react', () => ({
  useAuth: () => clerk.auth,
  RedirectToSignIn: () => <p>redirecting to sign-in</p>,
  ClerkProvider: ({ children, afterSignOutUrl, signInUrl, signUpUrl }: { children: React.ReactNode; afterSignOutUrl: string; signInUrl: string; signUpUrl: string }) =>
    <div data-testid="clerk-provider" data-after-sign-out={afterSignOutUrl} data-sign-in={signInUrl} data-sign-up={signUpUrl}>{children}</div>,
  SignIn: (props: { path: string; signUpUrl: string }) => <p>Clerk sign-in at {props.path} (sign-up {props.signUpUrl})</p>,
  SignUp: (props: { path: string; signInUrl: string }) => <p>Clerk sign-up at {props.path} (sign-in {props.signInUrl})</p>,
  Show: ({ when, children }: { when: 'signed-in' | 'signed-out'; children: React.ReactNode }) => (when === 'signed-in') === clerk.auth.isSignedIn ? <>{children}</> : null,
  UserButton: (props: { showName?: boolean; userProfileMode?: string }) => <button type="button">Clerk user button{props.showName ? ' with name' : ''} ({props.userProfileMode})</button>,
  SignInButton: ({ children, mode }: { children: React.ReactNode; mode?: string }) => <span data-mode={mode}>{children}</span>,
  SignUpButton: ({ children, mode }: { children: React.ReactNode; mode?: string }) => <span data-mode={mode}>{children}</span>,
  getToken: async () => 'unused',
}))

// Imported after the mock so the app picks up the fake Clerk.
const { default: App } = await import('../App')
const { ClerkRoot } = await import('../auth/ClerkRoot')
const { RequireAuth } = await import('../auth/RequireAuth')
const { AccountControls } = await import('../auth/AccountControls')

let queryClient: QueryClient
const renderAt = (path: string, ui: React.ReactNode) => render(
  <QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter></QueryClientProvider>,
)

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clerk.auth = { isLoaded: true, isSignedIn: true, userId: 'user_a' }
})
afterEach(() => { setTokenSource(null); vi.restoreAllMocks() })

describe('route protection', () => {
  it('shows a loading state until Clerk has loaded', () => {
    clerk.auth = { isLoaded: false, isSignedIn: false, userId: undefined }
    renderAt('/', <RequireAuth><p>private study</p></RequireAuth>)
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByText('private study')).not.toBeInTheDocument()
  })

  it('sends a signed-out visitor to sign in without rendering the app', () => {
    clerk.auth = { isLoaded: true, isSignedIn: false, userId: null }
    renderAt('/tasks', <RequireAuth><p>private study</p></RequireAuth>)
    expect(screen.getByText('redirecting to sign-in')).toBeInTheDocument()
    expect(screen.queryByText('private study')).not.toBeInTheDocument()
  })

  it('renders the app for a signed-in user', () => {
    renderAt('/', <RequireAuth><p>private study</p></RequireAuth>)
    expect(screen.getByText('private study')).toBeInTheDocument()
  })

  it('discards cached data when the signed-in account changes', () => {
    queryClient.setQueryData(['tasks'], ['alice private task'])
    const { rerender } = renderAt('/', <RequireAuth><p>private study</p></RequireAuth>)
    expect(queryClient.getQueryData(['tasks'])).toEqual(['alice private task'])
    clerk.auth = { isLoaded: true, isSignedIn: true, userId: 'user_b' }
    rerender(<QueryClientProvider client={queryClient}><MemoryRouter><RequireAuth><p>private study</p></RequireAuth></MemoryRouter></QueryClientProvider>)
    expect(queryClient.getQueryData(['tasks'])).toBeUndefined()
  })

  it('discards cached data on sign-out', () => {
    queryClient.setQueryData(['tasks'], ['alice private task'])
    const { rerender } = renderAt('/', <RequireAuth><p>private study</p></RequireAuth>)
    clerk.auth = { isLoaded: true, isSignedIn: false, userId: null }
    rerender(<QueryClientProvider client={queryClient}><MemoryRouter><RequireAuth><p>private study</p></RequireAuth></MemoryRouter></QueryClientProvider>)
    expect(queryClient.getQueryData(['tasks'])).toBeUndefined()
  })
})

describe('App', () => {
  const renderApp = (path: string) => render(<MemoryRouter initialEntries={[path]}><ClerkRoot clerkKey="pk_test_x"><App /></ClerkRoot></MemoryRouter>)

  it('serves the Clerk sign-in and sign-up pages to signed-out visitors', () => {
    clerk.auth = { isLoaded: true, isSignedIn: false, userId: null }
    const signIn = renderApp('/sign-in')
    expect(screen.getByText(/Clerk sign-in at \/sign-in/)).toBeInTheDocument()
    signIn.unmount()
    renderApp('/sign-up')
    expect(screen.getByText(/Clerk sign-up at \/sign-up/)).toBeInTheDocument()
  })

  it('sends a signed-out visitor to sign in from every application route', () => {
    clerk.auth = { isLoaded: true, isSignedIn: false, userId: null }
    for (const path of ['/', '/inbox', '/tasks', '/projects', '/library', '/notes', '/settings']) {
      const { unmount } = renderApp(path)
      expect(screen.getByText('redirecting to sign-in'), path).toBeInTheDocument()
      expect(screen.queryByRole('navigation', { name: 'Main navigation' }), path).not.toBeInTheDocument()
      unmount()
    }
  })
})

describe('ClerkRoot', () => {
  it('provides Clerk once around the whole app', () => {
    render(<MemoryRouter><ClerkRoot clerkKey="pk_test_x"><p>app</p></ClerkRoot></MemoryRouter>)
    expect(screen.getAllByTestId('clerk-provider')).toHaveLength(1)
    expect(screen.getByText('app')).toBeInTheDocument()
  })

  it('explains the missing publishable key instead of crashing', () => {
    render(<MemoryRouter><ClerkRoot clerkKey=""><p>app</p></ClerkRoot></MemoryRouter>)
    expect(screen.getByRole('alert')).toHaveTextContent('VITE_CLERK_PUBLISHABLE_KEY')
    expect(screen.queryByTestId('clerk-provider')).not.toBeInTheDocument()
    expect(screen.queryByText('app')).not.toBeInTheDocument()
  })
})

describe('account controls', () => {
  it('shows Clerk’s user button, and no sign-in links, to a signed-in user', () => {
    renderAt('/', <AccountControls />)
    expect(screen.getByRole('button', { name: 'Clerk user button with name (modal)' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create account' })).not.toBeInTheDocument()
  })

  it('offers sign-in and sign-up on our own pages when signed out', () => {
    clerk.auth = { isLoaded: true, isSignedIn: false, userId: null }
    renderAt('/', <AccountControls />)
    expect(screen.getByRole('button', { name: 'Sign in' }).parentElement).toHaveAttribute('data-mode', 'redirect')
    expect(screen.getByRole('button', { name: 'Create account' }).parentElement).toHaveAttribute('data-mode', 'redirect')
    expect(screen.queryByText(/Clerk user button/)).not.toBeInTheDocument()
  })

  it('sends sign-in, sign-up and sign-out to the app’s own pages', () => {
    render(<MemoryRouter><ClerkRoot clerkKey="pk_test_x"><p>app</p></ClerkRoot></MemoryRouter>)
    const provider = screen.getByTestId('clerk-provider')
    expect(provider).toHaveAttribute('data-after-sign-out', '/sign-in')
    expect(provider).toHaveAttribute('data-sign-in', '/sign-in')
    expect(provider).toHaveAttribute('data-sign-up', '/sign-up')
  })
})

describe('API requests', () => {
  const respond = () => vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }))

  it('sends the Clerk session token as a bearer credential', async () => {
    const fetchMock = respond()
    setTokenSource(async () => 'session-token')
    await api('/tasks')
    await api('/tasks', 'POST', { title: 'x' })
    await apiUpload('/books/import/preview', new File(['a'], 'a.csv'))
    for (const [, init] of fetchMock.mock.calls) {
      expect((init!.headers as Record<string, string>).Authorization).toBe('Bearer session-token')
    }
    expect((fetchMock.mock.calls[1][1]!.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('sends no credential when signed out', async () => {
    const fetchMock = respond()
    setTokenSource(async () => null)
    await api('/tasks')
    expect(fetchMock.mock.calls[0][1]!.headers).not.toHaveProperty('Authorization')
  })

  it('never puts the token in the URL or body', async () => {
    const fetchMock = respond()
    setTokenSource(async () => 'session-token')
    await api('/tasks', 'POST', { title: 'x' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).not.toContain('session-token')
    expect(String(init!.body)).not.toContain('session-token')
  })
})
