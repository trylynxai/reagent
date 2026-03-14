import { Handle, Position } from '@xyflow/react';
import { Brain } from 'lucide-react';

export default function LLMNode({ data, selected }) {
  const hasError = !!data.error;
  return (
    <div className={`flex items-center gap-2.5 px-4 py-3 rounded-full border-2 bg-prd-surface min-w-[180px] ${
      selected ? 'border-prd-llm node-selected' : 'border-prd-llm/40'
    } ${hasError ? 'border-prd-error/60' : ''}`}>
      <Handle type="target" position={Position.Top} className="!bg-prd-llm !w-2 !h-2" />
      <div className="w-8 h-8 rounded-full bg-prd-llm/20 flex items-center justify-center flex-shrink-0">
        <Brain className="w-4 h-4 text-prd-llm" />
      </div>
      <div className="min-w-0">
        <div className="text-xs font-medium text-prd-text-primary truncate">
          {data.model || 'LLM Call'}
        </div>
        <div className="text-[10px] text-prd-text-secondary">
          {data.token_usage ? `${data.token_usage.total_tokens} tokens` : `Step ${data.step_number}`}
        </div>
      </div>
      {hasError && (
        <span className="w-2 h-2 rounded-full bg-prd-error flex-shrink-0" />
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-prd-llm !w-2 !h-2" />
    </div>
  );
}
