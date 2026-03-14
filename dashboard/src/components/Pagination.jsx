import { ChevronLeft, ChevronRight } from 'lucide-react';

const PAGE_SIZES = [25, 50, 100];

export default function Pagination({ total = 0, limit = 50, offset = 0, onChange }) {
  const start = Math.min(offset + 1, total);
  const end = Math.min(offset + limit, total);
  const hasPrev = offset > 0;
  const hasNext = offset + limit < total;

  function goTo(newOffset) {
    onChange?.({ offset: Math.max(0, newOffset), limit });
  }

  function changePageSize(newLimit) {
    onChange?.({ offset: 0, limit: newLimit });
  }

  if (total === 0) return null;

  return (
    <div className="flex items-center justify-between text-sm">
      <p className="text-slate-400">
        Showing{' '}
        <span className="text-white font-medium">{start}-{end}</span>
        {' '}of{' '}
        <span className="text-white font-medium">{total.toLocaleString()}</span>
      </p>

      <div className="flex items-center gap-4">
        {/* Page size selector */}
        <div className="flex items-center gap-2">
          <span className="text-slate-500 text-xs">Per page</span>
          <select
            value={limit}
            onChange={(e) => changePageSize(Number(e.target.value))}
            className="bg-slate-800 border border-slate-700 rounded-md px-2 py-1.5 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>

        {/* Prev / Next */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => goTo(offset - limit)}
            disabled={!hasPrev}
            className="p-1.5 rounded-md border border-slate-700 text-slate-300 transition-colors enabled:hover:bg-slate-700 enabled:hover:text-white disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            onClick={() => goTo(offset + limit)}
            disabled={!hasNext}
            className="p-1.5 rounded-md border border-slate-700 text-slate-300 transition-colors enabled:hover:bg-slate-700 enabled:hover:text-white disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
