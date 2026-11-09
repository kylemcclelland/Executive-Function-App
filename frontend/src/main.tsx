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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ClerkRoot>
        <App />
      </ClerkRoot>
    </BrowserRouter>
  </StrictMode>,
)
