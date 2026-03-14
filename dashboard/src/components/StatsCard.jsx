import { TrendingUp, TrendingDown } from 'lucide-react';

export default function StatsCard({
  title,
  value,
  subtitle,
  icon: Icon,
  iconColor = 'bg-blue-500/20 text-blue-400',
  trend,
}) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-5 transition-colors hover:border-slate-600">
      <div className="flex items-start justify-between">
        <div className="space-y-2 min-w-0">
          <p className="text-sm text-slate-400">{title}</p>
          <div className="flex items-baseline gap-2">
            <p className="text-2xl font-semibold text-white truncate">
              {value}
            </p>
            {trend && (
              <span
                className={`flex items-center gap-0.5 text-xs font-medium ${
                  trend.direction === 'up'
                    ? 'text-green-400'
                    : 'text-red-400'
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
            <p className="text-xs text-slate-500">{subtitle}</p>
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
