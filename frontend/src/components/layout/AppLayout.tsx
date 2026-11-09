import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { CalendarDays, Feather, FolderOpen, Inbox, Library, ListTodo, NotebookPen, Settings2, Sun } from 'lucide-react'
import { SidebarBrand } from '../brand/Brand'
import { ThemeToggle } from '../brand/ThemeToggle'

const navigation = [
  { path: '/', label: 'Today', icon: Sun }, { path: '/inbox', label: 'Inbox', icon: Inbox },
  { path: '/tasks', label: 'Tasks', icon: ListTodo }, { path: '/calendar', label: 'Calendar', icon: CalendarDays },
  { path: '/projects', label: 'Projects', icon: FolderOpen }, { path: '/library', label: 'Library', icon: Library }, { path: '/notes', label: 'Notes', icon: NotebookPen },
]

export function AppLayout({ children, profile }: { children: ReactNode; profile?: ReactNode }) {
  return <div className="app-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <Link to="/" className="brand" aria-label="Optima Pars, Unum est necessarium. Go to Today"><SidebarBrand /></Link>
      <nav aria-label="Main navigation">
        {navigation.map(({ path, label, icon: Icon }) => <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          <Icon size={19} strokeWidth={1.6} /><span>{label}</span>
        </NavLink>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-note"><span lang="la">Maria optimam partem elegit.<small>Luke 10:42</small></span><Feather size={22} strokeWidth={1.2} /></div>
        <NavLink className="nav-link" to="/settings" aria-label="Preferences"><Settings2 size={18} /><span>Preferences</span></NavLink>
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
