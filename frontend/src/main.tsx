import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { BrowserRouter } from 'react-router-dom'
import { getToken } from '@clerk/react'
import App from './App.tsx'
import { ClerkRoot } from './auth/ClerkRoot'
import { setTokenSource } from './services/api'
import { initTheme } from './theme/theme'

initTheme()
setTokenSource(() => getToken())

// Installs/updates the PWA service worker (static caching + push). Registration is idempotent
// with the one the notification settings perform, and notification PERMISSION is still only
// ever requested from the user's explicit button — never here.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => { navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => { /* unsupported or blocked: the app works without it */ }) })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ClerkRoot>
        <App />
      </ClerkRoot>
    </BrowserRouter>
  </StrictMode>,
)
