import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { ReactFlowProvider } from '@xyflow/react';
import { Loader2 } from 'lucide-react';
import useTraceStore from '../stores/traceStore.js';
import TraceGraph from '../components/TraceGraph.jsx';
import StepDetailPanel from '../components/StepDetailPanel.jsx';
import TimelineBar from '../components/TimelineBar.jsx';

function TraceInspectInner() {
  const { runId } = useParams();
  const { trace, loading, loadTrace } = useTraceStore();

  useEffect(() => {
    if (runId) loadTrace(runId);
  }, [runId]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-prd-tool animate-spin" />
      </div>
    );
  }

  if (!trace) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-prd-text-secondary">Run not found</p>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Run header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-prd-border bg-prd-surface">
        <h2 className="text-sm font-semibold text-prd-text-primary truncate">
          {trace.metadata?.name || runId}
        </h2>
        <span className="text-xs text-prd-text-secondary">
          {trace.metadata?.project}
        </span>
        <span className="text-xs text-prd-text-secondary ml-auto">
          {trace.steps?.length || 0} steps
        </span>
      </div>

      {/* Main content */}
      <div className="flex flex-1 min-h-0">
        <TraceGraph className="w-[60%] h-full" />
        <StepDetailPanel className="w-[40%] h-full" runId={runId} />
      </div>

      <TimelineBar />
    </div>
  );
}

export default function TraceInspect() {
  return (
    <ReactFlowProvider>
      <TraceInspectInner />
    </ReactFlowProvider>
  );
}
