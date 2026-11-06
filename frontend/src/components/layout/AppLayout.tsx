import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { BookOpen, CalendarDays, FolderOpen, Inbox, Leaf, ListTodo, Settings2, Sun } from 'lucide-react'

const navigation = [
  { path: '/', label: 'Today', icon: Sun }, { path: '/inbox', label: 'Inbox', icon: Inbox },
  { path: '/tasks', label: 'Tasks', icon: ListTodo }, { path: '/calendar', label: 'Calendar', icon: CalendarDays },
  { path: '/projects', label: 'Projects', icon: FolderOpen }, { path: '/notes', label: 'Notes & Books', icon: BookOpen },
]

export function AppLayout({ children }: { children: ReactNode }) {
  return <div className="app-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <Link to="/" className="brand"><span className="brand-mark"><Leaf size={25} strokeWidth={1.5} /></span><span>still<span className="brand-period">.</span></span></Link>
      <p className="brand-caption">A little space for your mind.</p>
      <nav aria-label="Main navigation">
        {navigation.map(({ path, label, icon: Icon }) => <NavLink key={path} to={path} end={path === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          <Icon size={19} strokeWidth={1.6} /><span>{label}</span>{['Calendar', 'Projects', 'Notes & Books'].includes(label) && <span className="nav-later">soon</span>}
        </NavLink>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-note"><span>Less noise.<br />More room for you.</span><Leaf size={24} strokeWidth={1} /></div>
        <NavLink className="nav-link" to="/settings" aria-label="Preferences"><Settings2 size={18} /><span>Preferences</span></NavLink>
        <div className="profile"><span className="avatar">Y</span><div><strong>Your quiet corner</strong><small>One day at a time</small></div></div>
      </div>
    </aside>
    <main id="main" className="main-content">
      <div className="topline"><span>YOUR SPACE TO SLOW DOWN & MOVE FORWARD</span><span className="topline-right"><span className="status-dot" /> A fresh perspective</span></div>
      {children}
      <footer className="page-footer"><Leaf size={13} /> A little clarity. A little kindness. One thing at a time.</footer>
    </main>
  </div>
}
