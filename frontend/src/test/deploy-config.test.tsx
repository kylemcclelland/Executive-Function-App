import { describe, expect, it } from 'vitest'
import html from '../../index.html?raw'
import configText from '../../vercel.json?raw'

type Rule = { source: string; destination: string }
type Header = { source: string; headers: { key: string; value: string }[] }
const config = JSON.parse(configText) as { framework: string; rewrites: Rule[]; headers: Header[] }
const headerValue = (source: string, key: string) => config.headers.find(h => h.source === source)?.headers.find(h => h.key === key)?.value

async function sha256Base64(text: string) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
}

describe('Vercel deployment configuration', () => {
  it('builds with the Vite preset', () => expect(config.framework).toBe('vite'))

  it('proxies /api to the backend before the single-page-app fallback', () => {
    const api = config.rewrites.findIndex(rule => rule.source.startsWith('/api/'))
    const spa = config.rewrites.findIndex(rule => rule.destination === '/index.html')
    expect(api).toBeGreaterThanOrEqual(0)
    expect(spa).toBeGreaterThan(api)
    expect(config.rewrites[api].destination).toMatch(/^https:\/\/[^/]+\/api\/:path\*$/)
  })

  it('never aims the API rewrite at a host we do not control: it is a reserved placeholder until replaced', () => {
    // `.invalid` can never resolve. `npm run check:deploy` fails while it remains, so it cannot be promoted by accident.
    const host = new URL(config.rewrites.find(rule => rule.source.startsWith('/api/'))!.destination.replace(':path*', 'x')).hostname
    expect(host.endsWith('.invalid') || host.endsWith('.up.railway.app')).toBe(true)
  })

  it('serves deep links as the app but lets missing assets and API calls 404 honestly', () => {
    const spa = new RegExp(`^${config.rewrites.find(rule => rule.destination === '/index.html')!.source}$`)
    for (const path of ['/', '/tasks', '/settings', '/projects/abc', '/library/b1', '/sign-in/factor-one']) expect(path).toMatch(spa)
    expect('/assets/missing.js').not.toMatch(spa)
    expect('/api/tasks').not.toMatch(spa)
  })

  it('sends defensive headers on every page', () => {
    expect(headerValue('/(.*)', 'X-Content-Type-Options')).toBe('nosniff')
    expect(headerValue('/(.*)', 'X-Frame-Options')).toBe('DENY')
    expect(headerValue('/(.*)', 'Referrer-Policy')).toBe('strict-origin-when-cross-origin')
    expect(headerValue('/(.*)', 'Strict-Transport-Security')).toMatch(/max-age=\d{7,}/)
    expect(headerValue('/(.*)', 'Permissions-Policy')).toContain('camera=()')
  })

  it('has a content security policy that allows the inline theme script only by hash', async () => {
    const policy = headerValue('/(.*)', 'Content-Security-Policy-Report-Only')!
    const inline = /<script>([\s\S]*?)<\/script>/.exec(html)![1]
    expect(policy).toContain(`'sha256-${await sha256Base64(inline)}'`)
    const scripts = policy.split(';').map(part => part.trim()).find(part => part.startsWith('script-src'))!
    expect(scripts).not.toContain("'unsafe-inline'")
    expect(scripts).not.toContain("'unsafe-eval'")
    expect(scripts).not.toMatch(/\s\*(\s|$)/)
    for (const directive of ["object-src 'none'", "base-uri 'self'", "frame-ancestors 'none'", "default-src 'self'"]) expect(policy).toContain(directive)
  })

  it('caches fingerprinted assets for a year', () => {
    expect(headerValue('/assets/(.*)', 'Cache-Control')).toBe('public, max-age=31536000, immutable')
  })

  it('does not put any secret in the committed configuration', () => {
    expect(configText).not.toMatch(/sk_(live|test)_|pk_(live|test)_|client_secret|Bearer /)
  })
})
