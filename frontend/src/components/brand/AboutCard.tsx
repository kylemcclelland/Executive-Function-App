import { Card } from '../ui'
import { BrandLockup, MOTTO, MOTTO_ENGLISH } from './Brand'

export function AboutCard() {
  return <Card className="settings-card about-card">
    <h2>About Optima Pars</h2>
    <div className="about-body">
      <BrandLockup className="about-lockup" />
      <div>
        <p className="about-motto"><span lang="la">{MOTTO}</span></p>
        <p className="muted">{MOTTO_ENGLISH}</p>
        <p className="muted"><i>Optima pars</i> means “the best portion.” The name and motto come from Luke 10:42, where Christ tells Martha that Mary has chosen the better part. Optima Pars is built on the belief that productivity should serve a well-ordered life, not replace it: attend first to what matters most.</p>
      </div>
    </div>
  </Card>
}
