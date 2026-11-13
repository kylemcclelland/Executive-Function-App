import { useEffect, useState } from 'react'

/** The browser's install prompt, if it offered one (Chromium's beforeinstallprompt). */
interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

const DISPLAY_MODES = ['(display-mode: standalone)', '(display-mode: fullscreen)', '(display-mode: minimal-ui)']

/** True while running as an installed app (Chromium display modes, or iOS standalone). */
export function runningStandalone(): boolean {
  if (typeof window === 'undefined') return false
  const nav = window.navigator as Navigator & { standalone?: boolean }
  return nav.standalone === true || DISPLAY_MODES.some(query => window.matchMedia?.(query)?.matches)
}

export function isIOS(): boolean {
  const agent = window.navigator.userAgent
  return /iPad|iPhone|iPod/.test(agent) || (agent.includes('Mac') && window.navigator.maxTouchPoints > 1)
}

/**
 * Installation state for "Install Optima Pars": whether the app already runs installed (hide the
 * option), whether the browser offered a native prompt (show a real button), and the iOS case
 * (show Share → Add to Home Screen guidance, since iOS never fires beforeinstallprompt).
 *
 * Known limitation, by design of the platform: a regular browser tab cannot reliably tell that
 * the app is installed elsewhere, so a browser window may still show installation guidance even
 * after installing. Only the installed window itself knows it is standalone.
 */
export function useInstallPrompt() {
  const [standalone, setStandalone] = useState(runningStandalone)
  const [prompt, setPrompt] = useState<InstallPromptEvent | null>(null)

  useEffect(() => {
    const offered = (event: Event) => {
      event.preventDefault()               // keep it for our own button; never auto-prompt
      setPrompt(event as InstallPromptEvent)
    }
    const installed = () => { setPrompt(null); setStandalone(runningStandalone()) }
    window.addEventListener('beforeinstallprompt', offered)
    window.addEventListener('appinstalled', installed)
    const media = DISPLAY_MODES.map(query => window.matchMedia?.(query)).filter(Boolean)
    const changed = () => setStandalone(runningStandalone())
    media.forEach(m => m.addEventListener?.('change', changed))
    return () => {
      window.removeEventListener('beforeinstallprompt', offered)
      window.removeEventListener('appinstalled', installed)
      media.forEach(m => m.removeEventListener?.('change', changed))
    }
  }, [])

  async function install() {
    if (!prompt) return
    await prompt.prompt()
    const choice = await prompt.userChoice   // respect the decision either way
    if (choice.outcome === 'accepted') setPrompt(null)
  }

  return { standalone, canPrompt: prompt !== null, install, ios: !standalone && isIOS() }
}
