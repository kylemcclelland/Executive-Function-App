import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { dayHeading, groupByDay, localDay, timeLabel } from '../lib/calendar'
import type { CalendarEvent, CalendarStatus } from '../types'

const event = (id: string, title: string, fields: Partial<CalendarEvent> = {}): CalendarEvent => ({
  id, title, all_day: false, start: '2030-03-05T14:00:00Z', end: '2030-03-05T14:30:00Z', time_zone: 'America/New_York',
  start_date: null, end_date: null, location: null, html_link: null, recurring: false, ...fields,
})
const json = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

let status: CalendarStatus
let pages: { events: CalendarEvent[]; next_page_token: string | null }[]
let eventsFail: { status: number; detail: string } | null
let connectUrl: string
let requests: { url: string; method: string }[]
let queryClient: QueryClient
let assign: ReturnType<typeof vi.fn>

const connected = (): CalendarStatus => ({ configured: true, status: 'active', account_email: 'marcus@gmail.example', connected_at: '2030-03-01T00:00:00Z', last_successful_sync_at: '2030-03-01T00:00:00Z' })

beforeEach(() => {
  status = { configured: true, status: 'not_connected', account_email: null, connected_at: null, last_successful_sync_at: null }
  pages = [{ events: [], next_page_token: null }]
  eventsFail = null
  connectUrl = 'https://accounts.google.com/o/oauth2/v2/auth?state=abc'
  requests = []
  assign = vi.fn()
  vi.stubGlobal('location', { ...window.location, assign })
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } })
  vi.stubGlobal('fetch', vi.fn(async (input: string, options?: RequestInit) => {
    const url = input.replace('/api', '')
    const method = options?.method ?? 'GET'
    requests.push({ url, method })
    if (url === '/integrations/google-calendar/status') return json(status)
    if (url === '/integrations/google-calendar/connect' && method === 'POST') return json({ authorization_url: connectUrl })
    if (url === '/integrations/google-calendar/disconnect' && method === 'DELETE') { status = { ...status, status: 'not_connected', account_email: null }; return json(null, 204) }
    if (url.startsWith('/integrations/google-calendar/events')) {
      if (eventsFail) return json({ detail: eventsFail.detail }, eventsFail.status)
      const token = new URL(url, 'http://x').searchParams.get('page_token')
      const index = token ? Number(token) : 0
      return json({ ...pages[index], time_min: '2030-03-01T00:00:00Z', time_max: '2030-03-31T00:00:00Z' })
    }
    if (url === '/user') return json({ timezone: 'America/New_York' })
    if (url === '/today') return json({ date: '2030-03-05', timezone: 'America/New_York', priorities: [], previous_tasks: [], completed_tasks: [], inbox_count: 0 })
    if (url === '/tasks') return json([])
    return json({ detail: `Unhandled mock ${method} ${url}` }, 404)
  }))
})
afterEach(() => { queryClient.clear(); vi.unstubAllGlobals() })

function setup(path: string) {
  const user = userEvent.setup()
  render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter></QueryClientProvider>)
  return user
}
const eventRequests = () => requests.filter(r => r.url.includes('/events'))

