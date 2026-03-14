import { useCallback, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import nodeTypes from './graph/nodeTypes.js';
import useTraceStore from '../stores/traceStore.js';

export default function TraceGraph({ className = '' }) {
  const { graphNodes, graphEdges, selectedStepId, selectStep } = useTraceStore();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const { fitView } = useReactFlow();

  useEffect(() => {
    const updatedNodes = graphNodes.map((n) => ({
      ...n,
      selected: n.id === selectedStepId,
    }));
    setNodes(updatedNodes);
    setEdges(graphEdges);
  }, [graphNodes, graphEdges, selectedStepId, setNodes, setEdges]);

  useEffect(() => {
    if (nodes.length > 0) {
      setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 100);
    }
  }, [graphNodes.length]);

  const onNodeClick = useCallback((_event, node) => {
    selectStep(node.id);
  }, [selectStep]);

  return (
    <div className={`${className} bg-prd-bg`}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#30363d" gap={20} size={1} />
        <Controls
          showInteractive={false}
          className="!bg-prd-surface !border-prd-border !rounded-md !shadow-lg"
        />
      </ReactFlow>
    </div>
  );
}
