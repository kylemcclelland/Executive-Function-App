import { describe, expect, it } from 'vitest'
import css from '../index.css?raw'
import officeCss from '../components/devotions/divine-office.css?raw'
import html from '../../index.html?raw'

// The font files in public/, by name (their content is not needed, only that each referenced file exists).
const fontFiles = Object.keys(import.meta.glob('../../public/fonts/*.woff2', { query: '?raw', eager: true })).map(path => path.split('/').pop())

describe('typography', () => {
  it('defines display, reading and UI tokens, keeping the existing serif and sans names as aliases', () => {
    expect(css).toMatch(/--font-display:"Almendra"/)
    expect(css).toMatch(/--font-reading:"Cormorant Garamond"/)
    expect(css).toMatch(/--font-ui:Inter/)
    expect(css).toMatch(/--font-serif:var\(--font-reading\)/)
    expect(css).toMatch(/body\{font-family:var\(--font-ui\)\}/)
  })

  it('self-hosts only Almendra and Cormorant Garamond as WOFF2 with font-display: swap, and every referenced file exists', () => {
    const faces = css.match(/@font-face\{[^}]+\}/g) ?? []
    expect(faces.length).toBeGreaterThan(0)
    expect(new Set(faces.map((face: string) => /font-family:'([^']+)'/.exec(face)?.[1]))).toEqual(new Set(['Almendra', 'Cormorant Garamond']))
    for (const face of faces as string[]) {
      expect(face).toContain('font-display:swap')
      const file = /url\((\/fonts\/[^)]+\.woff2)\)/.exec(face)?.[1]
      expect(file).toBeTruthy()
      expect(fontFiles).toContain(file!.split('/').pop())
    }
    expect(css).not.toMatch(/fonts\.googleapis|fonts\.gstatic/)                                  // no third-party font requests
  })

  it('uses display type for headings and the wordmark, reading type for long passages, and the UI face for times', () => {
    expect(css).toMatch(/h1,\.brand-name[^{]*\{font-family:var\(--font-display\)/)
    expect(css).toMatch(/\.rule-time,\.rule-title[^{]*\{font-family:var\(--font-ui\)\}/)
    expect(officeCss).toMatch(/\.office-column \{[^}]*font-family: var\(--font-serif\)/)
    expect(css).toMatch(/\.office-column\{font-size:21px;line-height:1\.75\}/)
  })

  it('preloads the two most used faces so first paint does not shift', () => {
    expect(html).toContain('/fonts/almendra-400-latin.woff2')
    expect(html).toContain('/fonts/cormorant-garamond-400-latin.woff2')
  })
})
