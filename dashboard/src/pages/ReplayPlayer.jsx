import { useParams, useSearchParams } from 'react-router-dom';
import { ReactFlowProvider } from '@xyflow/react';
import { Loader2 } from 'lucide-react';
import useReplayEngine from '../hooks/useReplayEngine.js';
import useReplayKeyboard from '../hooks/useReplayKeyboard.js';
import ReplayGraph from '../components/ReplayGraph.jsx';
import StateInspector from '../components/StateInspector.jsx';
import PlaybackControls from '../components/PlaybackControls.jsx';
import CodeBlock from '../components/CodeBlock.jsx';

function formatContent(value) {
  if (value == null) return 'N/A';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function ReplayPlayerInner() {
  const { runId } = useParams();
  const [searchParams] = useSearchParams();
  const startStep = parseInt(searchParams.get('startStep') || '0');

  const { steps, metadata, currentStepIndex, getCurrentSnapshot } = useReplayEngine(runId, startStep);
  useReplayKeyboard();

  if (steps.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-prd-tool animate-spin" />
      </div>
    );
  }

  const currentStep = steps[currentStepIndex];
  const snapshot = getCurrentSnapshot();

  const promptContent = currentStep?.prompt || currentStep?.query ||
    (currentStep?.input ? formatContent(currentStep.input) : 'N/A');
  const responseContent = currentStep?.response ||
    (currentStep?.output ? formatContent(currentStep.output) : currentStep?.error_message || currentStep?.error || 'N/A');

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Run header */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-prd-border bg-prd-surface">
        <h2 className="text-sm font-semibold text-prd-text-primary truncate">
          Replay: {metadata?.name || runId}
        </h2>
        <span className="text-xs text-prd-text-secondary ml-auto">
          Keyboard: Space=Play, Arrows=Step, B=Breakpoint, [/]=Speed
        </span>
      </div>

      {/* Graph area */}
      <div className="h-[40%] min-h-[200px]">
        <ReplayGraph
          steps={steps}
          currentStepIndex={currentStepIndex}
          className="w-full h-full"
        />
      </div>

      {/* Prompt / Response panes */}
      <div className="flex flex-1 min-h-0 border-t border-prd-border">
        <div className="w-1/2 flex flex-col border-r border-prd-border">
          <div className="px-3 py-1.5 border-b border-prd-border">
            <span className="text-xs font-semibold text-prd-text-secondary uppercase">Prompt</span>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            <CodeBlock code={promptContent} language="text" />
          </div>
        </div>
        <div className="w-1/2 flex flex-col">
          <div className="px-3 py-1.5 border-b border-prd-border">
            <span className="text-xs font-semibold text-prd-text-secondary uppercase">Response</span>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            <CodeBlock code={responseContent} language="text" />
          </div>
        </div>
      </div>

      {/* State Inspector */}
      <StateInspector snapshot={snapshot} />

      {/* Playback Controls */}
      <PlaybackControls />
    </div>
  );
}

export default function ReplayPlayer() {
  return (
    <ReactFlowProvider>
      <ReplayPlayerInner />
    </ReactFlowProvider>
  );
}
