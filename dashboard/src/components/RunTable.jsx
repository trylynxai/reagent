import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';
import StatusBadge from './StatusBadge';

function formatDuration(seconds) {
  if (seconds == null) return '-';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function formatCost(cost) {
  if (cost == null) return '-';
  return `$${cost.toFixed(4)}`;
}

function formatTokens(n) {
  if (n == null) return '-';
  return n.toLocaleString();
}

function formatRelativeTime(dateStr) {
  if (!dateStr) return '-';
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

const columns = [
  { key: 'status', label: 'Status', sortable: true },
  { key: 'name', label: 'Name', sortable: true },
  { key: 'project', label: 'Project', sortable: true },
  { key: 'model', label: 'Model', sortable: true },
  { key: 'total_steps', label: 'Steps', sortable: true },
  { key: 'total_tokens', label: 'Tokens', sortable: true },
  { key: 'total_cost', label: 'Cost', sortable: true },
  { key: 'duration', label: 'Duration', sortable: true },
  { key: 'start_time', label: 'Time', sortable: true },
];

function SortIcon({ column, sortBy, sortOrder }) {
  if (sortBy !== column) {
    return <ChevronsUpDown className="w-3.5 h-3.5 text-slate-500" />;
  }
  return sortOrder === 'asc' ? (
    <ChevronUp className="w-3.5 h-3.5 text-blue-400" />
  ) : (
    <ChevronDown className="w-3.5 h-3.5 text-blue-400" />
  );
}

function SkeletonRow() {
  return (
    <tr className="border-b border-slate-700/50">
      {columns.map((col) => (
        <td key={col.key} className="px-4 py-3">
          <div className="h-4 bg-slate-700 rounded animate-pulse w-3/4" />
        </td>
      ))}
    </tr>
  );
}

export default function RunTable({
  runs = [],
  onSort,
  sortBy,
  sortOrder,
  onRunClick,
  loading = false,
}) {
  if (!loading && runs.length === 0) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-12 text-center">
        <p className="text-slate-400 text-sm">No runs found.</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead>
            <tr className="border-b border-slate-700 bg-slate-800">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`px-4 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider whitespace-nowrap ${
                    col.sortable
                      ? 'cursor-pointer select-none hover:text-slate-200 transition-colors'
                      : ''
                  }`}
                  onClick={() => col.sortable && onSort?.(col.key)}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.label}
                    {col.sortable && (
                      <SortIcon
                        column={col.key}
                        sortBy={sortBy}
                        sortOrder={sortOrder}
                      />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 8 }).map((_, i) => (
                  <SkeletonRow key={i} />
                ))
              : runs.map((run, idx) => (
                  <tr
                    key={run.run_id || idx}
                    onClick={() => onRunClick?.(run)}
                    className={`border-b border-slate-700/50 cursor-pointer transition-colors hover:bg-slate-700/50 ${
                      idx % 2 === 0 ? 'bg-slate-800' : 'bg-slate-800/60'
                    }`}
                  >
                    <td className="px-4 py-3">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-4 py-3 text-white font-medium max-w-[200px] truncate">
                      {run.name || run.run_id || '-'}
                    </td>
                    <td className="px-4 py-3 text-slate-300 max-w-[140px] truncate">
                      {run.project || '-'}
                    </td>
                    <td className="px-4 py-3 text-slate-300 max-w-[140px] truncate">
                      {run.model || '-'}
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {run.total_steps ?? '-'}
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {formatTokens(run.total_tokens)}
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {formatCost(run.total_cost)}
                    </td>
                    <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                      {formatDuration(run.duration)}
                    </td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                      {formatRelativeTime(run.start_time)}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
