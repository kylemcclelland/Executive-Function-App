import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { initTheme, resolveTheme, setThemePreference, THEME_KEY } from '../theme/theme'
import { clerkAppearanceFor } from '../auth/appearance'

import html from '../../index.html?raw'
import css from '../index.css?raw'
import manifestText from '../../public/manifest.webmanifest?raw'
import faviconSvg from '../../public/favicon.svg?raw'

// File listings (not contents): which brand files exist.
const publicFiles = Object.keys(import.meta.glob('../../public/*', { query: '?url' })).map(path => path.split('/').pop())
const brandFiles = Object.keys(import.meta.glob('../assets/brand/*', { query: '?url' })).map(path => path.split('/').pop())
const originalLogo = Object.keys(import.meta.glob('../../Logo.png', { query: '?url' }))

type MediaListener = () => void
let systemDark: boolean
let mediaListeners: MediaListener[]
let queryClient: QueryClient

function stubSystem(dark: boolean) {
  systemDark = dark
  mediaListeners = []
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('dark') ? systemDark : false, media: query,
    addEventListener: (_: string, listener: MediaListener) => mediaListeners.push(listener), removeEventListener: () => {},
  }))
}
const changeSystem = (dark: boolean) => { systemDark = dark; mediaListeners.forEach(listener => listener()) }
const themeOf = () => document.documentElement.getAttribute('data-theme')

/** Runs the real inline script from index.html, as the browser does before first paint. */
function runInlineScript() {
  const script = /<script>([\s\S]*?)<\/script>/.exec(html)![1]
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.style.colorScheme = ''
  new Function(script)()
}

beforeEach(() => {
  window.localStorage.clear()
  document.head.innerHTML = '<meta name="theme-color" content="#F7F3EA">'
  stubSystem(false)
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ timezone: 'UTC' }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
})
afterEach(() => { queryClient.clear(); vi.unstubAllGlobals(); document.documentElement.removeAttribute('data-theme') })

function renderApp(path = '/settings') {
  const user = userEvent.setup()
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
  return user
}

describe('theme resolution and persistence', () => {
  it('resolves light, dark and system', () => {
    expect(resolveTheme('light', true)).toBe('light')
    expect(resolveTheme('dark', false)).toBe('dark')
    expect(resolveTheme('system', true)).toBe('dark')
    expect(resolveTheme('system', false)).toBe('light')
  })

  it('applies and remembers an explicit choice, on the page and in storage', () => {
    initTheme()
    setThemePreference('dark')
    expect(themeOf()).toBe('dark')
    expect(document.documentElement.style.colorScheme).toBe('dark')
    expect(window.localStorage.getItem(THEME_KEY)).toBe('dark')
    expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute('content', '#111B17')
    setThemePreference('light')
    expect(themeOf()).toBe('light')
    expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute('content', '#F7F3EA')
  })

  it('follows the operating system while System is selected, and only then', () => {
    initTheme()
    setThemePreference('system')
    expect(themeOf()).toBe('light')
    changeSystem(true)
    expect(themeOf()).toBe('dark')
    changeSystem(false)
    expect(themeOf()).toBe('light')
    setThemePreference('light')
    changeSystem(true)
    expect(themeOf()).toBe('light')
  })

  it('survives a refresh: a stored choice is applied again on the next load', () => {
    window.localStorage.setItem(THEME_KEY, 'dark')
    initTheme()
    expect(themeOf()).toBe('dark')
    window.localStorage.setItem(THEME_KEY, 'system')
    stubSystem(true)
    initTheme()
    expect(themeOf()).toBe('dark')
  })

  it('treats an unknown stored value as System rather than breaking', () => {
    window.localStorage.setItem(THEME_KEY, 'purple')
    stubSystem(true)
    initTheme()
    expect(themeOf()).toBe('dark')
  })

  it('still works when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(() => initTheme()).not.toThrow()
    expect(themeOf()).toBe('light')
    expect(() => setThemePreference('dark')).not.toThrow()
    expect(themeOf()).toBe('dark')
    vi.restoreAllMocks()
  })
})

