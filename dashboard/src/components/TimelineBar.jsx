import useTraceStore from '../stores/traceStore.js';

const TYPE_COLORS = {
  llm_call: '#a371f7',
  tool_call: '#58a6ff',
  retrieval: '#3fb950',
  error: '#f85149',
  chain: '#58a6ff',
  agent: '#58a6ff',
};

export default function TimelineBar() {
  const { trace, selectedStepId, graphNodes, selectStep } = useTraceStore();
  const steps = trace?.steps || [];

  if (steps.length === 0) return null;

  const totalDuration = steps.reduce((sum, s) => sum + (s.duration_ms || 100), 0);

  return (
    <div className="h-10 flex-shrink-0 border-t border-prd-border bg-prd-surface flex items-center px-4 gap-0.5">
      {steps.map((step, i) => {
        const width = Math.max(2, ((step.duration_ms || 100) / totalDuration) * 100);
        const nodeId = graphNodes[i]?.id;
        const isSelected = nodeId === selectedStepId;
        const color = TYPE_COLORS[step.step_type] || '#8b949e';

        return (
          <button
            key={step.step_id || i}
            onClick={() => nodeId && selectStep(nodeId)}
            className="h-5 rounded-sm transition-all hover:opacity-80"
            style={{
              width: `${width}%`,
              backgroundColor: color,
              opacity: isSelected ? 1 : 0.5,
              outline: isSelected ? `2px solid ${color}` : 'none',
              outlineOffset: '1px',
            }}
            title={`Step ${step.step_number}: ${step.step_type} (${step.duration_ms || 0}ms)`}
          />
        );
      })}
    </div>
  );
}
