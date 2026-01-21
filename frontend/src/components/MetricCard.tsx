import React from 'react';
import { LucideIcon, TrendingUp, TrendingDown } from 'lucide-react';

interface MetricCardProps {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  subtitle?: string;
  trend?: 'up' | 'down' | null;
  color?: 'blue' | 'green' | 'yellow' | 'purple' | 'red';
}

const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  icon,
  subtitle,
  trend,
  color = 'blue'
}) => {
  const colorClasses = {
    blue: 'from-merlin-blue to-blue-600',
    green: 'from-success to-green-600',
    yellow: 'from-warning to-yellow-600',
    purple: 'from-merlin-purple to-purple-600',
    red: 'from-danger to-red-600'
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="metric-card group hover:scale-105 transition-transform duration-200"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm text-dark-muted mb-1">{title}</p>
          <p className="text-2xl font-bold text-dark-text">{value}</p>
          {subtitle && (
            <p className="text-xs text-dark-muted mt-1">{subtitle}</p>
          )}
        </div>
        <div className={`flex-shrink-0 w-12 h-12 bg-gradient-to-br ${colorClasses[color]} rounded-lg flex items-center justify-center text-white group-hover:scale-110 transition-transform duration-200`}>
          {icon}
        </div>
      </div>
      {trend && (
        <div className="flex items-center mt-4 text-sm">
          {trend === 'up' ? (
            <TrendingUp className="w-4 h-4 text-success mr-1" />
          ) : (
            <TrendingDown className="w-4 h-4 text-danger mr-1" />
          )}
          <span className={trend === 'up' ? 'text-success' : 'text-danger'}>
            {trend === 'up' ? '12%' : '8%'}
          </span>
          <span className="text-dark-muted ml-1">vs last period</span>
        </div>
      )}
    </motion.div>
  );
};

export default MetricCard;