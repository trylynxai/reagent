import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, ChevronDown } from 'lucide-react';
import SearchBar from './SearchBar.jsx';

const PROJECTS = ['All Projects', 'prod-agents', 'dev-tools', 'analytics', 'research', 'ecommerce', 'sales', 'marketing'];

export default function Header() {
  const navigate = useNavigate();
  const [project, setProject] = useState('All Projects');
  const [showProjectMenu, setShowProjectMenu] = useState(false);

  return (
    <header className="h-14 flex-shrink-0 flex items-center justify-between px-4 border-b border-prd-border bg-prd-surface">
      <div className="flex items-center gap-3">
        <Activity className="w-5 h-5 text-prd-tool" />
        <span className="text-base font-semibold text-white tracking-tight">ReAgent</span>
      </div>

      <div className="flex-1 flex justify-center px-8">
        <SearchBar
          placeholder="Search runs, errors, tags..."
          onSubmit={(q) => q && navigate(`/search?q=${encodeURIComponent(q)}`)}
        />
      </div>

      <div className="relative">
        <button
          onClick={() => setShowProjectMenu(!showProjectMenu)}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-prd-text-secondary hover:text-prd-text-primary bg-prd-bg border border-prd-border rounded-md transition-colors"
        >
          {project}
          <ChevronDown className="w-3.5 h-3.5" />
        </button>
        {showProjectMenu && (
          <div className="absolute right-0 top-full mt-1 w-48 bg-prd-surface border border-prd-border rounded-md shadow-xl z-50 py-1">
            {PROJECTS.map((p) => (
              <button
                key={p}
                onClick={() => { setProject(p); setShowProjectMenu(false); }}
                className={`w-full text-left px-3 py-1.5 text-sm hover:bg-prd-bg transition-colors ${
                  p === project ? 'text-prd-tool' : 'text-prd-text-secondary'
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        )}
      </div>
    </header>
  );
}
