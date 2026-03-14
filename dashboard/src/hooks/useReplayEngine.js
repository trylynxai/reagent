import { useEffect } from 'react';
import useReplayStore from '../stores/replayStore.js';
import { fetchRun } from '../api/client.js';

export default function useReplayEngine(runId, startStep) {
  const store = useReplayStore();

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;

    async function load() {
      try {
        const data = await fetchRun(runId);
        if (cancelled) return;
        store.init(data);
        if (startStep != null && startStep > 0) {
          store.seekTo(startStep);
        }
      } catch (err) {
        console.error('Failed to load replay data:', err);
      }
    }

    load();
    return () => {
      cancelled = true;
      store.pause();
    };
  }, [runId]);

  return store;
}
