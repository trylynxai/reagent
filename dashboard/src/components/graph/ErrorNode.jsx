import { Handle, Position } from '@xyflow/react';
import { AlertOctagon } from 'lucide-react';

export default function ErrorNode({ data, selected }) {
  return (
    <div className={`flex items-center gap-2.5 px-4 py-3 rounded-lg border-2 bg-prd-error/5 min-w-[180px] ${
      selected ? 'border-prd-error node-selected' : 'border-prd-error/60'
    }`}>
      <Handle type="target" position={Position.Top} className="!bg-prd-error !w-2 !h-2" />
      <div className="w-8 h-8 rounded-md bg-prd-error/20 flex items-center justify-center flex-shrink-0">
        <AlertOctagon className="w-4 h-4 text-prd-error" />
      </div>
      <div className="min-w-0">
        <div className="text-xs font-medium text-prd-error truncate">
          {data.error || 'Error'}
        </div>
        <div className="text-[10px] text-prd-text-secondary">
          Step {data.step_number}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-prd-error !w-2 !h-2" />
    </div>
  );
}
