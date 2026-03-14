import {
  SkipBack,
  Play,
  Pause,
  SkipForward,
  ChevronsRight,
  Flag,
  Circle,
} from 'lucide-react';
import useReplayStore from '../stores/replayStore.js';

const SPEEDS = [0.5, 1, 2, 5];
const MODES = ['strict', 'partial', 'sandbox'];

export default function PlaybackControls() {
  const {
    isPlaying, play, pause, next, prev, toEnd, toBreakpoint,
    speed, setSpeed, mode, setMode,
    currentStepIndex, steps, breakpoints, toggleBreakpoint,
  } = useReplayStore();

  const total = steps.length;

  return (
    <div className="flex-shrink-0 border-t border-prd-border bg-prd-surface px-4 py-2">
      {/* Scrubber */}
      <div className="mb-2">
        <input
          type="range"
          min={0}
          max={Math.max(0, total - 1)}
          value={currentStepIndex}
          onChange={(e) => useReplayStore.getState().seekTo(parseInt(e.target.value))}
          className="w-full h-1.5 rounded-full appearance-none bg-prd-border cursor-pointer
            [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3
            [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-prd-tool [&::-webkit-slider-thumb]:cursor-pointer"
        />
      </div>

      <div className="flex items-center justify-between">
        {/* Playback buttons */}
        <div className="flex items-center gap-1">
          <button
            onClick={prev}
            className="p-1.5 rounded hover:bg-prd-bg text-prd-text-secondary hover:text-prd-text-primary transition-colors"
            title="Previous (Left Arrow)"
          >
            <SkipBack className="w-4 h-4" />
          </button>
          <button
            onClick={isPlaying ? pause : play}
            className="p-2 rounded-full bg-prd-tool/20 text-prd-tool hover:bg-prd-tool/30 transition-colors"
            title="Play/Pause (Space)"
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          </button>
          <button
            onClick={next}
            className="p-1.5 rounded hover:bg-prd-bg text-prd-text-secondary hover:text-prd-text-primary transition-colors"
            title="Next (Right Arrow)"
          >
            <SkipForward className="w-4 h-4" />
          </button>
          <button
            onClick={toEnd}
            className="p-1.5 rounded hover:bg-prd-bg text-prd-text-secondary hover:text-prd-text-primary transition-colors"
            title="To End"
          >
            <ChevronsRight className="w-4 h-4" />
          </button>
          <button
            onClick={toBreakpoint}
            className="p-1.5 rounded hover:bg-prd-bg text-prd-text-secondary hover:text-prd-text-primary transition-colors"
            title="To Breakpoint (N)"
          >
            <Flag className="w-4 h-4" />
          </button>
        </div>

        {/* Step indicator */}
        <span className="text-xs font-mono text-prd-text-secondary">
          Step {currentStepIndex + 1}/{total}
        </span>

        {/* Speed, Mode, Breakpoint */}
        <div className="flex items-center gap-3">
          <select
            value={speed}
            onChange={(e) => setSpeed(parseFloat(e.target.value))}
            className="bg-prd-bg border border-prd-border rounded text-xs text-prd-text-primary px-2 py-1"
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>{s}x</option>
            ))}
          </select>

          <select
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            className="bg-prd-bg border border-prd-border rounded text-xs text-prd-text-primary px-2 py-1"
          >
            {MODES.map((m) => (
              <option key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>
            ))}
          </select>

          <button
            onClick={() => toggleBreakpoint(currentStepIndex)}
            className={`p-1.5 rounded transition-colors ${
              breakpoints.has(currentStepIndex)
                ? 'bg-prd-error/20 text-prd-error'
                : 'hover:bg-prd-bg text-prd-text-secondary hover:text-prd-text-primary'
            }`}
            title="Toggle Breakpoint (B)"
          >
            <Circle className="w-3.5 h-3.5" fill={breakpoints.has(currentStepIndex) ? 'currentColor' : 'none'} />
          </button>
        </div>
      </div>
    </div>
  );
}
