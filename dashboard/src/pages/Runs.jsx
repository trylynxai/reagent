import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ListOrdered, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { fetchRuns } from '../api/client.js';
import Header from '../components/Header.jsx';
import StatusBadge from '../components/StatusBadge.jsx';

const PAGE_SIZE = 25;

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

function SearchBar({ value, onChange, placeholder }) {
  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder || 'Search runs...'}
        className="w-full pl-10 pr-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
      />
    </div>
  );
}

function FilterSelect({ label, value, onChange, options }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={label}
      className="bg-slate-800 border border-slate-700 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}

function RunTable({ runs, onRowClick, loading }) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="h-12 bg-slate-800 border border-slate-700 rounded animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (!runs?.length) {
    return (
      <div className="text-center py-16 text-slate-500">
        <ListOrdered className="w-10 h-10 mx-auto mb-3 opacity-40" />
        <p>No runs found</p>
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
              Tokens
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
                {run.total_tokens?.toLocaleString() ?? '-'}
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

export default function Runs() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [runs, setRuns] = useState([]);
  const [allRuns, setAllRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(
    parseInt(searchParams.get('page') || '1', 10)
  );
  const [searchText, setSearchText] = useState(
    searchParams.get('q') || ''
  );
  const [statusFilter, setStatusFilter] = useState(
    searchParams.get('status') || ''
  );
  const [projectFilter, setProjectFilter] = useState(
    searchParams.get('project') || ''
  );
  const [modelFilter, setModelFilter] = useState(
    searchParams.get('model') || ''
  );

  // Unique projects and models derived from all runs
  const [projects, setProjects] = useState([]);
  const [models, setModels] = useState([]);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (projectFilter) params.project = projectFilter;
      if (modelFilter) params.model = modelFilter;

      const data = await fetchRuns(params);
      const list = Array.isArray(data) ? data : [];
      setAllRuns(list);

      // Extract unique projects and models
      const projSet = new Set();
      const modelSet = new Set();
      list.forEach((r) => {
        if (r.project) projSet.add(r.project);
        if (r.model) modelSet.add(r.model);
      });
      setProjects([...projSet].sort());
      setModels([...modelSet].sort());
    } catch (err) {
      console.error('Failed to fetch runs:', err);
      setAllRuns([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, projectFilter, modelFilter]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  // Apply text search filter client-side
  useEffect(() => {
    let filtered = allRuns;
    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      filtered = allRuns.filter(
        (r) =>
          (r.name && r.name.toLowerCase().includes(q)) ||
          (r.run_id && r.run_id.toLowerCase().includes(q)) ||
          (r.project && r.project.toLowerCase().includes(q)) ||
          (r.tags && r.tags.some((t) => t.toLowerCase().includes(q)))
      );
    }
    setRuns(filtered);
    setPage(1);
  }, [allRuns, searchText]);

  // Sync filters to URL
  useEffect(() => {
    const params = {};
    if (statusFilter) params.status = statusFilter;
    if (projectFilter) params.project = projectFilter;
    if (modelFilter) params.model = modelFilter;
    if (searchText) params.q = searchText;
    if (page > 1) params.page = String(page);
    setSearchParams(params, { replace: true });
  }, [statusFilter, projectFilter, modelFilter, searchText, page, setSearchParams]);

  const totalPages = Math.max(1, Math.ceil(runs.length / PAGE_SIZE));
  const pagedRuns = runs.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <>
      <Header title="Runs">
        <span className="text-sm text-slate-400">
          {runs.length} run{runs.length !== 1 ? 's' : ''}
        </span>
      </Header>
      <main className="flex-1 overflow-y-auto p-6 space-y-4">
        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-3">
          <FilterSelect
            label="Project"
            value={projectFilter}
            onChange={setProjectFilter}
            options={[
              { value: '', label: 'All Projects' },
              ...projects.map((p) => ({ value: p, label: p })),
            ]}
          />
          <FilterSelect
            label="Status"
            value={statusFilter}
            onChange={setStatusFilter}
            options={[
              { value: '', label: 'All Statuses' },
              { value: 'completed', label: 'Completed' },
              { value: 'failed', label: 'Failed' },
              { value: 'running', label: 'Running' },
            ]}
          />
          <FilterSelect
            label="Model"
            value={modelFilter}
            onChange={setModelFilter}
            options={[
              { value: '', label: 'All Models' },
              ...models.map((m) => ({ value: m, label: m })),
            ]}
          />
          <div className="flex-1 min-w-[200px]">
            <SearchBar
              value={searchText}
              onChange={setSearchText}
              placeholder="Filter by name, ID, or tags..."
            />
          </div>
        </div>

        {/* Run table */}
        <RunTable
          runs={pagedRuns}
          onRowClick={(id) => navigate(`/runs/${id}`)}
          loading={loading}
        />

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between pt-2">
            <p className="text-sm text-slate-500">
              Page {page} of {totalPages}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </main>
    </>
  );
}
