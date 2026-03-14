import { Handle, Position } from '@xyflow/react';
import { FileSearch } from 'lucide-react';

export default function RetrievalNode({ data, selected }) {
  return (
    <div className={`flex items-center gap-2.5 px-4 py-3 bg-prd-surface min-w-[180px] border-2 ${
      selected ? 'border-prd-retrieval node-selected' : 'border-prd-retrieval/40'
    }`}
    style={{ clipPath: 'polygon(12px 0, 100% 0, calc(100% - 12px) 100%, 0 100%)' }}
    >
      <Handle type="target" position={Position.Top} className="!bg-prd-retrieval !w-2 !h-2" />
      <div className="w-8 h-8 rounded bg-prd-retrieval/20 flex items-center justify-center flex-shrink-0 rotate-45">
        <FileSearch className="w-4 h-4 text-prd-retrieval -rotate-45" />
      </div>
      <div className="min-w-0">
        <div className="text-xs font-medium text-prd-text-primary truncate">
          {data.query ? data.query.slice(0, 30) : 'Retrieval'}
        </div>
        <div className="text-[10px] text-prd-text-secondary">
          Step {data.step_number}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-prd-retrieval !w-2 !h-2" />
    </div>
  );
}
