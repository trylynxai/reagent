const statusConfig = {
  completed: {
    dot: 'bg-prd-retrieval',
    bg: 'bg-prd-retrieval/10',
    text: 'text-prd-retrieval',
    label: 'Completed',
    pulse: false,
  },
  failed: {
    dot: 'bg-prd-error',
    bg: 'bg-prd-error/10',
    text: 'text-prd-error',
    label: 'Failed',
    pulse: false,
  },
  running: {
    dot: 'bg-yellow-400',
    bg: 'bg-yellow-400/10',
    text: 'text-yellow-400',
    label: 'Running',
    pulse: true,
  },
  cancelled: {
    dot: 'bg-prd-text-secondary',
    bg: 'bg-prd-text-secondary/10',
    text: 'text-prd-text-secondary',
    label: 'Cancelled',
    pulse: false,
  },
  partial: {
    dot: 'bg-orange-400',
    bg: 'bg-orange-400/10',
    text: 'text-orange-400',
    label: 'Partial',
    pulse: false,
  },
};

export default function StatusBadge({ status }) {
  const config = statusConfig[status] || statusConfig.cancelled;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${config.dot} ${
          config.pulse ? 'animate-pulse' : ''
        }`}
      />
      {config.label}
    </span>
  );
}
