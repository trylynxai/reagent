import { useState, useEffect } from 'react';
import { Wifi, WifiOff, Database } from 'lucide-react';

export default function StatusBar() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const res = await fetch('/health');
        if (!cancelled) setHealth(res.ok ? 'connected' : 'disconnected');
      } catch {
        if (!cancelled) setHealth('disconnected');
      }
    }
    check();
    const interval = setInterval(check, 30000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  return (
    <footer className="h-7 flex-shrink-0 flex items-center justify-between px-4 border-t border-prd-border bg-prd-surface text-xs">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          {health === 'connected' ? (
            <Wifi className="w-3 h-3 text-prd-retrieval" />
          ) : health === 'disconnected' ? (
            <WifiOff className="w-3 h-3 text-prd-error" />
          ) : (
            <Wifi className="w-3 h-3 text-prd-text-secondary animate-pulse" />
          )}
          <span className="text-prd-text-secondary">
            {health === 'connected' ? 'Connected' : health === 'disconnected' ? 'Disconnected' : 'Checking...'}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Database className="w-3 h-3 text-prd-text-secondary" />
          <span className="text-prd-text-secondary">Mock</span>
        </div>
      </div>
      <span className="text-prd-text-secondary">ReAgent v0.1.0</span>
    </footer>
  );
}
