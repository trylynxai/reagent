import { Handle, Position } from '@xyflow/react';
import { Wrench } from 'lucide-react';

export default function ToolNode({ data, selected }) {
  const hasError = !!data.error;
  return (
    <div className={`flex items-center gap-2.5 px-4 py-3 rounded-lg border-2 bg-prd-surface min-w-[180px] ${
      selected ? 'border-prd-tool node-selected' : 'border-prd-tool/40'
    } ${hasError ? 'border-prd-error/60' : ''}`}>
      <Handle type="target" position={Position.Top} className="!bg-prd-tool !w-2 !h-2" />
      <div className="w-8 h-8 rounded-md bg-prd-tool/20 flex items-center justify-center flex-shrink-0">
        <Wrench className="w-4 h-4 text-prd-tool" />
      </div>
      <div className="min-w-0">
        <div className="text-xs font-medium text-prd-text-primary truncate">
          {data.tool_name || data.agent_name || data.chain_name || 'Tool Call'}
        </div>
        <div className="text-[10px] text-prd-text-secondary">
          Step {data.step_number}
        </div>
      </div>
      {hasError && (
        <span className="w-2 h-2 rounded-full bg-prd-error flex-shrink-0" />
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-prd-tool !w-2 !h-2" />
    </div>
  );
}
