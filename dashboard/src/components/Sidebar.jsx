import { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Activity,
  LayoutDashboard,
  ListOrdered,
  AlertTriangle,
  Search,
} from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/runs', icon: ListOrdered, label: 'Runs' },
  { to: '/failures', icon: AlertTriangle, label: 'Failures' },
  { to: '/search', icon: Search, label: 'Search' },
];

export default function Sidebar() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function checkHealth() {
      try {
        const res = await fetch('/health');
        if (!cancelled) {
          setHealth(res.ok ? 'connected' : 'disconnected');
        }
      } catch {
        if (!cancelled) {
          setHealth('disconnected');
        }
      }
    }

    checkHealth();
    return () => { cancelled = true; };
  }, []);

  return (
    <aside className="w-64 h-screen flex-shrink-0 bg-slate-900 border-r border-slate-700 flex flex-col">
      {/* Logo */}
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-slate-700">
        <Activity className="w-6 h-6 text-blue-500" />
        <span className="text-lg font-semibold tracking-tight text-white">
          ReAgent
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-slate-800 text-blue-400 border-l-2 border-blue-400 pl-[10px]'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`
            }
          >
            <Icon className="w-5 h-5 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Bottom section */}
      <div className="px-5 pb-4 space-y-3 border-t border-slate-700 pt-4">
        {/* Health indicator */}
        <div className="flex items-center gap-2 text-sm">
          <span
            className={`w-2 h-2 rounded-full ${
              health === 'connected'
                ? 'bg-green-400'
                : health === 'disconnected'
                ? 'bg-red-400'
                : 'bg-slate-500'
            }`}
          />
          <span className="text-slate-400">
            {health === 'connected'
              ? 'Connected'
              : health === 'disconnected'
              ? 'Disconnected'
              : 'Checking...'}
          </span>
        </div>

        {/* Version */}
        <p className="text-xs text-slate-500">v0.1.0</p>
      </div>
    </aside>
  );
}
