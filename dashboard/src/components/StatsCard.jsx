import { TrendingUp, TrendingDown } from 'lucide-react';

export default function StatsCard({
  title,
  value,
  subtitle,
  icon: Icon,
  iconColor = 'bg-prd-tool/20 text-prd-tool',
  trend,
}) {
  return (
    <div className="bg-prd-surface border border-prd-border rounded-lg p-5 transition-colors hover:border-prd-text-secondary/40">
      <div className="flex items-start justify-between">
        <div className="space-y-2 min-w-0">
          <p className="text-sm text-prd-text-secondary">{title}</p>
          <div className="flex items-baseline gap-2">
            <p className="text-2xl font-semibold text-prd-text-primary truncate">
              {value}
            </p>
            {trend && (
              <span
                className={`flex items-center gap-0.5 text-xs font-medium ${
                  trend.direction === 'up'
                    ? 'text-prd-retrieval'
                    : 'text-prd-error'
                }`}
              >
                {trend.direction === 'up' ? (
                  <TrendingUp className="w-3.5 h-3.5" />
                ) : (
                  <TrendingDown className="w-3.5 h-3.5" />
                )}
                {trend.label}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="text-xs text-prd-text-secondary">{subtitle}</p>
          )}
        </div>
        {Icon && (
          <div className={`p-2.5 rounded-lg flex-shrink-0 ${iconColor}`}>
            <Icon className="w-5 h-5" />
          </div>
        )}
      </div>
    </div>
  );
}
