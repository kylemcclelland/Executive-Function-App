import { Link } from 'react-router-dom'
import { ArrowRight, type LucideIcon } from 'lucide-react'
import { Button, Card } from '../components/ui'
import { PageHeader } from '../components/common'

export function FuturePage({ name, description, icon: Icon }: { name: string; description: string; icon: LucideIcon }) {
  return <><PageHeader eyebrow="COMING LATER" title={name}>Not available yet, but planned.</PageHeader><Card className="future-card"><span className="future-icon"><Icon size={34} strokeWidth={1.4} /></span><span className="tag">Later milestone</span><h2>This space is on the way.</h2><p>{description}</p><p className="muted">This space is planned for a later milestone and isn’t available yet.</p><Button asChild variant="outline"><Link to="/">Back to Today <ArrowRight size={16} /></Link></Button></Card></>
}
