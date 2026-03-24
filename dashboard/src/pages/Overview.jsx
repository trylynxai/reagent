import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  CheckCircle,
  Coins,
  Hash,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { fetchStats, fetchRuns, fetchFailureStats } from '../api/client.js';
import { useAutoRefresh } from '../hooks/useAutoRefresh.js';
import StatsCard from '../components/StatsCard.jsx';
import StatusBadge from '../components/StatusBadge.jsx';

const CATEGORY_COLORS = {
  tool_error: '#f97316',
  rate_limit: '#eab308',
  context_overflow: '#a371f7',
  tool_timeout: '#f85149',
  authentication: '#ec4899',
  validation: '#06b6d4',
  network: '#8b949e',
  unknown: '#8b949e',
};

function categoryColor(category) {
  return CATEGORY_COLORS[category] || CATEGORY_COLORS.unknown;
}

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function formatCost(cost) {
  if (cost == null) return '$0.00';
  return `$${Number(cost).toFixed(4)}`;
}

function SkeletonCard() {
  return (
    <div className="bg-prd-surface border border-prd-border rounded-lg p-5 animate-pulse">
      <div className="h-4 bg-prd-border rounded w-24 mb-3" />
      <div className="h-7 bg-prd-border rounded w-16" />
    </div>
  );
}

function SkeletonRow() {
  return (
    <div className="flex items-center gap-4 py-3 animate-pulse">
      <div className="h-4 bg-prd-border rounded w-32" />
      <div className="h-4 bg-prd-border rounded w-16" />
      <div className="h-4 bg-prd-border rounded w-12" />
      <div className="h-4 bg-prd-border rounded w-14 ml-auto" />
    </div>
  );
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-prd-surface border border-prd-border rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-prd-text-secondary mb-1">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} style={{ color: entry.color }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  );
}

export default function Overview() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [runs, setRuns] = useState(null);
  const [failureStats, setFailureStats] = useState(null);

  const loadOverviewData = async () => {
    const [statsData, runsData, failuresData] = await Promise.all([
      fetchStats(),
      fetchRuns({ limit: 30 }),
      fetchFailureStats(),
    ]);
    setStats(statsData);
    setRuns(runsData);
    setFailureStats(failuresData);
    return { stats: statsData, runs: runsData, failureStats: failuresData };
  };

  const { data, loading } = useAutoRefresh(loadOverviewData, 10000);

  const recentRuns = runs?.slice(0, 10) || [];

  const failureChartData = failureStats?.by_category
    ? Object.entries(failureStats.by_category).map(([category, count]) => ({
        category,
        count,
      }))
    : [];

  const activityData = (() => {
    if (!runs?.length) return [];
    const byDay = {};
    runs.forEach((run) => {
      const day = run.start_time
        ? new Date(run.start_time).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
          })
        : 'Unknown';
      if (!byDay[day]) byDay[day] = { day, completed: 0, failed: 0 };
      if (run.status === 'failed') {
        byDay[day].failed += 1;
      } else {
        byDay[day].completed += 1;
      }
    });
    return Object.values(byDay).reverse();
  })();

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-4 border-b border-prd-border bg-prd-surface">
        <h1 className="text-lg font-semibold text-prd-text-primary">Overview</h1>
      </div>
      <div className="p-6 space-y-6">
        {/* Stats Row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {loading ? (
            Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
          ) : (
            <>
              <StatsCard
                title="Total Runs"
                value={stats?.total_runs ?? 0}
                icon={Activity}
                iconColor="bg-prd-tool/20 text-prd-tool"
              />
              <StatsCard
                title="Success Rate"
                value={`${(stats?.success_rate != null ? (stats.success_rate * 100).toFixed(1) : '0')}%`}
                icon={CheckCircle}
                iconColor="bg-prd-retrieval/20 text-prd-retrieval"
              />
              <StatsCard
                title="Total Tokens"
                value={stats?.total_tokens?.toLocaleString() ?? 0}
                icon={Hash}
                iconColor="bg-prd-llm/20 text-prd-llm"
              />
              <StatsCard
                title="Total Cost"
                value={formatCost(stats?.total_cost_usd)}
                icon={Coins}
                iconColor="bg-yellow-500/20 text-yellow-400"
              />
            </>
          )}
        </div>

        {/* Second Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-prd-surface border border-prd-border rounded-lg p-5">
            <h2 className="text-sm font-semibold text-prd-text-secondary mb-4">
              Recent Runs
            </h2>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
            ) : recentRuns.length === 0 ? (
              <p className="text-sm text-prd-text-secondary py-8 text-center">
                No runs yet
              </p>
            ) : (
              <div className="space-y-1">
                {recentRuns.map((run) => (
                  <button
                    key={run.run_id}
                    onClick={() => navigate(`/trace/${run.run_id}`)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md hover:bg-prd-bg transition-colors text-left"
                  >
                    <span className="text-sm text-prd-text-primary truncate flex-1 min-w-0">
                      {run.name || run.run_id}
                    </span>
                    <StatusBadge status={run.status} />
                    <span className="text-xs text-prd-text-secondary flex-shrink-0 w-16 text-right">
                      {timeAgo(run.start_time)}
                    </span>
                    <span className="text-xs text-prd-text-secondary flex-shrink-0 w-16 text-right">
                      {formatCost(run.total_cost_usd)}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="bg-prd-surface border border-prd-border rounded-lg p-5">
            <h2 className="text-sm font-semibold text-prd-text-secondary mb-4">
              Failure Breakdown
            </h2>
            {loading ? (
              <div className="h-48 animate-pulse bg-prd-border/30 rounded" />
            ) : failureChartData.length === 0 ? (
              <p className="text-sm text-prd-text-secondary py-8 text-center">
                No failures
              </p>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart
                  data={failureChartData}
                  layout="vertical"
                  margin={{ top: 0, right: 20, bottom: 0, left: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#30363d" horizontal={false} />
                  <XAxis type="number" tick={{ fill: '#8b949e', fontSize: 12 }} />
                  <YAxis type="category" dataKey="category" width={120} tick={{ fill: '#8b949e', fontSize: 12 }} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                    {failureChartData.map((entry) => (
                      <Cell key={entry.category} fill={categoryColor(entry.category)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Run Activity */}
        <div className="bg-prd-surface border border-prd-border rounded-lg p-5">
          <h2 className="text-sm font-semibold text-prd-text-secondary mb-4">
            Run Activity
          </h2>
          {loading ? (
            <div className="h-56 animate-pulse bg-prd-border/30 rounded" />
          ) : activityData.length === 0 ? (
            <p className="text-sm text-prd-text-secondary py-8 text-center">
              No activity data
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={activityData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                <XAxis dataKey="day" tick={{ fill: '#8b949e', fontSize: 12 }} />
                <YAxis tick={{ fill: '#8b949e', fontSize: 12 }} allowDecimals={false} />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="completed" name="Completed" stackId="1" stroke="#3fb950" fill="#3fb950" fillOpacity={0.3} />
                <Area type="monotone" dataKey="failed" name="Failed" stackId="1" stroke="#f85149" fill="#f85149" fillOpacity={0.3} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
