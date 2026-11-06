import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card } from '../components/ui'
import { Empty, ErrorMessage, Loading, PageHeader } from '../components/common'
import { Capture } from '../components/Capture'
import { InboxEntry } from '../components/inbox/InboxEntry'
import { api } from '../services/api'
import type { InboxItem } from '../types'

export function InboxPage() {
  const query = useQuery({ queryKey: ['inbox'], queryFn: () => api<InboxItem[]>('/inbox') })
  const [filter, setFilter] = useState<InboxItem['status']>('unprocessed')
  const filtered = query.data?.filter(item => item.status === filter) ?? []
  return <><PageHeader eyebrow="LET YOUR MIND EXHALE" title="Your inbox">Catch it now. Give it a home when you’re ready.</PageHeader><Capture /><div className="tabs" aria-label="Filter inbox">{(['unprocessed', 'processed', 'archived'] as const).map(status => <Button key={status} variant={filter === status ? 'default' : 'ghost'} aria-pressed={filter === status} onClick={() => setFilter(status)}>{status === 'unprocessed' ? 'Unprocessed' : status === 'processed' ? 'Processed' : 'Archived'} <span className="tab-count">{query.data?.filter(i => i.status === status).length ?? 0}</span></Button>)}</div>
    <Card>{query.isPending ? <Loading /> : query.isError ? <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></> : filtered.length ? filtered.map(item => <InboxEntry key={`${item.id}-${item.updated_at ?? item.status}`} item={item} />) : <Empty title={filter === 'unprocessed' ? 'A little more headspace' : `No ${filter} thoughts yet`}>{filter === 'unprocessed' ? 'Your unprocessed thoughts will land here. No need to hold everything in your head.' : 'Your thoughts will appear here when you move them.'}</Empty>}</Card></>
}
