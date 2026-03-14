import { create } from 'zustand';
import { fetchRuns } from '../api/client.js';

const useRunStore = create((set, get) => ({
  runs: [],
  filters: { project: '', status: '', model: '', timeRange: '', search: '' },
  selectedRunId: null,
  loading: false,

  setFilter: (key, value) => {
    set((state) => ({ filters: { ...state.filters, [key]: value } }));
  },

  setSelectedRunId: (id) => set({ selectedRunId: id }),

  loadRuns: async () => {
    set({ loading: true });
    try {
      const { filters } = get();
      const params = {};
      if (filters.project) params.project = filters.project;
      if (filters.status) params.status = filters.status;
      if (filters.model) params.model = filters.model;
      const data = await fetchRuns(params);
      set({ runs: Array.isArray(data) ? data : [], loading: false });
    } catch {
      set({ runs: [], loading: false });
    }
  },
}));

export default useRunStore;
