import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search as SearchIcon, ListOrdered, Loader2 } from 'lucide-react';
import { searchRuns } from '../api/client.js';
import Header from '../components/Header.jsx';
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
      <div className="text-center py-16 text-slate-500">
        <ListOrdered className="w-10 h-10 mx-auto mb-3 opacity-40" />
        <p>No results found</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-700 text-left">
            <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
              Name
            </th>
            <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
              Status
            </th>
            <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
              Project
            </th>
            <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
              Model
            </th>
            <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
              Duration
            </th>
            <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
              Cost
            </th>
            <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
              Time
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-700/50">
          {runs.map((run) => (
            <tr
              key={run.run_id}
              onClick={() => onRowClick(run.run_id)}
              className="hover:bg-slate-700/30 cursor-pointer transition-colors"
            >
              <td className="px-4 py-3 text-white font-medium truncate max-w-[200px]">
                {run.name || run.run_id}
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={run.status} />
              </td>
              <td className="px-4 py-3 text-slate-400">
                {run.project || '-'}
              </td>
              <td className="px-4 py-3 text-slate-400">
                {run.model || '-'}
              </td>
              <td className="px-4 py-3 text-slate-400">
                {formatDuration(run.duration_ms)}
              </td>
              <td className="px-4 py-3 text-slate-400">
                {formatCost(run.total_cost_usd)}
              </td>
              <td className="px-4 py-3 text-slate-500 text-xs">
                {formatTime(run.start_time)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Search() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const handleSearch = useCallback(
    async (e) => {
      e?.preventDefault();
      const trimmed = query.trim();
      if (!trimmed) return;

      setLoading(true);
      setSearched(true);
      try {
        const data = await searchRuns(trimmed);
        setResults(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error('Search failed:', err);
        setResults([]);
      } finally {
        setLoading(false);
      }
    },
    [query]
  );

  return (
    <>
      <Header title="Search" />
      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Search bar */}
        <form onSubmit={handleSearch} className="max-w-2xl mx-auto">
          <div className="relative">
            <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search runs..."
              className="w-full pl-12 pr-4 py-3.5 bg-slate-800 border border-slate-700 rounded-xl text-base text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            {loading && (
              <Loader2 className="absolute right-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500 animate-spin" />
            )}
          </div>
        </form>

        {/* Search tips */}
        {!searched && (
          <div className="text-center space-y-4 pt-8">
            <p className="text-sm text-slate-500">
              Search by run name, tags, or error messages
            </p>
            <p className="text-sm text-slate-600">
              Enter a query to search across all runs
            </p>
          </div>
        )}

        {/* Results */}
        {searched && !loading && (
          <div className="space-y-3">
            <p className="text-sm text-slate-400">
              {results?.length ?? 0} result{results?.length !== 1 ? 's' : ''}{' '}
              found
            </p>
            <RunTable
              runs={results}
              onRowClick={(id) => navigate(`/runs/${id}`)}
            />
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-12 bg-slate-800 border border-slate-700 rounded animate-pulse"
              />
            ))}
          </div>
        )}
      </main>
    </>
  );
}
