import { Church } from 'lucide-react'
import { Card } from '../ui'

/**
 * A reserved place for the planned liturgical calendar and saint of the day. It is not connected to
 * any liturgical data, so it shows none: no feast, saint or biography is invented here.
 */
export function LiturgyCard() {
  return <Card className="liturgy-card" aria-label="Living Liturgically, coming later">
    <div className="section-heading"><div className="section-title"><Church size={17} /><h2>Living Liturgically</h2></div><span className="tag">Coming later</span></div>
    <p className="muted">A quiet place for the day’s feast or saint and the liturgical season. It is not connected to a liturgical calendar yet, so nothing is shown.</p>
    <div className="liturgy-placeholder" aria-hidden="true"><span /><span /><span /></div>
  </Card>
}
