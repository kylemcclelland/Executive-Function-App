import type { ReactNode } from 'react'
import { Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Feather } from 'lucide-react'
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
import { CalendarPage } from './pages/CalendarPage'
import { DevotionLibraryPage } from './pages/DevotionLibraryPage'
import { DevotionPage } from './pages/DevotionPage'
import { DevotionPreviewPage } from './pages/DevotionPreviewPage'
import { DivineOfficePage } from './pages/DivineOfficePage'
import { SavedOfficePage } from './pages/SavedOfficePage'
import { RuleOfLifePage } from './pages/RuleOfLifePage'
import { SignInPage, SignUpPage } from './auth/AuthPages'
import { RequireAuth } from './auth/RequireAuth'
import { AccountControls } from './auth/AccountControls'

const client = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true } } })

export function AppRoutes({ profile }: { profile?: ReactNode }) {
  return <AppLayout profile={profile}>
    <Routes>
      <Route path="/" element={<TodayPage />} />
      <Route path="/inbox" element={<InboxPage />} />
      <Route path="/tasks" element={<TasksPage />} />
      <Route path="/calendar" element={<CalendarPage />} />
      <Route path="/projects" element={<ProjectsPage />} />
      <Route path="/projects/:projectId" element={<ProjectPage />} />
      <Route path="/session" element={<WorkSessionPage />} />
      <Route path="/library" element={<LibraryPage />} />
      <Route path="/library/:bookId" element={<LibraryPage />} />
      <Route path="/notes" element={<NotesPage />} />
      <Route path="/notes/:noteId" element={<NotesPage />} />
      <Route path="/devotions" element={<DevotionLibraryPage />} />
      <Route path="/devotions/preview/:kind?" element={<DevotionPreviewPage />} />
      <Route path="/divine-office" element={<DivineOfficePage />} />
      <Route path="/divine-office/saved/:id" element={<SavedOfficePage />} />
      <Route path="/rule-of-life" element={<RuleOfLifePage />} />
      <Route path="/devotions/:slug" element={<DevotionPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<FuturePage name="Page not found" icon={Feather} description="That page doesn’t exist. Head back to Today." />} />
    </Routes>
  </AppLayout>
}

/** Rendered inside the router and ClerkProvider supplied by main.tsx. */
export default function App() {
  return <QueryClientProvider client={client}>
    <Routes>
      <Route path="/sign-in/*" element={<SignInPage />} />
      <Route path="/sign-up/*" element={<SignUpPage />} />
      <Route path="*" element={<RequireAuth><AppRoutes profile={<AccountControls />} /></RequireAuth>} />
    </Routes>
  </QueryClientProvider>
}