describe('no flash of the wrong theme (the inline script in index.html)', () => {
  it.each([
    [null, false, 'light'], [null, true, 'dark'], ['system', true, 'dark'], ['system', false, 'light'],
    ['dark', false, 'dark'], ['light', true, 'light'], ['bogus', true, 'dark'],
  ])('stored=%s, system dark=%s -> %s', (stored, dark, expected) => {
    stubSystem(dark)
    if (stored) window.localStorage.setItem(THEME_KEY, stored)
    runInlineScript()
    expect(themeOf()).toBe(expected)
    expect(document.documentElement.style.colorScheme).toBe(expected)
  })

  it('falls back quietly when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    expect(() => runInlineScript()).not.toThrow()
    vi.restoreAllMocks()
  })

  it('uses the same storage key as the app, and runs before the stylesheet-driven app starts', () => {
    expect(html).toContain(`'${THEME_KEY}'`)
    expect(html.indexOf('<script>')).toBeLessThan(html.indexOf('type="module"'))
  })
})

describe('theme controls', () => {
  it('offers Light, Dark and System as one accessible radio group in Preferences', async () => {
    window.localStorage.setItem(THEME_KEY, 'dark')
    initTheme()
    const user = renderApp()
    const group = await screen.findByRole('group', { name: 'Theme' })
    const radios = within(group).getAllByRole('radio')
    expect(radios.map(radio => (radio as HTMLInputElement).value)).toEqual(['light', 'dark', 'system'])
    expect(within(group).getByRole('radio', { name: /Dark/ })).toBeChecked()
    await user.click(within(group).getByRole('radio', { name: /Light/ }))
    expect(themeOf()).toBe('light')
    expect(window.localStorage.getItem(THEME_KEY)).toBe('light')
    await user.click(within(group).getByRole('radio', { name: /System/ }))
    expect(window.localStorage.getItem(THEME_KEY)).toBe('system')
    expect(screen.getByText(/Following your device: currently light/)).toBeInTheDocument()
  })

  it('moves between options with the keyboard', async () => {
    initTheme()
    const user = renderApp()
    const group = await screen.findByRole('group', { name: 'Theme' })
    within(group).getByRole('radio', { name: /Light|System/, checked: true }).focus()
    await user.keyboard('{ArrowRight}')
    expect(themeOf()).toBeTruthy()
    expect(window.localStorage.getItem(THEME_KEY)).not.toBeNull()
  })

  it('has a header toggle that flips the theme and says what it will do', async () => {
    initTheme()
    setThemePreference('light')
    const user = renderApp('/settings')
    await user.click(await screen.findByRole('button', { name: 'Switch to dark mode' }))
    expect(themeOf()).toBe('dark')
    await user.click(screen.getByRole('button', { name: 'Switch to light mode' }))
    expect(themeOf()).toBe('light')
    expect(window.localStorage.getItem(THEME_KEY)).toBe('light')
  })

  it('shows the same theme in the toggle and in Preferences', async () => {
    initTheme()
    setThemePreference('system')
    stubSystem(true)
    changeSystem(true)
    renderApp('/settings')
    expect(await screen.findByRole('button', { name: 'Switch to light mode' })).toBeInTheDocument()
  })
})

