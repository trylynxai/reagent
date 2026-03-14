import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Brain,
  Wrench,
  AlertCircle,
  Link2,
  Bot,
  Search,
  Clock,
  Hash,
  Coins,
  Layers,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';
import { fetchRun } from '../api/client.js';
import Header from '../components/Header.jsx';
import StatsCard from '../components/StatsCard.jsx';
import StatusBadge from '../components/StatusBadge.jsx';

const STEP_CONFIG = {
  llm_call: { icon: Brain, color: 'border-blue-500', bg: 'bg-blue-500/10', text: 'text-blue-400', label: 'LLM Call' },
  tool_call: { icon: Wrench, color: 'border-green-500', bg: 'bg-green-500/10', text: 'text-green-400', label: 'Tool Call' },
  error: { icon: AlertCircle, color: 'border-red-500', bg: 'bg-red-500/10', text: 'text-red-400', label: 'Error' },
  chain: { icon: Link2, color: 'border-purple-500', bg: 'bg-purple-500/10', text: 'text-purple-400', label: 'Chain' },
  agent: { icon: Bot, color: 'border-cyan-500', bg: 'bg-cyan-500/10', text: 'text-cyan-400', label: 'Agent' },
  retrieval: { icon: Search, color: 'border-yellow-500', bg: 'bg-yellow-500/10', text: 'text-yellow-400', label: 'Retrieval' },
};

function getStepConfig(type) {
  return STEP_CONFIG[type] || STEP_CONFIG.error;
}

function formatDuration(ms) {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatCost(cost) {
  if (cost == null) return '$0.00';
  return `$${Number(cost).toFixed(4)}`;
}

function formatTime(dateStr) {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleString();
}

function CodeBlock({ children, className = '' }) {
  return (
    <pre
      className={`bg-slate-900 border border-slate-700 rounded-lg p-3 text-xs text-slate-300 overflow-x-auto whitespace-pre-wrap break-words max-h-80 overflow-y-auto ${className}`}
    >
      {typeof children === 'string' ? children : JSON.stringify(children, null, 2)}
    </pre>
  );
}

function Collapsible({ title, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-slate-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:bg-slate-700/50 transition-colors"
      >
        {open ? (
          <ChevronDown className="w-4 h-4 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 flex-shrink-0" />
        )}
        {title}
      </button>
      {open && <div className="px-3 pb-3">{children}</div>}
    </div>
  );
}

function StepDetails({ step }) {
  const type = step.step_type;

  if (type === 'llm_call') {
    return (
      <div className="space-y-3 mt-3">
        {step.model && (
          <p className="text-xs text-slate-400">
            Model: <span className="text-slate-200">{step.model}</span>
          </p>
        )}
        {step.prompt && (
          <Collapsible title="Prompt" defaultOpen>
            <CodeBlock>{step.prompt}</CodeBlock>
          </Collapsible>
        )}
        {step.response && (
          <Collapsible title="Response" defaultOpen>
            <CodeBlock>{step.response}</CodeBlock>
          </Collapsible>
        )}
      </div>
    );
  }

  if (type === 'tool_call') {
    return (
      <div className="space-y-3 mt-3">
        <p className="text-xs text-slate-400">
          Tool: <span className="text-slate-200 font-medium">{step.tool_name}</span>
        </p>
        {step.input != null && (
          <Collapsible title="Input" defaultOpen>
            <CodeBlock>{step.input}</CodeBlock>
          </Collapsible>
        )}
        {step.output != null && (
          <Collapsible title="Output" defaultOpen>
            <CodeBlock>{step.output}</CodeBlock>
          </Collapsible>
        )}
        {step.error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
            <p className="text-xs text-red-400">{step.error}</p>
          </div>
        )}
      </div>
    );
  }

  if (type === 'error') {
    return (
      <div className="mt-3 bg-red-500/10 border border-red-500/30 rounded-lg p-4 space-y-2">
        {step.error && (
          <p className="text-sm text-red-300 font-medium">{step.error}</p>
        )}
        {step.error_message && (
          <CodeBlock className="!bg-red-950/50 !border-red-500/20 !text-red-300">
            {step.error_message}
          </CodeBlock>
        )}
      </div>
    );
  }

  if (type === 'chain') {
    return (
      <div className="space-y-3 mt-3">
        {step.chain_name && (
          <p className="text-xs text-slate-400">
            Chain: <span className="text-slate-200">{step.chain_name}</span>
          </p>
        )}
        {step.input != null && (
          <Collapsible title="Input">
            <CodeBlock>{step.input}</CodeBlock>
          </Collapsible>
        )}
        {step.output != null && (
          <Collapsible title="Output">
            <CodeBlock>{step.output}</CodeBlock>
          </Collapsible>
        )}
      </div>
    );
  }

  if (type === 'agent') {
    return (
      <div className="space-y-3 mt-3">
        {step.agent_name && (
          <p className="text-xs text-slate-400">
            Agent: <span className="text-slate-200">{step.agent_name}</span>
          </p>
        )}
        {step.input != null && (
          <Collapsible title="Action Input">
            <CodeBlock>{step.input}</CodeBlock>
          </Collapsible>
        )}
        {step.output != null && (
          <Collapsible title="Output">
            <CodeBlock>{step.output}</CodeBlock>
          </Collapsible>
        )}
      </div>
    );
  }

  if (type === 'retrieval') {
    return (
      <div className="space-y-3 mt-3">
        {step.query && (
          <p className="text-xs text-slate-400">
            Query: <span className="text-slate-200">{step.query}</span>
          </p>
        )}
        {step.output != null && (
          <Collapsible title="Results">
            <CodeBlock>{step.output}</CodeBlock>
          </Collapsible>
        )}
      </div>
    );
  }

  return null;
}

