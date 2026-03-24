import { useState, useCallback, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Search as SearchIcon, ListOrdered, Loader2 } from 'lucide-react';
import { searchRuns } from '../api/client.js';
import { useAutoRefresh } from '../hooks/useAutoRefresh.js';
import StatusBadge from '../components/StatusBadge.jsx';

function formatDuration(ms) {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatCost(cost) {
  if (cost == null) return '-';
  return `$${Number(cost).toFixed(4)}`;
}

function formatTime(dateStr) {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString();
}

function RunTable({ runs, onRowClick }) {
  if (!runs?.length) {
    return (
      <div className="text-center py-16 text-prd-text-secondary">
        <ListOrdered className="w-10 h-10 mx-auto mb-3 opacity-40" />
        <p>No results found</p>
      </div>
    );
  }

  return (
    <div className="bg-prd-surface border border-prd-border rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-prd-border text-left">
            <th className="px-4 py-3 text-xs font-medium text-prd-text-secondary uppercase tracking-wider">Name</th>
            <th className="px-4 py-3 text-xs font-medium text-prd-text-secondary uppercase tracking-wider">Status</th>
            <th className="px-4 py-3 text-xs font-medium text-prd-text-secondary uppercase tracking-wider">Project</th>
            <th className="px-4 py-3 text-xs font-medium text-prd-text-secondary uppercase tracking-wider">Model</th>
            <th className="px-4 py-3 text-xs font-medium text-prd-text-secondary uppercase tracking-wider">Duration</th>
            <th className="px-4 py-3 text-xs font-medium text-prd-text-secondary uppercase tracking-wider">Cost</th>
            <th className="px-4 py-3 text-xs font-medium text-prd-text-secondary uppercase tracking-wider">Time</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-prd-border/50">
          {runs.map((run) => (
            <tr
              key={run.run_id}
              onClick={() => onRowClick(run.run_id)}
              className="hover:bg-prd-bg cursor-pointer transition-colors"
            >
              <td className="px-4 py-3 text-prd-text-primary font-medium truncate max-w-[200px]">{run.name || run.run_id}</td>
              <td className="px-4 py-3"><StatusBadge status={run.status} /></td>
              <td className="px-4 py-3 text-prd-text-secondary">{run.project || '-'}</td>
              <td className="px-4 py-3 text-prd-text-secondary">{run.model || '-'}</td>
              <td className="px-4 py-3 text-prd-text-secondary">{formatDuration(run.duration_ms)}</td>
              <td className="px-4 py-3 text-prd-text-secondary">{formatCost(run.total_cost_usd)}</td>
              <td className="px-4 py-3 text-prd-text-secondary text-xs">{formatTime(run.start_time)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Search() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [query, setQuery] = useState(searchParams.get('q') || '');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [lastSearchedQuery, setLastSearchedQuery] = useState(null);

  const handleSearch = useCallback(
    async (searchQuery = query) => {
      const trimmed = (searchQuery || query).trim();
      if (!trimmed) return;

      setLoading(true);
      setSearched(true);
      setLastSearchedQuery(trimmed);
      try {
        const data = await searchRuns(trimmed);
        setResults(Array.isArray(data) ? data : []);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
      return trimmed;
    },
    [query]
  );

  const refreshSearch = useCallback(async () => {
    if (!lastSearchedQuery) return;
    setLoading(true);
    try {
      const data = await searchRuns(lastSearchedQuery);
      setResults(Array.isArray(data) ? data : []);
    } catch {
      // Silent fail on refresh
    } finally {
      setLoading(false);
    }
  }, [lastSearchedQuery]);

  useAutoRefresh(refreshSearch, 10000);

  // Auto-search if query param exists
  useEffect(() => {
    if (query) {
      handleSearch();
    }
  }, []);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-4 border-b border-prd-border bg-prd-surface">
        <h1 className="text-lg font-semibold text-prd-text-primary">Search</h1>
      </div>
      <div className="p-6 space-y-6">
        <form onSubmit={handleSearch} className="max-w-2xl mx-auto">
          <div className="relative">
            <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-prd-text-secondary" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search runs..."
              className="w-full pl-12 pr-4 py-3.5 bg-prd-surface border border-prd-border rounded-xl text-base text-prd-text-primary placeholder-prd-text-secondary focus:outline-none focus:ring-2 focus:ring-prd-tool focus:border-transparent"
            />
            {loading && (
              <Loader2 className="absolute right-4 top-1/2 -translate-y-1/2 w-5 h-5 text-prd-text-secondary animate-spin" />
            )}
          </div>
        </form>

        {!searched && (
          <div className="text-center space-y-4 pt-8">
            <p className="text-sm text-prd-text-secondary">Search by run name, tags, or error messages</p>
            <p className="text-sm text-prd-text-secondary/60">Enter a query to search across all runs</p>
          </div>
        )}

        {searched && !loading && (
          <div className="space-y-3">
            <p className="text-sm text-prd-text-secondary">
              {results?.length ?? 0} result{results?.length !== 1 ? 's' : ''} found
            </p>
            <RunTable runs={results} onRowClick={(id) => navigate(`/trace/${id}`)} />
          </div>
        )}

        {loading && (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-12 bg-prd-surface border border-prd-border rounded animate-pulse" />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
