import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BookOpen, CalendarDays, FolderOpen, Leaf } from 'lucide-react'
import { AppLayout } from './components/layout/AppLayout'
import { TodayPage } from './pages/TodayPage'
import { InboxPage } from './pages/InboxPage'
import { TasksPage } from './pages/TasksPage'
import { FuturePage } from './pages/FuturePage'
import { SettingsPage } from './pages/SettingsPage'

const client = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true } } })

export function AppRoutes() {
  return <AppLayout>
    <Routes>
      <Route path="/" element={<TodayPage />} />
      <Route path="/inbox" element={<InboxPage />} />
      <Route path="/tasks" element={<TasksPage />} />
      <Route path="/calendar" element={<FuturePage name="Calendar" icon={CalendarDays} description="A calmer view of your time, with room for both doing and breathing. For now, you can set due and scheduled dates on your tasks." />} />
      <Route path="/projects" element={<FuturePage name="Projects" icon={FolderOpen} description="A home for the bigger picture, broken into smaller, kinder steps. For now, keep your next actions in Tasks." />} />
      <Route path="/notes" element={<FuturePage name="Notes & Books" icon={BookOpen} description="A thoughtful place for ideas worth keeping, notes worth returning to, and books along the way. Capture thoughts in your inbox for now." />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<FuturePage name="This path is a little quiet" icon={Leaf} description="We couldn’t find that page. Your Today page is a good place to begin again." />} />
    </Routes>
  </AppLayout>
}

export default function App() {
  return <QueryClientProvider client={client}><BrowserRouter><AppRoutes /></BrowserRouter></QueryClientProvider>
}