function TimelineStep({ step }) {
  const [expanded, setExpanded] = useState(false);
  const config = getStepConfig(step.step_type);
  const Icon = config.icon;

  const preview = (() => {
    switch (step.step_type) {
      case 'llm_call':
        return step.model || '';
      case 'tool_call':
        return step.tool_name || '';
      case 'error':
        return step.error_message?.slice(0, 80) || step.error || '';
      case 'chain':
        return step.chain_name || '';
      case 'agent':
        return step.agent_name || '';
      case 'retrieval':
        return step.query?.slice(0, 80) || '';
      default:
        return '';
    }
  })();

  return (
    <div
      className={`border-l-2 ${config.color} pl-4 pb-4 last:pb-0`}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left group"
      >
        <div className="flex items-center gap-3">
          <div className={`p-1.5 rounded-md ${config.bg}`}>
            <Icon className={`w-4 h-4 ${config.text}`} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">
                #{step.step_number}
              </span>
              <span className={`text-xs font-medium ${config.text}`}>
                {config.label}
              </span>
              {step.duration_ms != null && (
                <span className="text-xs text-slate-500">
                  {formatDuration(step.duration_ms)}
                </span>
              )}
            </div>
            {preview && (
              <p className="text-sm text-slate-400 truncate mt-0.5 group-hover:text-slate-300 transition-colors">
                {preview}
              </p>
            )}
          </div>
          <div className="flex-shrink-0">
            {expanded ? (
              <ChevronDown className="w-4 h-4 text-slate-500" />
            ) : (
              <ChevronRight className="w-4 h-4 text-slate-500" />
            )}
          </div>
        </div>
      </button>
      {expanded && <StepDetails step={step} />}
    </div>
  );
}

function ErrorPanel({ error, errorType, failureCategory }) {
  return (
    <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 space-y-2">
      <h3 className="text-sm font-semibold text-red-400">Error</h3>
      {errorType && (
        <p className="text-xs text-slate-400">
          Type: <span className="text-red-300">{errorType}</span>
        </p>
      )}
      {failureCategory && (
        <p className="text-xs text-slate-400">
          Category: <span className="text-red-300">{failureCategory}</span>
        </p>
      )}
      {error && <p className="text-sm text-red-300 break-words">{error}</p>}
    </div>
  );
}

function SkeletonView() {
  return (
    <div className="p-6 space-y-6 animate-pulse">
      <div className="h-8 bg-slate-800 rounded w-64" />
      <div className="grid grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-20 bg-slate-800 rounded-lg" />
        ))}
      </div>
      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 h-96 bg-slate-800 rounded-lg" />
        <div className="h-96 bg-slate-800 rounded-lg" />
      </div>
    </div>
  );
}