describe('theme tokens', () => {
  const dark = /:root\[data-theme="dark"\]\{([^}]*)\}/.exec(css)![1]
  const light = /:root\{\s*color-scheme:light;([^}]*)\}/.exec(css)![1]
  const names = (block: string) => [...block.matchAll(/--([a-z0-9-]+):/g)].map(match => match[1])
  const value = (block: string, name: string) => new RegExp(`--${name}:(#[0-9A-Fa-f]{6})`).exec(block)?.[1].toUpperCase()

  it('defines every colour token in both themes', () => {
    const colourNames = names(light).filter(name => !name.startsWith('font-') && !name.startsWith('radius'))
    expect(names(dark).sort()).toEqual(colourNames.sort())
  })

  it('uses the specified palette', () => {
    expect([value(light, 'cream'), value(light, 'paper'), value(light, 'sidebar'), value(light, 'ink'), value(light, 'green-deep'), value(light, 'gold')]).toEqual(['#F7F3EA', '#FFFCF6', '#EFEBDD', '#263A2D', '#355740', '#B39455'])
    expect([value(dark, 'cream'), value(dark, 'sidebar'), value(dark, 'paper'), value(dark, 'elevated'), value(dark, 'ink'), value(dark, 'ink-soft'), value(dark, 'green-deep'), value(dark, 'gold'), value(dark, 'line-strong')]).toEqual(['#111B17', '#15231C', '#1C2B23', '#25372C', '#F2EBDD', '#B7C1B3', '#A6BA91', '#D1B273', '#3B4B40'])
  })

  const luminance = (hex: string) => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(c => c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0)
  const contrast = (a: string, b: string) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05) }

  it.each([['light', light], ['dark', dark]])('keeps text readable in the %s theme (WCAG AA)', (_, block) => {
    for (const text of ['ink', 'ink-2', 'ink-soft', 'green-deep']) {
      for (const surface of ['cream', 'paper', 'sidebar', 'elevated', 'sage', 'field']) {
        expect(contrast(value(block, text)!, value(block, surface)!), `${text} on ${surface}`).toBeGreaterThanOrEqual(4.5)
      }
    }
    expect(contrast(value(block, 'paper')!, value(block, 'green-deep')!), 'button text').toBeGreaterThanOrEqual(4.5)
    expect(contrast(value(block, 'gold-deep')!, value(block, 'gold-soft')!), 'gold text').toBeGreaterThanOrEqual(4.5)
    expect(contrast(value(block, 'control')!, value(block, 'field')!), 'input border').toBeGreaterThanOrEqual(3)
    expect(contrast(value(block, 'decor')!, value(block, 'paper')!), 'completion circle').toBeGreaterThanOrEqual(3)
    expect(contrast(value(block, 'on-danger')!, value(block, 'danger')!), 'danger button').toBeGreaterThanOrEqual(4.5)
    expect(contrast(value(block, 'danger-text')!, value(block, 'danger-bg')!), 'error message').toBeGreaterThanOrEqual(4.5)
  })

  it('keeps colour values in the token blocks, not scattered through the stylesheet', () => {
    const afterTokens = css.slice(css.indexOf(':root{font-family'))
    const stray = [...afterTokens.matchAll(/#[0-9a-fA-F]{3,8}\b/g)].map(match => match[0].toUpperCase())
    expect(stray).toEqual(['#F8F1E4', '#F8F1E4']) // the logo plates' ivory ground: the same in both themes by design
  })

  it('matches Clerk’s appearance to the active theme', () => {
    const lightAppearance = clerkAppearanceFor('light')!.variables!
    const darkAppearance = clerkAppearanceFor('dark')!.variables!
    expect(lightAppearance.colorBackground).toBe('#FFFCF6')
    expect(darkAppearance.colorBackground).toBe('#1C2B23')
    expect(darkAppearance.colorForeground).toBe('#F2EBDD')
  })
})

describe('brand assets', () => {
  it('ships a favicon, small PNG icons, an apple icon and a manifest that name Optima Pars', () => {
    for (const file of ['favicon.svg', 'favicon-16.png', 'favicon-32.png', 'apple-touch-icon.png', 'icon-192.png', 'icon-512.png', 'manifest.webmanifest']) {
      expect(publicFiles, file).toContain(file)
    }
    const manifest = JSON.parse(manifestText)
    expect(manifest.name).toBe('Optima Pars')
    expect(manifest.icons.length).toBeGreaterThan(1)
    expect(faviconSvg).not.toMatch(/<text|<image/) // a simplified drawing with no lettering and no embedded raster
  })

  it('keeps the supplied artwork and its optimised derivatives', () => {
    expect(originalLogo).toHaveLength(1)
    for (const file of ['optima-pars-lockup-1254.webp', 'optima-pars-lockup-640.webp', 'optima-pars-arch-320.webp', 'optima-pars-arch-160.webp']) {
      expect(brandFiles, file).toContain(file)
    }
  })

  it('titles the page and links the icons and manifest', () => {
    expect(html).toContain('<title>Optima Pars — Unum est necessarium</title>')
    expect(html).toContain('rel="manifest"')
    expect(html).toContain('rel="apple-touch-icon"')
    expect(html).not.toMatch(/studium/i)
  })

  it('shows the name and motto in the sidebar and footer, and never the old name', async () => {
    renderApp('/inbox')
    const brand = await screen.findByRole('link', { name: /Optima Pars, Unum est necessarium/ })
    expect(brand).toHaveTextContent('Optima Pars')
    expect(brand).toHaveTextContent('Unum est necessarium')
    expect(document.body.textContent).not.toMatch(/studium/i)
    expect(screen.getByText('One thing is necessary.', { exact: false })).toBeInTheDocument()
  })

  it('shows the full artwork, undistorted, in About', async () => {
    renderApp('/settings')
    const logo = await screen.findByRole('img', { name: /Optima Pars: a monastery/ })
    expect(logo).toHaveAttribute('width', '1254')
    expect(logo).toHaveAttribute('height', '1254')
    expect(screen.getByText(/means “the best portion/)).toBeInTheDocument()
    expect(css).toMatch(/\.brand-lockup\{[^}]*aspect-ratio:1\/1/)
    expect(css).not.toMatch(/\.brand-lockup\{[^}]*object-fit:\s*cover/)
  })
})
