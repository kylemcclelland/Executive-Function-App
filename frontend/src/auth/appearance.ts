import type { ClerkProviderProps } from '@clerk/react'
import type { ResolvedTheme } from '../theme/theme'

const serif = '"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Times New Roman",serif'
const sans = 'Inter,"Segoe UI",system-ui,-apple-system,BlinkMacSystemFont,Roboto,sans-serif'

// The same palettes as the CSS tokens in index.css (Clerk's components are styled through props).
const palettes = {
  light: {
    primary: '#355740', onPrimary: '#FFFCF6', hover: '#2A4733', surface: '#FFFCF6', field: '#FFFCF6', text: '#263A2D',
    muted: '#55645A', mutedFill: '#E6E8D8', border: '#CFC9B4', line: '#E2DDCC', ring: '#55645A', danger: '#A74438', success: '#355740',
    shadow: '0 3px 12px rgba(38,58,45,.10)', popover: '0 8px 24px rgba(38,58,45,.14)', backdrop: 'rgba(38,58,45,.55)',
  },
  dark: {
    primary: '#A6BA91', onPrimary: '#111B17', hover: '#BACBA8', surface: '#1C2B23', field: '#14211A', text: '#F2EBDD',
    muted: '#B7C1B3', mutedFill: '#26392E', border: '#3B4B40', line: '#2F4036', ring: '#A6BA91', danger: '#E58F7F', success: '#A6BA91',
    shadow: '0 3px 12px rgba(0,0,0,.4)', popover: '0 8px 24px rgba(0,0,0,.5)', backdrop: 'rgba(6,11,9,.68)',
  },
} as const

/** Clerk's components, dressed in the Optima Pars palette for the active theme. */
export function clerkAppearanceFor(theme: ResolvedTheme): ClerkProviderProps['appearance'] {
  const c = palettes[theme]
  return {
    variables: {
      colorPrimary: c.primary,
      colorPrimaryForeground: c.onPrimary,
      colorBackground: c.surface,
      colorInput: c.field,
      colorInputForeground: c.text,
      colorForeground: c.text,
      colorMutedForeground: c.muted,
      colorMuted: c.mutedFill,
      colorBorder: c.border,
      colorRing: c.ring,
      colorNeutral: c.text,
      colorDanger: c.danger,
      colorSuccess: c.success,
      colorModalBackdrop: c.backdrop,
      fontFamily: sans,
      fontFamilyButtons: sans,
      fontSize: '13px',
      borderRadius: '6px',
    },
    elements: {
      rootBox: { width: '100%' },
      cardBox: { width: '100%', boxShadow: 'none' },
      card: { border: `1px solid ${c.line}`, borderRadius: '11px', boxShadow: c.shadow },
      headerTitle: { fontFamily: serif, fontWeight: 400, fontSize: '26px', letterSpacing: '-0.6px' },
      headerSubtitle: { color: c.muted },
      formButtonPrimary: { boxShadow: 'none', textTransform: 'none', fontWeight: 500, '&:hover': { backgroundColor: c.hover } },
      formFieldInput: { borderColor: c.border, boxShadow: 'none' },
      socialButtonsBlockButton: { borderColor: c.line, boxShadow: 'none' },
      footerActionLink: { color: c.primary, fontWeight: 500 },
      footer: { background: 'transparent' },
      dividerLine: { background: c.line },
      userButtonBox: { flexDirection: 'row-reverse', justifyContent: 'flex-end', gap: '10px' },
      userButtonOuterIdentifier: { color: c.text, fontSize: '12px', fontWeight: 500, paddingLeft: 0 },
      userButtonAvatarBox: { width: '32px', height: '32px', border: `1px solid ${c.border}` },
      userButtonPopoverCard: { border: `1px solid ${c.border}`, borderRadius: '10px', boxShadow: c.popover },
    },
  }
}
