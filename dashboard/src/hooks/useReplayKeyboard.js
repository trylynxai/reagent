import { useEffect } from 'react';
import useReplayStore from '../stores/replayStore.js';

export default function useReplayKeyboard() {
  const { isPlaying, play, pause, next, prev, toEnd, toBreakpoint, speed, setSpeed, currentStepIndex, toggleBreakpoint } = useReplayStore();

  useEffect(() => {
    function handleKeyDown(e) {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;

      switch (e.key) {
        case ' ':
          e.preventDefault();
          isPlaying ? pause() : play();
          break;
        case 'ArrowRight':
          e.preventDefault();
          next();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          prev();
          break;
        case 'b':
          toggleBreakpoint(currentStepIndex);
          break;
        case 'Escape':
          pause();
          break;
        case ']':
          setSpeed(Math.min(5, speed * 2));
          break;
        case '[':
          setSpeed(Math.max(0.5, speed / 2));
          break;
        case 'End':
          e.preventDefault();
          toEnd();
          break;
        case 'n':
          toBreakpoint();
          break;
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isPlaying, play, pause, next, prev, toEnd, toBreakpoint, speed, setSpeed, currentStepIndex, toggleBreakpoint]);
}
