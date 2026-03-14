import { create } from 'zustand';
import { fetchRun } from '../api/client.js';

function buildGraph(steps) {
  const nodes = steps.map((step, i) => ({
    id: step.step_id || `step-${i}`,
    type: step.step_type === 'llm_call' ? 'llmNode'
      : step.step_type === 'tool_call' ? 'toolNode'
      : step.step_type === 'retrieval' ? 'retrievalNode'
      : step.step_type === 'error' ? 'errorNode'
      : 'toolNode',
    position: { x: 250, y: i * 120 },
    data: { ...step, stepIndex: i },
  }));

  const edges = [];
  for (let i = 1; i < nodes.length; i++) {
    edges.push({
      id: `e-${nodes[i - 1].id}-${nodes[i].id}`,
      source: nodes[i - 1].id,
      target: nodes[i].id,
      animated: true,
      style: { stroke: '#30363d', strokeWidth: 2 },
    });
  }

  return { nodes, edges };
}

const useTraceStore = create((set, get) => ({
  trace: null,
  selectedStepId: null,
  graphNodes: [],
  graphEdges: [],
  loading: false,

  loadTrace: async (runId) => {
    set({ loading: true });
    try {
      const data = await fetchRun(runId);
      const { nodes, edges } = buildGraph(data.steps || []);
      set({
        trace: data,
        graphNodes: nodes,
        graphEdges: edges,
        selectedStepId: nodes.length > 0 ? nodes[0].id : null,
        loading: false,
      });
    } catch {
      set({ trace: null, graphNodes: [], graphEdges: [], loading: false });
    }
  },

  selectStep: (stepId) => set({ selectedStepId: stepId }),

  selectStepByIndex: (index) => {
    const { graphNodes } = get();
    if (index >= 0 && index < graphNodes.length) {
      set({ selectedStepId: graphNodes[index].id });
    }
  },

  getSelectedStep: () => {
    const { trace, selectedStepId, graphNodes } = get();
    if (!trace || !selectedStepId) return null;
    const node = graphNodes.find((n) => n.id === selectedStepId);
    return node?.data || null;
  },

  getSelectedStepIndex: () => {
    const { selectedStepId, graphNodes } = get();
    return graphNodes.findIndex((n) => n.id === selectedStepId);
  },
}));

export default useTraceStore;