describe('Calendar page', () => {
  it('says plainly when the server has no Google credentials', async () => {
    status = { ...status, configured: false }
    setup('/calendar')
    await screen.findByText('Google Calendar isn’t set up here')
    expect(screen.queryByRole('button', { name: 'Connect Google Calendar' })).not.toBeInTheDocument()
  })

  it('offers to connect, and sends nothing to Google until the user chooses to', async () => {
    const user = setup('/calendar')
    const connect = await screen.findByRole('button', { name: 'Connect Google Calendar' })
    expect(screen.getByText(/entirely optional/)).toBeInTheDocument()
    expect(requests.map(r => `${r.method} ${r.url}`)).not.toContain('POST /integrations/google-calendar/connect')
    expect(eventRequests()).toHaveLength(0)
    expect(assign).not.toHaveBeenCalled()
    await user.click(connect)
    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/v2/auth?state=abc'))
  })

  it('refuses to navigate anywhere but Google’s consent screen', async () => {
    connectUrl = 'https://evil.example/phish'
    const user = setup('/calendar')
    await user.click(await screen.findByRole('button', { name: 'Connect Google Calendar' }))
    await screen.findByRole('alert')
    expect(assign).not.toHaveBeenCalled()
  })

  it('shows the connected account and upcoming events grouped by day, in the user’s timezone', async () => {
    status = connected()
    pages = [{ events: [
      event('a', 'Morning standup'),
      event('b', 'Dentist', { start: '2030-03-05T20:00:00Z', end: '2030-03-05T21:00:00Z', location: 'Main St', recurring: true, html_link: 'https://calendar.google.com/event?eid=1' }),
      event('c', 'Conference', { all_day: true, start: null, end: null, start_date: '2030-03-07', end_date: '2030-03-09', time_zone: null }),
    ], next_page_token: null }]
    setup('/calendar')
    await screen.findByText('marcus@gmail.example')
    expect(await screen.findByText('Morning standup')).toBeInTheDocument()
    const days = screen.getAllByRole('heading', { level: 3 }).map(h => h.textContent)
    expect(days).toEqual(['Tuesday, March 5', 'Thursday, March 7'])
    expect(screen.getByText(/9:00\s?AM\s–\s9:30\s?AM/)).toBeInTheDocument() // 14:00Z is 9:00 in New York
    expect(screen.getByText('All day · through Mar 9')).toBeInTheDocument()
    expect(screen.getByText('Main St')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Repeating event' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Dentist/ })).toHaveAttribute('href', 'https://calendar.google.com/event?eid=1')
    expect(screen.getByRole('link', { name: /Dentist/ })).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('does not link events to non-https URLs', async () => {
    status = connected()
    pages = [{ events: [event('x', 'Sneaky', { html_link: 'javascript:alert(1)' })], next_page_token: null }]
    setup('/calendar')
    await screen.findByText('Sneaky')
    expect(screen.queryByRole('link', { name: /Sneaky/ })).not.toBeInTheDocument()
  })

  it('pages through events', async () => {
    status = connected()
    pages = [{ events: [event('1', 'First')], next_page_token: '1' }, { events: [event('2', 'Second', { start: '2030-03-06T15:00:00Z', end: null })], next_page_token: null }]
    const user = setup('/calendar')
    await screen.findByText('First')
    expect(screen.queryByText('Second')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show more' }))
    await screen.findByText('Second')
    expect(screen.queryByRole('button', { name: 'Show more' })).not.toBeInTheDocument()
    expect(eventRequests().at(-1)?.url).toContain('page_token=1')
  })

  it('shows an empty state, loading, and a retryable error', async () => {
    status = connected()
    eventsFail = { status: 503, detail: 'Google Calendar is temporarily unavailable. Please try again.' }
    const user = setup('/calendar')
    await screen.findByText('Google Calendar is temporarily unavailable. Please try again.')
    eventsFail = null
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByText('Nothing on your calendar in the next 30 days.')
  })

  it('asks the user to reconnect when Google no longer accepts the authorization', async () => {
    status = { ...connected(), status: 'needs_reauth' }
    const user = setup('/calendar')
    await screen.findByText(/no longer allows Optima Pars/)
    expect(eventRequests()).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Reconnect' }))
    await waitFor(() => expect(assign).toHaveBeenCalled())
  })

  it('disconnects only after confirmation, then offers to connect again', async () => {
    status = connected()
    const user = setup('/calendar')
    await user.click(await screen.findByRole('button', { name: 'Disconnect' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/Your Google account and events are not changed/)).toBeInTheDocument()
    expect(requests.some(r => r.method === 'DELETE')).toBe(false)
    await user.click(within(dialog).getByRole('button', { name: 'Keep connected' }))
    expect(requests.some(r => r.method === 'DELETE')).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Disconnect' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Disconnect' }))
    await screen.findByRole('button', { name: 'Connect Google Calendar' })
    expect(requests.filter(r => r.method === 'DELETE')).toHaveLength(1)
  })

  it.each([
    ['connected', 'status', 'Google Calendar is connected.'],
    ['access_denied', 'status', /Nothing was connected/],
    ['invalid_state', 'alert', /expired or was already used/],
    ['missing_scope', 'alert', /calendar permission/],
  ] as const)('reports the outcome of returning from Google: %s', async (outcome, role, text) => {
    setup(`/calendar?google=${outcome}`)
    expect(await screen.findByRole(role)).toHaveTextContent(text)
  })
})

describe('Today', () => {
  it('shows nothing about calendars when the server does not offer them, and keeps the priorities', async () => {
    status = { ...status, configured: false }
    setup('/')
    await screen.findByText('Choose your priorities')
    expect(screen.queryByText('Coming up')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Today’s Priorities/ })).toHaveTextContent('0 / 3')
  })

  it('works unchanged if the calendar service errors', async () => {
    vi.mocked(fetch).mockImplementationOnce(async () => json({ detail: 'boom' }, 500))
    setup('/')
    await screen.findByText('Choose your priorities')
    expect(screen.queryByText('Coming up')).not.toBeInTheDocument()
  })

  it('invites, without pushing, a user who has not connected', async () => {
    setup('/')
    const link = await screen.findByRole('link', { name: /Connect Google Calendar/ })
    expect(link).toHaveAttribute('href', '/calendar')
    expect(eventRequests()).toHaveLength(0)
  })

  it('lists the next few events for a connected user', async () => {
    status = connected()
    pages = [{ events: ['One', 'Two', 'Three', 'Four', 'Five', 'Six'].map((title, i) => event(String(i), title, { start: `2030-03-0${i + 1}T15:00:00Z`, end: null })), next_page_token: null }]
    setup('/')
    await screen.findByText('One')
    expect(screen.getByText('Four')).toBeInTheDocument()
    expect(screen.queryByText('Five')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open calendar/ })).toHaveAttribute('href', '/calendar')
    expect(eventRequests()[0].url).toContain('page_size=6')
    expect(screen.getByRole('heading', { name: /Today’s Priorities/ })).toHaveTextContent('0 / 3')
  })

  it('asks to reconnect rather than showing stale events', async () => {
    status = { ...connected(), status: 'needs_reauth' }
    setup('/')
    expect(await screen.findByRole('link', { name: /Reconnect Google Calendar/ })).toBeInTheDocument()
    expect(eventRequests()).toHaveLength(0)
  })
})

