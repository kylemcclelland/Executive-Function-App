import archSmall from '../../assets/brand/optima-pars-arch-160.webp'
import archLarge from '../../assets/brand/optima-pars-arch-320.webp'
import lockupSmall from '../../assets/brand/optima-pars-lockup-640.webp'
import lockupLarge from '../../assets/brand/optima-pars-lockup-1254.webp'

export const MOTTO = 'Unum est necessarium'
export const MOTTO_ENGLISH = 'One thing is necessary.'

/**
 * The approved Optima Pars artwork, unaltered and at its original 1:1 proportions. The image keeps
 * its own ivory ground in both themes, like a printed plate, so the engraving is never recoloured.
 */
export function BrandLockup({ className = '' }: { className?: string }) {
  return <img className={`brand-lockup ${className}`} src={lockupLarge} srcSet={`${lockupSmall} 640w, ${lockupLarge} 1254w`} sizes="(max-width: 520px) 70vw, 300px"
    width={1254} height={1254} alt="Optima Pars: a monastery among cypress-covered hills above an open book marked with the Chi-Rho. Unum est necessarium." />
}

/** Sidebar mark: the monastery arch cropped from the approved artwork, with live, themeable type. */
export function SidebarBrand() {
  return <>
    <span className="brand-plate"><img src={archSmall} srcSet={`${archSmall} 160w, ${archLarge} 320w`} sizes="56px" width={56} height={56} alt="" /></span>
    <span className="brand-text"><span className="brand-name">Optima Pars</span><span className="brand-motto">{MOTTO}</span></span>
  </>
}
