import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { Button } from '../ui'
import { ErrorMessage, Loading } from '../common'
import { describeEditorialError, useEditorialAccess } from '../../lib/editorial'
import type { EditorialAccess } from '../../types/devotions'

/**
 * Everything under /editorial needs an editorial role. A signed-in person without one sees a plain
 * explanation here, not an error. The server enforces the same rule on every request, so this gate is
 * only about being kind: hiding a screen is never what protects the content.
 */
export function EditorialGate({ children }: { children: (access: EditorialAccess) => ReactNode }) {
  const access = useEditorialAccess()
  if (access.isPending) return <Loading />
  if (access.isError) {
    const problem = describeEditorialError(access.error)
    return <div className="editorial-problem"><ErrorMessage message={problem.message} />{problem.kind !== 'forbidden' && <Button variant="outline" onClick={() => void access.refetch()}>Try again</Button>}</div>
  }
  if (!access.data.is_editor && !access.data.is_approver) {
    return <section className="editorial-restricted" aria-labelledby="restricted-title">
      <Lock size={26} strokeWidth={1.4} aria-hidden="true" />
      <h1 id="restricted-title">Editorial review is private</h1>
      <p>This area is for the editors and approvers who check prayer texts against their sources. Your account doesn’t hold an editorial role, so nothing here is available to you.</p>
      <p className="muted">Roles are granted by the person who runs the server, by Clerk user ID. Signing in does not grant one.</p>
      <Button asChild variant="outline"><Link to="/devotions">Back to The Oratory</Link></Button>
    </section>
  }
  return <>{children(access.data)}</>
}
