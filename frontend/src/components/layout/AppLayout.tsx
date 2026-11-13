import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { BookOpenCheck, CalendarDays, Cross, Feather, FolderOpen, Inbox, Library, ListTodo, NotebookPen, ScrollText, Settings2, SquareKanban, Sun } from 'lucide-react'
import { SidebarBrand } from '../brand/Brand'
import { ThemeToggle } from '../brand/ThemeToggle'
import { useEditorialAccess } from '../../lib/editorial'

const navigation = [
  { path: '/', label: 'Today', icon: Sun }, { path: '/inbox', label: 'Idea Wall', icon: Inbox },
  { path: '/tasks', label: 'Daily Checklist', icon: ListTodo }, { path: '/board', label: 'Task Board', icon: SquareKanban }, { path: '/calendar', label: 'Calendar', icon: CalendarDays },
  { path: '/projects', label: 'Projects', icon: FolderOpen }, { path: '/library', label: 'Library', icon: Library }, { path: '/notes', label: 'Notes', icon: NotebookPen },
  { path: '/devotions', label: 'The Oratory', icon: Cross }, { path: '/rule-of-life', label: 'Rule of Life', icon: ScrollText },
]

/** The owner's private review desk. Hidden unless the server confirms this account is the owner;
 * the server is the real boundary — this only keeps the link out of other users' sidebars. */
function EditorialNavLink() {
  const access = useEditorialAccess()
  if (access.data !== true) return null
  return <NavLink to="/editorial" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
    <BookOpenCheck size={19} strokeWidth={1.6} /><span>Editorial</span>
  </NavLink>
}

export function AppLayout({ children, profile }: { children: ReactNode; profile?: ReactNode }) {
  return <div className="app-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <Link to="/" className="brand" aria-label="Optima Pars, Unum est necessarium. Go to Today"><SidebarBrand /></Link>
      <nav aria-label="Main navigation">
        {navigation.map(({ path, label, icon: Icon }) => <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          <Icon size={19} strokeWidth={1.6} /><span>{label}</span>
        </NavLink>)}
        <EditorialNavLink />
        <NavLink to="/settings" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}><Settings2 size={19} strokeWidth={1.6} /><span>Preferences</span></NavLink>
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-note"><span lang="la">Maria optimam partem elegit.<small>Luke 10:42</small></span><Feather size={22} strokeWidth={1.2} /></div>
        {profile}
      </div>
    </aside>
    <main id="main" className="main-content">
      <div className="topline"><span>ONE THING IS NECESSARY</span><span className="topline-right"><span className="status-dot" /> Local workspace<ThemeToggle /></span></div>
      {children}
      <footer className="page-footer"><Feather size={13} /> <span lang="la">Unum est necessarium.</span> One thing is necessary.</footer>
    </main>
  </div>
}
