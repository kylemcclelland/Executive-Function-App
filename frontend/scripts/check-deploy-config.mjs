// Pre-deploy gate for the Vercel configuration. Run before promoting anything to production:
//   npm run build && npm run check:deploy
// Fails (exit 1) while the API rewrite still points at the placeholder host, or if the
// Content-Security-Policy hash no longer matches the inline theme script in the built page.
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const config = JSON.parse(readFileSync(resolve(root, 'vercel.json'), 'utf8'))
const problems = []

const rewrites = config.rewrites ?? []
const api = rewrites.findIndex(rule => rule.source.startsWith('/api/'))
const spa = rewrites.findIndex(rule => rule.destination === '/index.html')
if (api === -1) problems.push('No /api rewrite: the app would receive index.html instead of data.')
else {
  let host = ''
  try { host = new URL(rewrites[api].destination.replace(':path*', 'x')).hostname } catch { problems.push('The /api rewrite destination is not a valid URL.') }
  if (host.endsWith('.invalid')) problems.push(`The /api rewrite still points at the placeholder host (${host}). Replace it with the Railway domain.`)
  if (rewrites[api].destination.startsWith('http://')) problems.push('The /api rewrite must use https.')
  if (spa !== -1 && spa < api) problems.push('The single-page-app rewrite comes before the /api rewrite.')
}
if (spa === -1) problems.push('No single-page-app rewrite to /index.html.')

const policy = JSON.stringify(config.headers ?? [])
const dist = resolve(root, 'dist/index.html')
if (existsSync(dist)) {
  const inline = /<script>([\s\S]*?)<\/script>/.exec(readFileSync(dist, 'utf8'))
  const hash = inline ? `sha256-${createHash('sha256').update(inline[1]).digest('base64')}` : null
  if (hash && !policy.includes(hash)) problems.push(`The CSP does not allow the built inline theme script (${hash}).`)
} else console.log('Note: dist/ not found, so the CSP hash was not checked. Run `npm run build` first.')

if (problems.length) {
  console.error('Deployment configuration problems:\n - ' + problems.join('\n - '))
  process.exit(1)
}
console.log('Deployment configuration looks ready.')
