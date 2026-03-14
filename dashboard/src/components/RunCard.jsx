import { useNavigate } from 'react-router-dom';
import { Eye, Play, Download, Clock, Coins, Layers, Cpu } from 'lucide-react';
import StatusBadge from './StatusBadge.jsx';

function formatDuration(ms) {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function formatCost(cost) {
  if (cost == null) return '-';
  return `$${Number(cost).toFixed(4)}`;
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

export default function RunCard({ run }) {
  const navigate = useNavigate();

  const handleExport = (e) => {
    e.stopPropagation();
    const blob = new Blob([JSON.stringify(run, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${run.name || run.run_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="bg-prd-surface border border-prd-border rounded-lg p-4 hover:border-prd-tool/40 transition-colors group">
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0">
          <h3 className="text-sm font-medium text-prd-text-primary truncate">
            {run.name || run.run_id}
          </h3>
          <p className="text-xs text-prd-text-secondary mt-0.5">
            {run.project} &middot; {timeAgo(run.start_time)}
          </p>
        </div>
        <StatusBadge status={run.status} />
      </div>

      <div className="flex items-center gap-3 mb-3">
        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium bg-prd-llm/10 text-prd-llm rounded">
          <Cpu className="w-3 h-3" />
          {run.model}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs text-prd-text-secondary mb-3">
        <div className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {formatDuration(run.duration_ms)}
        </div>
        <div className="flex items-center gap-1">
          <Layers className="w-3 h-3" />
          {run.step_count} steps
        </div>
        <div className="flex items-center gap-1">
          <Coins className="w-3 h-3" />
          {formatCost(run.total_cost_usd)}
        </div>
      </div>

      {run.error && (
        <div className="mb-3 px-2 py-1.5 rounded bg-prd-error/5 border border-prd-error/20">
          <p className="text-[11px] text-prd-error truncate font-mono">{run.error}</p>
        </div>
      )}

      <div className="flex items-center gap-2 pt-2 border-t border-prd-border">
        <button
          onClick={(e) => { e.stopPropagation(); navigate(`/trace/${run.run_id}`); }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-prd-tool bg-prd-tool/10 hover:bg-prd-tool/20 rounded transition-colors"
        >
          <Eye className="w-3 h-3" />
          Inspect
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); navigate(`/replay/${run.run_id}`); }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-prd-retrieval bg-prd-retrieval/10 hover:bg-prd-retrieval/20 rounded transition-colors"
        >
          <Play className="w-3 h-3" />
          Replay
        </button>
        <button
          onClick={handleExport}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-prd-text-secondary bg-prd-bg hover:bg-prd-border/50 rounded transition-colors ml-auto"
        >
          <Download className="w-3 h-3" />
          Export
        </button>
      </div>
    </div>
  );
}
