import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '../components/ui'
import { Empty, ErrorMessage, Loading } from '../components/common'
import { DevotionView } from '../components/devotions/DevotionView'
import { ApiError, api } from '../services/api'
import type { Devotion } from '../types/devotions'

export function DevotionPage() {
  const { slug = '' } = useParams()
  const client = useQueryClient()
  const path = `/devotions/${encodeURIComponent(slug)}`
  const query = useQuery({ queryKey: ['devotion', slug], queryFn: () => api<Devotion>(path) })
  const bookmark = useMutation({
    mutationFn: (next: boolean) => api(`${path}/bookmark`, next ? 'PUT' : 'DELETE'),
    onSuccess: () => Promise.all([client.invalidateQueries({ queryKey: ['devotion', slug] }), client.invalidateQueries({ queryKey: ['devotions'] })]),
  })
  if (query.isPending) return <Loading />
  if (query.isError) {
    return query.error instanceof ApiError && query.error.status === 404
      ? <Empty title="This devotion isn’t available">It may not have been published yet. <Link to="/devotions">Back to Devotions</Link>.</Empty>
      : <><ErrorMessage message={query.error.message} /><Button variant="outline" onClick={() => void query.refetch()}>Try again</Button></>
  }
  return <>
    <DevotionView devotion={query.data} onToggleBookmark={next => bookmark.mutate(next)} bookmarkPending={bookmark.isPending} />
    {bookmark.isError && <ErrorMessage message={bookmark.error.message} />}
  </>
}
