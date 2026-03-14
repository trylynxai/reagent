import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  ListOrdered,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { fetchRuns, fetchFailureStats } from '../api/client.js';
import Header from '../components/Header.jsx';
import StatsCard from '../components/StatsCard.jsx';
import StatusBadge from '../components/StatusBadge.jsx';

const PAGE_SIZE = 25;

const CATEGORY_COLORS = {
  tool_error: '#f97316',
  rate_limit: '#eab308',
  context_overflow: '#a855f7',
  tool_timeout: '#ef4444',
  authentication: '#ec4899',
  validation: '#06b6d4',
  network: '#64748b',
  unknown: '#6b7280',
};

function categoryColor(cat) {
  return CATEGORY_COLORS[cat] || CATEGORY_COLORS.unknown;
}

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

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-slate-300 mb-1">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} style={{ color: entry.color }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  );
}

function RunTable({ runs, onRowClick, loading }) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 6 }).map((_, i) => (
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
        <p>No failed runs found</p>
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
              Failure Category
            </th>
            <th className="px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">
              Project
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
              <td className="px-4 py-3">
                {run.failure_category ? (
                  <span
                    className="text-xs px-2 py-0.5 rounded"
                    style={{
                      backgroundColor: categoryColor(run.failure_category) + '20',
                      color: categoryColor(run.failure_category),
                    }}
                  >
                    {run.failure_category}
                  </span>
                ) : (
                  <span className="text-slate-500">-</span>
                )}
              </td>
              <td className="px-4 py-3 text-slate-400">
                {run.project || '-'}
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

export default function Failures() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [failureStats, setFailureStats] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(
    parseInt(searchParams.get('page') || '1', 10)
  );
  const [projectFilter, setProjectFilter] = useState(
    searchParams.get('project') || ''
  );
  const [categoryFilter, setCategoryFilter] = useState(
    searchParams.get('category') || ''
  );
  const [projects, setProjects] = useState([]);
  const [categories, setCategories] = useState([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params = { status: 'failed' };
      if (projectFilter) params.project = projectFilter;
      if (categoryFilter) params.failure_category = categoryFilter;

      const [statsData, runsData] = await Promise.all([
        fetchFailureStats(projectFilter ? { project: projectFilter } : undefined),
        fetchRuns(params),
      ]);

      const list = Array.isArray(runsData) ? runsData : [];
      setFailureStats(statsData);
      setRuns(list);

      const projSet = new Set();
      const catSet = new Set();
      list.forEach((r) => {
        if (r.project) projSet.add(r.project);
        if (r.failure_category) catSet.add(r.failure_category);
      });
      setProjects([...projSet].sort());
      setCategories([...catSet].sort());
    } catch (err) {
      console.error('Failed to load failure data:', err);
    } finally {
      setLoading(false);
    }
  }, [projectFilter, categoryFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const params = {};
    if (projectFilter) params.project = projectFilter;
    if (categoryFilter) params.category = categoryFilter;
    if (page > 1) params.page = String(page);
    setSearchParams(params, { replace: true });
  }, [projectFilter, categoryFilter, page, setSearchParams]);

  const chartData = failureStats?.by_category
    ? Object.entries(failureStats.by_category).map(([category, count]) => ({
        category,
        count,
      }))
    : [];

  const topCategory =
    chartData.length > 0
      ? chartData.reduce((a, b) => (b.count > a.count ? b : a)).category
      : '-';

  const totalPages = Math.max(1, Math.ceil(runs.length / PAGE_SIZE));
  const pagedRuns = runs.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <>
      <Header title="Failures">
        <span className="text-sm text-slate-400">
          {failureStats?.total_failures ?? runs.length} total
        </span>
      </Header>
      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Stats row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {loading ? (
            <>
              <div className="h-20 bg-slate-800 border border-slate-700 rounded-lg animate-pulse" />
              <div className="h-20 bg-slate-800 border border-slate-700 rounded-lg animate-pulse" />
            </>
          ) : (
            <>
              <StatsCard
                title="Total Failures"
                value={failureStats?.total_failures ?? runs.length}
                icon={AlertTriangle}
                iconColor="bg-red-500/20 text-red-400"
              />
              <StatsCard
                title="Top Failure Category"
                value={topCategory}
                icon={AlertTriangle}
                iconColor="bg-orange-500/20 text-orange-400"
              />
            </>
          )}
        </div>

        {/* Failure chart */}
        {!loading && chartData.length > 0 && (
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
            <h2 className="text-sm font-semibold text-slate-300 mb-4">
              Failure Categories
            </h2>
            <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 40)}>
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 0, right: 20, bottom: 0, left: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#334155"
                  horizontal={false}
                />
                <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <YAxis
                  type="category"
                  dataKey="category"
                  width={130}
                  tick={{ fill: '#94a3b8', fontSize: 12 }}
                />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.category}
                      fill={categoryColor(entry.category)}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={projectFilter}
            onChange={(e) => {
              setProjectFilter(e.target.value);
              setPage(1);
            }}
            aria-label="Project filter"
            className="bg-slate-800 border border-slate-700 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Projects</option>
            {projects.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <select
            value={categoryFilter}
            onChange={(e) => {
              setCategoryFilter(e.target.value);
              setPage(1);
            }}
            aria-label="Category filter"
            className="bg-slate-800 border border-slate-700 rounded-lg text-sm text-white px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        {/* Failed runs table */}
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
