import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InstallCard } from '../pages/SettingsPage'

function mockDisplayMode(standalone: boolean) {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: standalone && query === '(display-mode: standalone)',
    media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })))
}

class FakeInstallPrompt extends Event {
  prompted = false
  outcome: 'accepted' | 'dismissed' = 'accepted'
  prompt = () => { this.prompted = true; return Promise.resolve() }
  get userChoice() { return Promise.resolve({ outcome: this.outcome }) }
  constructor() { super('beforeinstallprompt', { cancelable: true }) }
}

beforeEach(() => mockDisplayMode(false))
afterEach(() => vi.unstubAllGlobals())

describe('Install Optima Pars', () => {
  it('shows a real install button only after the browser offers installation, and invokes it', async () => {
    const user = userEvent.setup()
    render(<InstallCard />)
    expect(screen.queryByRole('button', { name: 'Install Optima Pars' })).not.toBeInTheDocument()
    const offer = new FakeInstallPrompt()
    fireEvent(window, offer)
    expect(offer.defaultPrevented).toBe(true)        // never auto-prompts
    await user.click(await screen.findByRole('button', { name: 'Install Optima Pars' }))
    expect(offer.prompted).toBe(true)
  })

  it('respects a declined prompt: the option stays available without re-prompting by itself', async () => {
    const user = userEvent.setup()
    render(<InstallCard />)
    const offer = new FakeInstallPrompt()
    offer.outcome = 'dismissed'
    fireEvent(window, offer)
    await user.click(await screen.findByRole('button', { name: 'Install Optima Pars' }))
    expect(offer.prompted).toBe(true)
    expect(screen.getByRole('button', { name: 'Install Optima Pars' })).toBeInTheDocument()
  })

  it('hides itself completely inside the installed app', () => {
    mockDisplayMode(true)
    const { container } = render(<InstallCard />)
    expect(container).toBeEmptyDOMElement()
  })

  it('hides itself in iOS standalone mode', () => {
    vi.stubGlobal('navigator', { ...window.navigator, standalone: true, userAgent: 'iPhone', maxTouchPoints: 5 })
    const { container } = render(<InstallCard />)
    expect(container).toBeEmptyDOMElement()
  })

  it('gives iPhone and iPad the Share → Add to Home Screen guidance instead of a dead button', () => {
    vi.stubGlobal('navigator', { ...window.navigator, standalone: false, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)', maxTouchPoints: 5 })
    render(<InstallCard />)
    expect(screen.getByText('Add to Home Screen')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Install Optima Pars' })).not.toBeInTheDocument()
  })

  it('explains quietly in browsers that never offer the prompt', () => {
    render(<InstallCard />)
    expect(screen.getByText(/hasn.t offered installation/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Install Optima Pars' })).not.toBeInTheDocument()
  })

  it('disappears the moment the app is installed from this window', async () => {
    render(<InstallCard />)
    fireEvent(window, new FakeInstallPrompt())
    await screen.findByRole('button', { name: 'Install Optima Pars' })
    mockDisplayMode(true)                             // the browser flips the display mode
    fireEvent(window, new Event('appinstalled'))
    expect(screen.queryByRole('button', { name: 'Install Optima Pars' })).not.toBeInTheDocument()
  })
})
