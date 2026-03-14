import { NavLink, useParams } from 'react-router-dom';
import {
  LayoutDashboard,
  ListOrdered,
  AlertTriangle,
  Search,
  GitBranch,
  Play,
} from 'lucide-react';

export default function Sidebar() {
  const { runId } = useParams();

  const navItems = [
    { to: '/runs', icon: ListOrdered, label: 'Runs' },
    ...(runId ? [
      { to: `/trace/${runId}`, icon: GitBranch, label: 'Trace' },
      { to: `/replay/${runId}`, icon: Play, label: 'Replay' },
    ] : []),
    { to: '/', icon: LayoutDashboard, label: 'Overview', end: true },
    { to: '/failures', icon: AlertTriangle, label: 'Failures' },
    { to: '/search', icon: Search, label: 'Search' },
  ];

  return (
    <aside className="w-52 h-full flex-shrink-0 bg-prd-surface border-r border-prd-border flex flex-col">
      <nav className="flex-1 py-3 px-2 space-y-0.5">
        {navItems.map(({ to, icon: Icon, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-prd-bg text-prd-tool'
                  : 'text-prd-text-secondary hover:bg-prd-bg hover:text-prd-text-primary'
              }`
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
