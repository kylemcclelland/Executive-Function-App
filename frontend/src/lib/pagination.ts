import type { BookSort } from '../types'

export const bookSorts: { value: BookSort; label: string }[] = [
  { value: 'title', label: 'Title (A–Z)' },
  { value: 'title_desc', label: 'Title (Z–A)' },
  { value: 'recent', label: 'Recently added' },
  { value: 'year_desc', label: 'Newest published' },
  { value: 'year_asc', label: 'Oldest published' },
]

export const isBookSort = (value: string | null): value is BookSort => bookSorts.some(sort => sort.value === value)

/** Page numbers to show: the ends and the neighbourhood of the current page, with gaps marked. */
export function pageWindow(page: number, totalPages: number): (number | 'gap')[] {
  const wanted = new Set([1, totalPages, page - 1, page, page + 1])
  const numbers = [...wanted].filter(number => number >= 1 && number <= totalPages).sort((a, b) => a - b)
  const result: (number | 'gap')[] = []
  numbers.forEach((number, index) => {
    if (index > 0 && number - numbers[index - 1] > 1) result.push('gap')
    result.push(number)
  })
  return result
}
