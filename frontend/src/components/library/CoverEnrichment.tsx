import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ImageIcon } from 'lucide-react'
import { api } from '../../services/api'
import { useNow } from '../../hooks/useActiveSession'
import { cooldownMessage, isAbort } from '../../lib/covers'
import type { CoverAutoJob, CoverBatch, CoverStatus } from '../../types'
import { Button } from '../ui'

const MAX_BATCHES = 100

function autoNote(job: CoverAutoJob, now: number): string {
  const found = `${job.covers_found} ${job.covers_found === 1 ? 'cover' : 'covers'} found`
  const left = job.remaining !== null ? ` · ${job.remaining} left` : ''
  if (job.status === 'done') return `Automatic search finished: ${found}${job.without_cover ? ` · Open Library has none for ${job.without_cover}` : ''}.`
  if (job.status === 'paused') return `Automatic search paused: ${found}${left}.${job.last_error ? ` ${job.last_error}` : ''}`
  if (job.waiting && job.next_run_at) {
    const minutes = Math.max(1, Math.ceil((Date.parse(job.next_run_at) - now) / 60_000))
    return `Automatic search waiting (${job.last_error ?? 'cooling down'}) · ${found}${left} · continues in about ${minutes} min — no need to keep this page open.`
  }
  return `Automatic search running: ${found}${left} — it continues on the server, so this page can be closed.`
}

/**
 * Looks for covers a few books at a time. The server paces requests (one every few seconds), remembers every answer, and honours Open Library's cooldown, so this just keeps
 * asking for the next small batch until it is done, rate limited, or stopped. Existing cover
 * URLs are never replaced, and the rest of the Library stays usable throughout.
 */
export function CoverEnrichment() {
  const client = useQueryClient()
  const status = useQuery({ queryKey: ['covers-missing'], queryFn: () => api<CoverStatus>('/books/covers/missing') })
  const auto = useQuery({
    queryKey: ['covers-auto'],
    queryFn: () => api<CoverAutoJob>('/books/covers/auto'),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 30_000 : false),
  })
  const autoAction = useMutation({
    mutationFn: (action: 'start' | 'pause' | 'resume') => api<CoverAutoJob>(`/books/covers/auto/${action}`, 'POST', {}),
    onSuccess: (job) => client.setQueryData(['covers-auto'], job),
  })
  const now = useNow(30_000)
  const [running, setRunning] = useState(false)
  const [found, setFound] = useState(0)
  const [left, setLeft] = useState<number | null>(null)
  const [message, setMessage] = useState('')
  const stop = useRef(false)
  const controller = useRef<AbortController | null>(null)
  const count = status.data?.count ?? 0
  const blockedUntil = status.data?.blocked_until ?? null
  const cooling = blockedUntil !== null && Date.parse(blockedUntil) > now
  const coolingNote = cooling ? cooldownMessage(blockedUntil, Math.max(0, Math.ceil((Date.parse(blockedUntil) - now) / 1000)), status.data?.cooldown_reason ?? null) : ''
  async function run() {
    setRunning(true)
    setMessage('')
    setFound(0)
    stop.current = false
    const skip: string[] = []
    let total = 0, converted = 0, noCover = 0, note = ''
    try {
      for (let batch = 0; batch < MAX_BATCHES && !stop.current; batch++) {
        controller.current = new AbortController()
        const result = await api<CoverBatch>('/books/covers/enrich', 'POST', { limit: 3, skip }, controller.current.signal)
        skip.push(...result.checked_ids)
        total += result.found
        converted += result.converted
        noCover += result.not_found
        setFound(total)
        setLeft(result.remaining)
        if (result.found > 0 || result.converted > 0) await client.invalidateQueries({ queryKey: ['books'] })
        if (result.rate_limited || result.unavailable) { note = cooldownMessage(result.blocked_until, result.retry_after_seconds, result.cooldown_reason); break }
        if (result.stopped_early) { note = 'Couldn’t reach Open Library just now. Nothing was changed. Try again later.'; break }
        if (result.remaining === 0 && result.legacy_remaining === 0) break
        if (result.checked === 0 && result.cached === 0 && result.converted === 0) break
      }
    } catch (failure) {
      note = isAbort(failure) ? `Stopped. ${total} ${total === 1 ? 'cover was' : 'covers were'} added so far; everything learned is remembered.` : failure instanceof Error ? failure.message : 'Something went wrong looking for covers.'
    } finally {
      controller.current = null
      setRunning(false)
      await client.invalidateQueries({ queryKey: ['covers-missing'] })
      await client.invalidateQueries({ queryKey: ['books'] })
    }
    setMessage(note || `Added ${total} ${total === 1 ? 'cover' : 'covers'}${noCover ? `. Open Library has none for ${noCover}` : ''}${converted ? `. Steadied ${converted} existing cover ${converted === 1 ? 'link' : 'links'}` : ''}. Covers are matched by ISBN and may show a different edition; set a cover URL on any book to change it.`)
  }
  function cancel() {
    stop.current = true
    controller.current?.abort()
  }
  const stats = status.data
  const progressNote = stats
    ? `${stats.with_covers} ${stats.with_covers === 1 ? 'book has' : 'books have'} a cover · ${stats.count} missing · Open Library answers remembered: ${stats.found_lookups} found, ${stats.not_found_lookups} without a cover`
    : ''
  const job = auto.data
  const jobActive = job?.exists && job.status !== 'done'
  if (!running && count === 0 && !message && !cooling && !jobActive) return null
  return <div className="cover-row" aria-live="polite">
    {running ? <><span className="cover-status"><ImageIcon size={15} /> Looking for covers, one book every few seconds… {found} found{left !== null && ` · ${left} left`}</span><Button size="sm" variant="outline" onClick={cancel}>Stop</Button></>
      : <>{(count > 0 || cooling) && <Button size="sm" variant="outline" disabled={cooling || count === 0} onClick={() => void run()}><ImageIcon size={15} />Find missing covers ({count})</Button>}{cooling ? <span className="cover-status">{coolingNote}</span> : message && <span className="cover-status">{message}</span>}{progressNote && <span className="cover-status muted small">{progressNote}</span>}</>}
    {!running && job && <>
      {!jobActive && count > 0 && <Button size="sm" variant="outline" disabled={autoAction.isPending} onClick={() => autoAction.mutate('start')}>Search automatically</Button>}
      {job.exists && job.status === 'running' && <Button size="sm" variant="outline" disabled={autoAction.isPending} onClick={() => autoAction.mutate('pause')}>Pause automatic search</Button>}
      {job.exists && job.status === 'paused' && <Button size="sm" variant="outline" disabled={autoAction.isPending} onClick={() => autoAction.mutate('resume')}>Resume automatic search</Button>}
      {job.exists && <span className="cover-status muted small">{autoNote(job, now)}</span>}
    </>}
  </div>
}
