import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Eye } from 'lucide-react'
import { Button } from '../components/ui'
import { ErrorMessage, Loading } from '../components/common'
import { DevotionView } from '../components/devotions/DevotionView'
import { EditorialGate } from '../components/editorial/EditorialGate'
import { ProseNote, StatusBadge } from '../components/editorial/EditorialParts'
import { api } from '../services/api'
import { describeEditorialError, proseIsUnapproved, textStatusLabels, workflowLabels } from '../lib/editorial'
import type { EditorialPreview, PreviewText, PrayerText } from '../types/devotions'
import '../components/editorial/editorial.css'

function Preview({ id }: { id: string }) {
  const query = useQuery({ queryKey: ['editorial-preview', id], queryFn: () => api<EditorialPreview>(`/editorial/devotions/${id}/preview`) })
  if (query.isPending) return <Loading />
  if (query.isError) {
    const problem = describeEditorialError(query.error)
    return <div className="editorial-problem"><ErrorMessage message={problem.message} /><div className="editorial-problem-actions">{problem.kind !== 'forbidden' && problem.kind !== 'missing' && <Button variant="outline" onClick={() => void query.refetch()}>Try again</Button>}<Button asChild variant="ghost"><Link to="/editorial/devotions">Back to the review queue</Link></Button></div></div>
  }
  const devotion = query.data
  const banner = <aside className="preview-banner" role="note">
    <Eye size={18} aria-hidden="true" />
    <div><strong>Unpublished preview.</strong> Only editors and approvers can see this page. It shows the devotion as The Oratory would, including prayer texts that are not approved, each marked below. Nothing here is public.
      <p className="preview-state">Devotion status: <StatusBadge label={workflowLabels[devotion.devotion_status]} tone={devotion.devotion_status === 'published' ? 'good' : 'attention'} />{devotion.devotion_status !== 'published' && ' It is not visible to readers.'}</p></div>
  </aside>
  const badge = (text: PrayerText) => {
    const item = text as PreviewText
    return item.publicly_visible
      ? <StatusBadge label="Approved: visible to readers" tone="good" />
      : <StatusBadge label={`${textStatusLabels[item.status]}: not visible to readers`} tone={item.status === 'approved' ? 'attention' : 'stop'} />
  }
  return <DevotionView devotion={devotion} backTo={`/editorial/devotions/${id}`} backLabel="Review" banner={banner} proseNote={proseIsUnapproved({ prose_origin: devotion.prose_origin, status: devotion.devotion_status }) ? <ProseNote /> : undefined} textBadge={badge} />
}

/** A private preview of a devotion in The Oratory's own layout, reusing the public components. */
export function EditorialPreviewPage() {
  const { id = '' } = useParams()
  return <div className="editorial"><EditorialGate>{() => <Preview id={id} />}</EditorialGate></div>
}
