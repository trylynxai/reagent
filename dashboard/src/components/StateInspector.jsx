import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

function TreeNode({ name, value, depth = 0 }) {
  const [expanded, setExpanded] = useState(depth < 2);
  const isObject = value != null && typeof value === 'object';
  const isArray = Array.isArray(value);
  const entries = isObject ? Object.entries(value) : [];

  if (!isObject) {
    const colorClass = typeof value === 'string' ? 'text-prd-retrieval'
      : typeof value === 'number' ? 'text-prd-llm'
      : typeof value === 'boolean' ? 'text-prd-tool'
      : value === null ? 'text-prd-text-secondary'
      : 'text-prd-text-primary';

    return (
      <div className="flex items-baseline gap-2 py-0.5" style={{ paddingLeft: `${depth * 16}px` }}>
        <span className="text-prd-text-secondary font-mono text-xs">{name}:</span>
        <span className={`font-mono text-xs ${colorClass}`}>
          {value === null ? 'null' : JSON.stringify(value)}
        </span>
      </div>
    );
  }

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 py-0.5 w-full text-left hover:bg-prd-bg/50 rounded"
        style={{ paddingLeft: `${depth * 16}px` }}
      >
        {expanded
          ? <ChevronDown className="w-3 h-3 text-prd-text-secondary flex-shrink-0" />
          : <ChevronRight className="w-3 h-3 text-prd-text-secondary flex-shrink-0" />
        }
        <span className="text-prd-text-secondary font-mono text-xs">{name}</span>
        <span className="text-prd-text-secondary text-[10px] ml-1">
          {isArray ? `[${entries.length}]` : `{${entries.length}}`}
        </span>
      </button>
      {expanded && entries.map(([key, val]) => (
        <TreeNode key={key} name={key} value={val} depth={depth + 1} />
      ))}
    </div>
  );
}

export default function StateInspector({ snapshot, className = '' }) {
  const [collapsed, setCollapsed] = useState(false);

  if (!snapshot) {
    return (
      <div className={`${className} bg-prd-surface border-t border-prd-border p-3`}>
        <p className="text-xs text-prd-text-secondary">No state available</p>
      </div>
    );
  }

  return (
    <div className={`${className} bg-prd-surface border-t border-prd-border`}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-4 py-2 hover:bg-prd-bg/50 transition-colors"
      >
        <span className="text-xs font-semibold text-prd-text-secondary uppercase tracking-wider">State Inspector</span>
        {collapsed
          ? <ChevronRight className="w-3.5 h-3.5 text-prd-text-secondary" />
          : <ChevronDown className="w-3.5 h-3.5 text-prd-text-secondary" />
        }
      </button>
      {!collapsed && (
        <div className="px-4 pb-3 max-h-48 overflow-y-auto">
          {Object.entries(snapshot).map(([key, val]) => (
            <TreeNode key={key} name={key} value={val} />
          ))}
        </div>
      )}
    </div>
  );
}
