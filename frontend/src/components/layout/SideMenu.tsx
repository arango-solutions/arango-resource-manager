import {
  Activity,
  Boxes,
  Container,
  Database,
  Gauge,
  LayoutDashboard,
  Settings,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'

const ITEMS = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/services', label: 'Services', icon: Boxes },
  { to: '/pods', label: 'Pods', icon: Container },
  { to: '/capacity', label: 'Capacity', icon: Gauge },
  { to: '/database', label: 'Database', icon: Database },
  { to: '/activity', label: 'Activity', icon: Activity },
  { to: '/settings', label: 'Settings', icon: Settings },
]

interface Props {
  healthy: boolean | null
}

export default function SideMenu({ healthy }: Props) {
  return (
    <nav className="flex w-16 shrink-0 flex-col items-center bg-skin py-3">
      <img src="/avocado.svg" alt="Arango Resource Manager" className="mb-4 h-7 w-7" />

      <ul className="flex w-full flex-1 flex-col items-center gap-1">
        {ITEMS.map(({ to, label, icon: Icon, end }) => (
          <li key={to} className="w-full px-1.5">
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                [
                  'relative flex flex-col items-center gap-1 rounded-md py-2',
                  'text-[10px] leading-none text-flesh-pale transition-colors',
                  isActive ? 'bg-skin-soft' : 'hover:bg-skin-soft/70',
                ].join(' ')
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span className="absolute top-1 bottom-1 -left-1.5 w-[3px] rounded-r bg-flesh" />
                  )}
                  <Icon size={18} strokeWidth={1.75} aria-hidden />
                  <span>{label}</span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>

      <span
        className="mt-3 h-2 w-2 rounded-full"
        style={{
          backgroundColor:
            healthy === null ? '#9a9a9a' : healthy ? 'var(--color-flesh)' : 'var(--color-pit)',
        }}
        title={
          healthy === null
            ? 'Checking the namespace…'
            : healthy
              ? 'Connected to the namespace.'
              : 'Cannot reach the namespace.'
        }
      />
    </nav>
  )
}