describe('calendar helpers', () => {
  it('formats times and days in the given timezone, not the browser’s', () => {
    const e = event('a', 'x', { start: '2030-03-06T03:30:00Z', end: '2030-03-06T05:00:00Z' })
    expect(localDay(new Date(e.start!), 'America/Los_Angeles')).toBe('2030-03-05')
    expect(localDay(new Date(e.start!), 'Asia/Tokyo')).toBe('2030-03-06')
    expect(timeLabel(e, 'America/New_York')).toMatch(/10:30\s?PM\s–\sMar 6, 12:00\s?AM/)
    expect(timeLabel({ ...e, end: null }, 'UTC')).toMatch(/3:30\s?AM$/)
  })

  it('labels all-day events and groups consecutive events by day', () => {
    const day = event('d', 'd', { all_day: true, start: null, end: null, start_date: '2030-03-05', end_date: '2030-03-05' })
    expect(timeLabel(day)).toBe('All day')
    const groups = groupByDay([day, event('a', 'a'), event('b', 'b', { start: '2030-03-06T15:00:00Z' })], 'America/New_York')
    expect(groups.map(g => [g.day, g.events.length])).toEqual([['2030-03-05', 2], ['2030-03-06', 1]])
  })

  it('names today and tomorrow', () => {
    const now = new Date('2030-03-05T12:00:00Z')
    expect(dayHeading('2030-03-05', 'UTC', now)).toBe('Today')
    expect(dayHeading('2030-03-06', 'UTC', now)).toBe('Tomorrow')
    expect(dayHeading('2030-03-09', 'UTC', now)).toBe('Saturday, March 9')
  })
})