export default function RunView() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await fetchRun(runId);
        if (!cancelled) setRun(data);
      } catch (err) {
        console.error('Failed to fetch run:', err);
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [runId]);

  if (loading) {
    return (
      <>
        <Header title="Run Details" />
        <main className="flex-1 overflow-y-auto">
          <SkeletonView />
        </main>
      </>
    );
  }

  if (error || !run) {
    return (
      <>
        <Header title="Run Details" />
        <main className="flex-1 overflow-y-auto p-6">
          <button
            onClick={() => navigate('/runs')}
            className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors mb-6"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Runs
          </button>
          <div className="text-center py-16">
            <AlertCircle className="w-10 h-10 text-red-400 mx-auto mb-3" />
            <p className="text-slate-300">
              {error || 'Run not found'}
            </p>
          </div>
        </main>
      </>
    );
  }

  const meta = run.metadata || {};
  const steps = run.steps || [];
  const tokens = meta.tokens || {};
  const cost = meta.cost || {};
  const stepStats = meta.steps || {};

  return (
    <>
      <Header title="Run Details" />
      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Back button */}
        <button
          onClick={() => navigate('/runs')}
          className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Runs
        </button>

        {/* Header section */}
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-semibold text-white truncate">
              {meta.name || runId}
            </h2>
            <div className="flex flex-wrap items-center gap-3 mt-2">
              <StatusBadge status={meta.status} />
              {meta.project && (
                <span className="text-xs bg-slate-700 text-slate-300 px-2.5 py-1 rounded-full">
                  {meta.project}
                </span>
              )}
              {meta.model && (
                <span className="text-xs bg-blue-500/10 text-blue-400 px-2.5 py-1 rounded-full">
                  {meta.model}
                </span>
              )}
            </div>
            <div className="flex flex-wrap gap-4 mt-2 text-xs text-slate-500">
              <span>Start: {formatTime(meta.start_time)}</span>
              {meta.end_time && <span>End: {formatTime(meta.end_time)}</span>}
              {meta.duration_ms != null && (
                <span>Duration: {formatDuration(meta.duration_ms)}</span>
              )}
            </div>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatsCard
            title="Steps"
            value={stepStats.total ?? steps.length}
            icon={Layers}
            iconColor="bg-blue-500/20 text-blue-400"
            subtitle={
              stepStats.llm_calls != null
                ? `${stepStats.llm_calls} LLM, ${stepStats.tool_calls ?? 0} Tool`
                : undefined
            }
          />
          <StatsCard
            title="Tokens"
            value={tokens.total_tokens?.toLocaleString() ?? '-'}
            icon={Hash}
            iconColor="bg-purple-500/20 text-purple-400"
            subtitle={
              tokens.prompt_tokens != null
                ? `${tokens.prompt_tokens.toLocaleString()} prompt, ${(tokens.completion_tokens ?? 0).toLocaleString()} completion`
                : undefined
            }
          />
          <StatsCard
            title="Cost"
            value={formatCost(cost.total_usd)}
            icon={Coins}
            iconColor="bg-yellow-500/20 text-yellow-400"
          />
          <StatsCard
            title="Duration"
            value={formatDuration(meta.duration_ms)}
            icon={Clock}
            iconColor="bg-green-500/20 text-green-400"
          />
        </div>

        {/* Two-column layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Timeline */}
          <div className="lg:col-span-2">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5">
              <h3 className="text-sm font-semibold text-slate-300 mb-5">
                Execution Timeline
              </h3>
              {steps.length === 0 ? (
                <p className="text-sm text-slate-500 py-8 text-center">
                  No steps recorded
                </p>
              ) : (
                <div className="space-y-1">
                  {steps.map((step) => (
                    <TimelineStep key={step.step_id || step.step_number} step={step} />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right: Run Info */}
          <div className="space-y-4">
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 space-y-4">
              <h3 className="text-sm font-semibold text-slate-300">
                Run Info
              </h3>

              {/* Metadata */}
              <div className="space-y-2 text-sm">
                {meta.project && (
                  <div className="flex justify-between">
                    <span className="text-slate-500">Project</span>
                    <span className="text-slate-200">{meta.project}</span>
                  </div>
                )}
                {meta.tags?.length > 0 && (
                  <div className="flex justify-between items-start">
                    <span className="text-slate-500">Tags</span>
                    <div className="flex flex-wrap gap-1 justify-end">
                      {meta.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-xs bg-slate-700 text-slate-300 px-2 py-0.5 rounded"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {meta.model && (
                  <div className="flex justify-between">
                    <span className="text-slate-500">Model</span>
                    <span className="text-slate-200">{meta.model}</span>
                  </div>
                )}
                {meta.models_used?.length > 0 && (
                  <div className="flex justify-between items-start">
                    <span className="text-slate-500">Models Used</span>
                    <div className="text-right">
                      {meta.models_used.map((m) => (
                        <p key={m} className="text-xs text-slate-300">{m}</p>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Input */}
              {meta.input != null && (
                <Collapsible title="Input">
                  <CodeBlock>{meta.input}</CodeBlock>
                </Collapsible>
              )}

              {/* Output */}
              {meta.output != null && (
                <Collapsible title="Output">
                  <CodeBlock>{meta.output}</CodeBlock>
                </Collapsible>
              )}

              {/* Custom metadata */}
              {meta.custom != null && Object.keys(meta.custom).length > 0 && (
                <Collapsible title="Custom Metadata">
                  <CodeBlock>{meta.custom}</CodeBlock>
                </Collapsible>
              )}
            </div>

            {/* Error panel */}
            {meta.error && (
              <ErrorPanel
                error={meta.error}
                errorType={meta.error_type}
                failureCategory={meta.failure_category}
              />
            )}
          </div>
        </div>
      </main>
    </>
  );
}
