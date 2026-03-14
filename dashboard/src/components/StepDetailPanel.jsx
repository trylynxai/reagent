import { useState } from 'react';
import { ChevronLeft, ChevronRight, Play } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import useTraceStore from '../stores/traceStore.js';
import TabBar from './TabBar.jsx';
import CodeBlock from './CodeBlock.jsx';

const TABS = [
  { id: 'prompt', label: 'Prompt' },
  { id: 'response', label: 'Response' },
  { id: 'raw', label: 'Raw' },
  { id: 'state', label: 'State' },
];

function formatContent(value) {
  if (value == null) return 'null';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

export default function StepDetailPanel({ className = '', runId }) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('prompt');
  const { getSelectedStep, getSelectedStepIndex, selectStepByIndex, graphNodes } = useTraceStore();

  const step = getSelectedStep();
  const index = getSelectedStepIndex();
  const totalSteps = graphNodes.length;

  if (!step) {
    return (
      <div className={`${className} bg-prd-surface border-l border-prd-border flex items-center justify-center`}>
        <p className="text-sm text-prd-text-secondary">Select a node to view details</p>
      </div>
    );
  }

  const typeColor = step.step_type === 'llm_call' ? 'text-prd-llm'
    : step.step_type === 'tool_call' ? 'text-prd-tool'
    : step.step_type === 'retrieval' ? 'text-prd-retrieval'
    : step.step_type === 'error' ? 'text-prd-error'
    : 'text-prd-text-secondary';

  const promptContent = step.prompt || step.query || (step.input ? formatContent(step.input) : 'N/A');
  const responseContent = step.response || (step.output ? formatContent(step.output) : step.error_message || step.error || 'N/A');

  return (
    <div className={`${className} bg-prd-surface border-l border-prd-border flex flex-col`}>
      {/* Step header */}
      <div className="p-4 border-b border-prd-border">
        <div className="flex items-center justify-between mb-2">
          <span className={`text-xs font-semibold uppercase ${typeColor}`}>
            {step.step_type?.replace('_', ' ')}
          </span>
          <span className="text-xs text-prd-text-secondary">
            Step {step.step_number + 1} of {totalSteps}
          </span>
        </div>
        <h3 className="text-sm font-medium text-prd-text-primary truncate">
          {step.model || step.tool_name || step.chain_name || step.agent_name || step.error || `Step ${step.step_number}`}
        </h3>
        {step.duration_ms != null && (
          <p className="text-xs text-prd-text-secondary mt-1">
            Duration: {step.duration_ms}ms
            {step.token_usage && ` | Tokens: ${step.token_usage.total_tokens}`}
          </p>
        )}
      </div>

      {/* Tabs */}
      <TabBar tabs={TABS} activeTab={activeTab} onChange={setActiveTab} />

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'prompt' && (
          <CodeBlock code={promptContent} language="text" />
        )}
        {activeTab === 'response' && (
          <CodeBlock code={responseContent} language="text" />
        )}
        {activeTab === 'raw' && (
          <CodeBlock code={JSON.stringify(step, null, 2)} language="json" downloadable filename={`step-${step.step_number}.json`} />
        )}
        {activeTab === 'state' && (
          <div className="space-y-3">
            {step.error_traceback && (
              <CodeBlock code={step.error_traceback} language="python" filename="traceback" />
            )}
            {step.token_usage && (
              <CodeBlock code={JSON.stringify(step.token_usage, null, 2)} language="json" filename="token_usage" />
            )}
            {!step.error_traceback && !step.token_usage && (
              <p className="text-sm text-prd-text-secondary">No state information available</p>
            )}
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between p-3 border-t border-prd-border">
        <button
          onClick={() => selectStepByIndex(index - 1)}
          disabled={index <= 0}
          className="flex items-center gap-1 px-2 py-1 text-xs text-prd-text-secondary hover:text-prd-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronLeft className="w-3.5 h-3.5" /> Prev
        </button>
        <button
          onClick={() => navigate(`/replay/${runId}?startStep=${step.step_number}`)}
          className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-prd-retrieval bg-prd-retrieval/10 hover:bg-prd-retrieval/20 rounded transition-colors"
        >
          <Play className="w-3 h-3" /> Replay From Here
        </button>
        <button
          onClick={() => selectStepByIndex(index + 1)}
          disabled={index >= totalSteps - 1}
          className="flex items-center gap-1 px-2 py-1 text-xs text-prd-text-secondary hover:text-prd-text-primary disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          Next <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
