import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CalendarDays, Feather } from 'lucide-react'
import { AppLayout } from './components/layout/AppLayout'
import { TodayPage } from './pages/TodayPage'
import { InboxPage } from './pages/InboxPage'
import { TasksPage } from './pages/TasksPage'
import { FuturePage } from './pages/FuturePage'
import { SettingsPage } from './pages/SettingsPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { ProjectPage } from './pages/ProjectPage'
import { WorkSessionPage } from './pages/WorkSessionPage'
import { LibraryPage } from './pages/LibraryPage'
import { NotesPage } from './pages/NotesPage'

const client = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true } } })

export function AppRoutes() {
  return <AppLayout>
    <Routes>
      <Route path="/" element={<TodayPage />} />
      <Route path="/inbox" element={<InboxPage />} />
      <Route path="/tasks" element={<TasksPage />} />
      <Route path="/calendar" element={<FuturePage name="Calendar" icon={CalendarDays} description="A calmer view of your time, with room for both doing and breathing. For now, you can set due and scheduled dates on your tasks." />} />
      <Route path="/projects" element={<ProjectsPage />} />
      <Route path="/projects/:projectId" element={<ProjectPage />} />
      <Route path="/session" element={<WorkSessionPage />} />
      <Route path="/library" element={<LibraryPage />} />
      <Route path="/library/:bookId" element={<LibraryPage />} />
      <Route path="/notes" element={<NotesPage />} />
      <Route path="/notes/:noteId" element={<NotesPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<FuturePage name="Page not found" icon={Feather} description="That page doesn’t exist. Head back to Today." />} />
    </Routes>
  </AppLayout>
}

export default function App() {
  return <QueryClientProvider client={client}><BrowserRouter><AppRoutes /></BrowserRouter></QueryClientProvider>
}
