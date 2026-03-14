import { useState } from 'react';
import { ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';

export default function ErrorPanel({
  error,
  errorType,
  failureCategory,
  traceback,
}) {
  const [showTraceback, setShowTraceback] = useState(false);
  const [copied, setCopied] = useState(false);

  async function copyError() {
    const text = [errorType, error, traceback].filter(Boolean).join('\n\n');
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard API may not be available
    }
  }

  return (
    <div className="bg-red-950/50 border border-red-800 rounded-lg p-5 space-y-3">
      {/* Badges */}
      <div className="flex items-center flex-wrap gap-2">
        {errorType && (
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-red-400/10 text-red-400">
            {errorType}
          </span>
        )}
        {failureCategory && (
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-700 text-slate-300">
            {failureCategory}
          </span>
        )}
      </div>

      {/* Error message */}
      <p className="text-sm text-red-300 leading-relaxed">{error}</p>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button
          onClick={copyError}
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
        >
          {copied ? (
            <Check className="w-3.5 h-3.5 text-green-400" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
          {copied ? 'Copied' : 'Copy error'}
        </button>
      </div>

      {/* Traceback */}
      {traceback && (
        <div>
          <button
            onClick={() => setShowTraceback(!showTraceback)}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
          >
            {showTraceback ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )}
            Traceback
          </button>
          {showTraceback && (
            <pre className="mt-2 p-3 bg-slate-900 border border-slate-700 rounded-md text-xs text-slate-300 font-mono overflow-x-auto whitespace-pre leading-relaxed max-h-64 overflow-y-auto">
              {traceback}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
