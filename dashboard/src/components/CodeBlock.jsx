import { useState } from 'react';
import { Copy, Check, Download } from 'lucide-react';

export default function CodeBlock({ code, language = 'json', filename, downloadable = false }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `export.${language}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative group rounded-md border border-prd-border bg-prd-bg overflow-hidden">
      {filename && (
        <div className="px-3 py-1.5 text-xs text-prd-text-secondary border-b border-prd-border bg-prd-surface">
          {filename}
        </div>
      )}
      <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={handleCopy}
          className="p-1.5 rounded bg-prd-surface border border-prd-border text-prd-text-secondary hover:text-prd-text-primary transition-colors"
          title="Copy"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-prd-retrieval" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
        {downloadable && (
          <button
            onClick={handleDownload}
            className="p-1.5 rounded bg-prd-surface border border-prd-border text-prd-text-secondary hover:text-prd-text-primary transition-colors"
            title="Download"
          >
            <Download className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
      <pre className="p-3 overflow-x-auto text-sm font-mono text-prd-text-primary leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}
