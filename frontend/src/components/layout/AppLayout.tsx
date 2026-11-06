import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { CalendarDays, Feather, FolderOpen, Inbox, Library, ListTodo, NotebookPen, Settings2, Sun } from 'lucide-react'

const navigation = [
  { path: '/', label: 'Today', icon: Sun }, { path: '/inbox', label: 'Inbox', icon: Inbox },
  { path: '/tasks', label: 'Tasks', icon: ListTodo }, { path: '/calendar', label: 'Calendar', icon: CalendarDays },
  { path: '/projects', label: 'Projects', icon: FolderOpen }, { path: '/library', label: 'Library', icon: Library }, { path: '/notes', label: 'Notes', icon: NotebookPen },
]

export function AppLayout({ children }: { children: ReactNode }) {
  return <div className="app-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <Link to="/" className="brand"><span className="brand-mark"><Feather size={21} strokeWidth={1.6} /></span><span>studium<span className="brand-period">.</span></span></Link>
      <p className="brand-caption">Age quod agis</p>
      <nav aria-label="Main navigation">
        {navigation.map(({ path, label, icon: Icon }) => <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          <Icon size={19} strokeWidth={1.6} /><span>{label}</span>{['Calendar'].includes(label) && <span className="nav-later">soon</span>}
        </NavLink>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-note"><span>A place for<br />purposeful living.</span><Feather size={22} strokeWidth={1.2} /></div>
        <NavLink className="nav-link" to="/settings" aria-label="Preferences"><Settings2 size={18} /><span>Preferences</span></NavLink>
        <div className="profile"><span className="avatar">L</span><div><strong>Your study</strong><small>Single-user development mode</small></div></div>
      </div>
    </aside>
    <main id="main" className="main-content">
      <div className="topline"><span>A PLACE FOR PURPOSEFUL LIVING</span><span className="topline-right"><span className="status-dot" /> Local workspace</span></div>
      {children}
      <footer className="page-footer"><Feather size={13} /> Age quod agis. Do what you are doing.</footer>
    </main>
  </div>
}
