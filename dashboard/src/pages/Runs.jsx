import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ListOrdered, ChevronLeft, ChevronRight, Search, Clock } from 'lucide-react';
import { fetchRuns } from '../api/client.js';
import { useAutoRefresh } from '../hooks/useAutoRefresh.js';
import RunCard from '../components/RunCard.jsx';

const PAGE_SIZE = 12;

const TIME_RANGES = [
  { value: '', label: 'All Time' },
  { value: '1h', label: 'Last Hour' },
  { value: '24h', label: 'Last 24h' },
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
];

export default function Runs() {
  const [searchParams, setSearchParams] = useSearchParams();

  const [runs, setRuns] = useState([]);
  const [allRuns, setAllRuns] = useState([]);
  const [page, setPage] = useState(parseInt(searchParams.get('page') || '1', 10));
  const [searchText, setSearchText] = useState(searchParams.get('q') || '');
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || '');
  const [projectFilter, setProjectFilter] = useState(searchParams.get('project') || '');
  const [modelFilter, setModelFilter] = useState(searchParams.get('model') || '');
  const [timeRange, setTimeRange] = useState(searchParams.get('time') || '');
  const [projects, setProjects] = useState([]);
  const [models, setModels] = useState([]);

  const loadRuns = useCallback(async () => {
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (projectFilter) params.project = projectFilter;
      if (modelFilter) params.model = modelFilter;

      const data = await fetchRuns(params);
      const list = Array.isArray(data) ? data : [];
      setAllRuns(list);

      const projSet = new Set();
      const modelSet = new Set();
      list.forEach((r) => {
        if (r.project) projSet.add(r.project);
        if (r.model) modelSet.add(r.model);
      });
      setProjects([...projSet].sort());
      setModels([...modelSet].sort());
      return list;
    } catch {
      setAllRuns([]);
      return [];
    }
  }, [statusFilter, projectFilter, modelFilter]);

  const { data, loading } = useAutoRefresh(loadRuns, 10000);

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
    if (timeRange) {
      const now = Date.now();
      const ms = timeRange === '1h' ? 3600000 : timeRange === '24h' ? 86400000 : timeRange === '7d' ? 604800000 : 2592000000;
      filtered = filtered.filter((r) => r.start_time && (now - new Date(r.start_time).getTime()) < ms);
    }
    setRuns(filtered);
    setPage(1);
  }, [allRuns, searchText, timeRange]);

  useEffect(() => {
    const params = {};
    if (statusFilter) params.status = statusFilter;
    if (projectFilter) params.project = projectFilter;
    if (modelFilter) params.model = modelFilter;
    if (searchText) params.q = searchText;
    if (timeRange) params.time = timeRange;
    if (page > 1) params.page = String(page);
    setSearchParams(params, { replace: true });
  }, [statusFilter, projectFilter, modelFilter, searchText, timeRange, page, setSearchParams]);

  const totalPages = Math.max(1, Math.ceil(runs.length / PAGE_SIZE));
  const pagedRuns = runs.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="flex-1 flex flex-col overflow-y-auto">
      <div className="p-4 border-b border-prd-border bg-prd-surface">
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-lg font-semibold text-prd-text-primary">Runs</h1>
          <span className="text-sm text-prd-text-secondary">{runs.length} run{runs.length !== 1 ? 's' : ''}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={projectFilter}
            onChange={(e) => setProjectFilter(e.target.value)}
            className="bg-prd-bg border border-prd-border rounded-md text-sm text-prd-text-primary px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-prd-tool"
          >
            <option value="">All Projects</option>
            {projects.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-prd-bg border border-prd-border rounded-md text-sm text-prd-text-primary px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-prd-tool"
          >
            <option value="">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="running">Running</option>
          </select>
          <select
            value={modelFilter}
            onChange={(e) => setModelFilter(e.target.value)}
            className="bg-prd-bg border border-prd-border rounded-md text-sm text-prd-text-primary px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-prd-tool"
          >
            <option value="">All Models</option>
            {models.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            className="bg-prd-bg border border-prd-border rounded-md text-sm text-prd-text-primary px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-prd-tool"
          >
            {TIME_RANGES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          <div className="flex-1 min-w-[200px] relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-prd-text-secondary" />
            <input
              type="text"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Filter by name, ID, or tags..."
              className="w-full pl-10 pr-4 py-1.5 bg-prd-bg border border-prd-border rounded-md text-sm text-prd-text-primary placeholder-prd-text-secondary focus:outline-none focus:ring-1 focus:ring-prd-tool"
            />
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-48 bg-prd-surface border border-prd-border rounded-lg animate-pulse" />
            ))}
          </div>
        ) : pagedRuns.length === 0 ? (
          <div className="text-center py-16 text-prd-text-secondary">
            <ListOrdered className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p>No runs found</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {pagedRuns.map((run) => (
              <RunCard key={run.run_id} run={run} />
            ))}
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex items-center justify-between pt-4 mt-4 border-t border-prd-border">
            <p className="text-sm text-prd-text-secondary">Page {page} of {totalPages}</p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-2 rounded-lg bg-prd-surface border border-prd-border text-prd-text-secondary hover:bg-prd-bg disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-2 rounded-lg bg-prd-surface border border-prd-border text-prd-text-secondary hover:bg-prd-bg disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
