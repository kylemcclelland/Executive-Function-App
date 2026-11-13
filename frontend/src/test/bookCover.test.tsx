import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BookCover } from '../components/library/BookCover'
import { COVER_PALETTE, coverColor } from '../lib/covers'

const ID = '7df6d02c-45a1-4e5c-9ad2-0d7c2bb01a11'

describe('the generated book cover', () => {
  it('gives the same book the same palette colour every time, and only palette colours', () => {
    expect(coverColor(ID)).toBe(coverColor(ID))
    const seen = new Set<string>()
    for (let i = 0; i < 200; i++) {
      const color = coverColor(`book-${i}`)
      expect(COVER_PALETTE).toContain(color)
      seen.add(color)
    }
    expect(seen.size).toBe(COVER_PALETTE.length)   // every palette colour is actually reachable
  })

  it('shows the real title and author, centred on a solid palette background', () => {
    const { container } = render(<BookCover bookId={ID} title="Confessions" author="St. Augustine" size="detail" />)
    expect(screen.getByText('Confessions')).toBeInTheDocument()
    expect(screen.getByText('St. Augustine')).toBeInTheDocument()
    const cover = container.querySelector('.book-cover') as HTMLElement
    expect(cover.getAttribute('aria-hidden')).toBe('true')
    expect(cover.style.backgroundColor).not.toBe('')
    expect(cover.querySelector('svg')).not.toBeNull()   // the small book icon
  })

  it('omits the author line gracefully when there is none', () => {
    const { container } = render(<BookCover bookId={ID} title="Middlemarch" size="detail" />)
    expect(screen.getByText('Middlemarch')).toBeInTheDocument()
    expect(container.querySelector('.book-cover-author')).toBeNull()
  })

  it('steps the title size down as titles grow, so long titles stay legible', () => {
    const size = (title: string) => {
      const { container, unmount } = render(<BookCover bookId={ID} title={title} size="detail" />)
      const px = (container.querySelector('.book-cover-title') as HTMLElement).style.fontSize
      unmount()
      return px
    }
    expect(size('Confessions')).toBe('14px')
    expect(size('Summa Theologiae, Prima Pars')).toBe('12px')
    expect(size('The Consolation of Philosophy, in a New Translation')).toBe('10px')
  })

  it('renders the list thumbnail as a miniature cover: colour and icon, no cramped text', () => {
    const { container } = render(<BookCover bookId={ID} title="Confessions" author="St. Augustine" />)
    const cover = container.querySelector('.book-cover-list') as HTMLElement
    expect(cover).not.toBeNull()
    expect(cover.querySelector('svg')).not.toBeNull()
    expect(container.querySelector('.book-cover-title')).toBeNull()
    expect(cover.style.backgroundColor).toBe((render(<BookCover bookId={ID} title="Confessions" />).container.querySelector('.book-cover') as HTMLElement).style.backgroundColor)
  })
})
