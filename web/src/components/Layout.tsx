import { NavLink, Outlet } from 'react-router-dom'
import { ThemeToggle } from './ThemeToggle'

const NAV_ITEMS = [
  { to: '/', label: 'Inbox', end: true },
  { to: '/week', label: 'This Week' },
  { to: '/backlog', label: 'Backlog' },
]

function navClass({ isActive }: { isActive: boolean }) {
  return `whitespace-nowrap border-b-2 px-1 pb-2.5 pt-1 text-sm transition ${
    isActive
      ? 'border-sage text-ink font-medium'
      : 'border-transparent text-ink-soft hover:text-ink hover:border-hairline'
  }`
}

export function Layout() {
  return (
    <div className="paper-grain min-h-screen bg-paper text-ink">
      <header className="sticky top-0 z-10 border-b border-hairline bg-paper/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 pt-4 sm:px-6">
          <div className="flex items-baseline gap-2">
            <span className="font-serif text-lg font-semibold tracking-tight">Skinstinct</span>
            <span className="hidden font-mono text-[11px] text-ink-faint sm:inline">drafting studio</span>
          </div>
          <ThemeToggle />
        </div>
        <nav className="mx-auto flex max-w-5xl gap-5 overflow-x-auto px-4 sm:px-6">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
    </div>
  )
}
