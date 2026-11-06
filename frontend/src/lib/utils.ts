import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(value: string | null, options?: Intl.DateTimeFormatOptions) {
  if (!value) return ''
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString(undefined, options ?? { month: 'short', day: 'numeric' })
}
