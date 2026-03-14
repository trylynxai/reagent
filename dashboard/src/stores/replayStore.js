import { create } from 'zustand';

const useReplayStore = create((set, get) => ({
  mode: 'strict',
  currentStepIndex: 0,
  isPlaying: false,
  speed: 1,
  breakpoints: new Set(),
  stateSnapshots: [],
  steps: [],
  metadata: null,
  timerId: null,

  init: (trace) => {
    const steps = trace?.steps || [];
    const snapshots = steps.map((step, i) => ({
      memory: { context_size: Math.floor(Math.random() * 4096) + 512 },
      variables: {
        step_number: i,
        step_type: step.step_type,
        model: step.model || null,
        tool: step.tool_name || null,
      },
      available_tools: ['web_search', 'database_query', 'api_call', 'file_read'].slice(0, Math.min(4, i + 2)),
    }));
    set({
      steps,
      metadata: trace?.metadata || null,
      stateSnapshots: snapshots,
      currentStepIndex: 0,
      isPlaying: false,
      breakpoints: new Set(),
    });
  },

  play: () => {
    const { isPlaying, steps, currentStepIndex } = get();
    if (isPlaying || currentStepIndex >= steps.length - 1) return;
    set({ isPlaying: true });
    get()._tick();
  },

  pause: () => {
    const { timerId } = get();
    if (timerId) clearTimeout(timerId);
    set({ isPlaying: false, timerId: null });
  },

  _tick: () => {
    const { currentStepIndex, steps, speed, breakpoints, isPlaying } = get();
    if (!isPlaying) return;
    const nextIndex = currentStepIndex + 1;
    if (nextIndex >= steps.length) {
      set({ isPlaying: false, timerId: null });
      return;
    }
    if (breakpoints.has(nextIndex)) {
      set({ isPlaying: false, timerId: null, currentStepIndex: nextIndex });
      return;
    }
    const step = steps[currentStepIndex];
    const delay = Math.max(200, (step?.duration_ms || 1000) / speed);
    const id = setTimeout(() => {
      set({ currentStepIndex: nextIndex });
      get()._tick();
    }, delay);
    set({ timerId: id });
  },

  next: () => {
    const { currentStepIndex, steps } = get();
    if (currentStepIndex < steps.length - 1) {
      set({ currentStepIndex: currentStepIndex + 1 });
    }
  },

  prev: () => {
    const { currentStepIndex } = get();
    if (currentStepIndex > 0) {
      set({ currentStepIndex: currentStepIndex - 1 });
    }
  },

  toEnd: () => {
    const { steps } = get();
    set({ currentStepIndex: steps.length - 1, isPlaying: false });
  },

  toStart: () => {
    set({ currentStepIndex: 0 });
  },

  toBreakpoint: () => {
    const { currentStepIndex, breakpoints, steps } = get();
    const sorted = [...breakpoints].sort((a, b) => a - b);
    const next = sorted.find((bp) => bp > currentStepIndex);
    if (next !== undefined && next < steps.length) {
      set({ currentStepIndex: next });
    }
  },

  setSpeed: (speed) => set({ speed }),
  setMode: (mode) => set({ mode }),

  toggleBreakpoint: (index) => {
    const { breakpoints } = get();
    const next = new Set(breakpoints);
    if (next.has(index)) next.delete(index);
    else next.add(index);
    set({ breakpoints: next });
  },

  seekTo: (index) => {
    const { steps } = get();
    if (index >= 0 && index < steps.length) {
      set({ currentStepIndex: index });
    }
  },

  getCurrentSnapshot: () => {
    const { stateSnapshots, currentStepIndex } = get();
    return stateSnapshots[currentStepIndex] || null;
  },
}));

export default useReplayStore;
