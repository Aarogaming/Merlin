import React from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  Activity, 
  Clock, 
  CheckCircle, 
  Star,
  TrendingUp,
  ExternalLink
} from 'lucide-react';
import { useDashboardStore } from '../store/dashboard';

const ModelPerformanceGrid: React.FC = () => {
  const { dashboardData } = useDashboardStore();

  if (!dashboardData || Object.keys(dashboardData.models).length === 0) {
    return (
      <div className="card">
        <h3 className="text-lg font-semibold mb-4 text-merlin-blue">Model Performance</h3>
        <div className="text-center py-8 text-dark-muted">
          <Activity className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>No model data available</p>
        </div>
      </div>
    );
  }

  const getModelStatusColor = (successRate: number) => {
    if (successRate >= 0.9) return 'text-success';
    if (successRate >= 0.7) return 'text-warning';
    return 'text-danger';
  };

  const getLatencyColor = (latency: number) => {
    if (latency <= 1.0) return 'text-success';
    if (latency <= 2.0) return 'text-warning';
    return 'text-danger';
  };

  return (
    <div className="card">
      <h3 className="text-lg font-semibold mb-6 text-merlin-blue">Model Performance</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {Object.entries(dashboardData.models).map(([modelName, metrics], index) => (
          <motion.div
            key={modelName}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: index * 0.1 }}
            className="metric-card group hover:border-merlin-blue/30 cursor-pointer"
          >
            {/* Model Header */}
            <div className="flex items-start justify-between mb-4">
              <div className="flex-1">
                <h4 className="font-semibold text-dark-text group-hover:text-merlin-blue transition-colors">
                  {modelName.split('-')[0]}
                </h4>
                <p className="text-xs text-dark-muted mt-1">
                  {modelName}
                </p>
              </div>
              <Link
                to={`/model/${encodeURIComponent(modelName)}`}
                className="opacity-0 group-hover:opacity-100 transition-opacity"
              >
                <ExternalLink className="w-4 h-4 text-dark-muted hover:text-merlin-blue" />
              </Link>
            </div>

            {/* Key Metrics */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="text-center p-2 bg-dark-border/50 rounded">
                <CheckCircle className="w-4 h-4 mx-auto mb-1 text-success" />
                <p className="text-lg font-bold">{(metrics.success_rate * 100).toFixed(1)}%</p>
                <p className="text-xs text-dark-muted">Success Rate</p>
              </div>
              <div className="text-center p-2 bg-dark-border/50 rounded">
                <Clock className="w-4 h-4 mx-auto mb-1 text-warning" />
                <p className="text-lg font-bold">{metrics.avg_latency.toFixed(2)}s</p>
                <p className="text-xs text-dark-muted">Avg Latency</p>
              </div>
            </div>

            {/* Performance Bars */}
            <div className="space-y-2">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-dark-muted">Success Rate</span>
                  <span className={getModelStatusColor(metrics.success_rate)}>
                    {(metrics.success_rate * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="progress-bar">
                  <div 
                    className={`progress-fill ${
                      metrics.success_rate >= 0.9 ? 'bg-success' : 
                      metrics.success_rate >= 0.7 ? 'bg-warning' : 'bg-danger'
                    }`}
                    style={{ width: `${metrics.success_rate * 100}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-dark-muted">Rating</span>
                  <span className="flex items-center">
                    <Star className="w-3 h-3 text-yellow-500 mr-1" />
                    <span>{metrics.avg_rating.toFixed(1)}/5</span>
                  </span>
                </div>
                <div className="progress-bar">
                  <div 
                    className="progress-fill bg-yellow-500"
                    style={{ width: `${(metrics.avg_rating / 5) * 100}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Request Count */}
            <div className="mt-4 pt-4 border-t border-dark-border">
              <div className="flex items-center justify-between">
                <span className="text-sm text-dark-muted">Total Requests</span>
                <span className="text-sm font-semibold text-merlin-blue">
                  {metrics.total_requests.toLocaleString()}
                </span>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

export default ModelPerformanceGrid;