import { useCallback, useEffect, useMemo } from 'react';
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

export default function ReplayGraph({ steps, currentStepIndex, className = '' }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const { fitView } = useReactFlow();

  const graphData = useMemo(() => {
    const gNodes = steps.map((step, i) => ({
      id: step.step_id || `step-${i}`,
      type: step.step_type === 'llm_call' ? 'llmNode'
        : step.step_type === 'tool_call' ? 'toolNode'
        : step.step_type === 'retrieval' ? 'retrievalNode'
        : step.step_type === 'error' ? 'errorNode'
        : 'toolNode',
      position: { x: 250, y: i * 120 },
      data: { ...step, stepIndex: i },
    }));

    const gEdges = [];
    for (let i = 1; i < gNodes.length; i++) {
      gEdges.push({
        id: `e-${gNodes[i - 1].id}-${gNodes[i].id}`,
        source: gNodes[i - 1].id,
        target: gNodes[i].id,
        animated: i <= currentStepIndex,
        style: {
          stroke: i <= currentStepIndex ? '#58a6ff' : '#30363d',
          strokeWidth: 2,
          opacity: i <= currentStepIndex ? 1 : 0.3,
        },
      });
    }

    return { nodes: gNodes, edges: gEdges };
  }, [steps, currentStepIndex]);

  useEffect(() => {
    const updatedNodes = graphData.nodes.map((n, i) => ({
      ...n,
      selected: i === currentStepIndex,
      style: {
        opacity: i <= currentStepIndex ? 1 : 0.3,
      },
      className: i === currentStepIndex ? 'node-selected' : '',
    }));
    setNodes(updatedNodes);
    setEdges(graphData.edges);
  }, [graphData, currentStepIndex, setNodes, setEdges]);

  useEffect(() => {
    if (graphData.nodes.length > 0) {
      setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 100);
    }
  }, [steps.length]);

  return (
    <div className={`${className} bg-prd-bg`}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
      >
        <Background color="#30363d" gap={20} size={1} />
        <Controls showInteractive={false} className="!bg-prd-surface !border-prd-border" />
      </ReactFlow>
    </div>
  );
}
