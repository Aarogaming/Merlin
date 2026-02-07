import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

interface PluginMetrics {
  plugin_id: string;
  plugin_name: string;
  category: string;
  total_invocations: number;
  successful_invocations: number;
  failed_invocations: number;
  success_rate: number;
  error_rate: number;
  avg_execution_time_ms: number;
  health_score: number;
  last_used: string | null;
}

interface GlobalStats {
  total_plugins: number;
  active_plugins: number;
  total_invocations: number;
  total_errors: number;
  avg_success_rate: number;
}

interface ComparativeAnalysis {
  fastest_plugin: string;
  slowest_plugin: string;
  most_reliable: string;
  least_reliable: string;
  most_used: string;
  least_used: string;
  healthiest: string;
}

interface PluginAnalyticsData {
  timestamp: string;
  global_stats: GlobalStats;
  top_plugins: PluginMetrics[];
  comparative_analysis: ComparativeAnalysis;
  error?: string;
}

const PluginAnalytics: React.FC = () => {
  const [data, setData] = useState<PluginAnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPluginAnalytics = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/plugin/analytics');
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const result: PluginAnalyticsData = await response.json();
      if (result.error) {
        setError(result.error);
      } else {
        setData(result);
        setError(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch plugin analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPluginAnalytics();
    const interval = setInterval(fetchPluginAnalytics, 15000); // Refresh every 15 seconds
    return () => clearInterval(interval);
  }, []);

  const getHealthColor = (score: number): string => {
    if (score >= 90) return 'text-green-500';
    if (score >= 70) return 'text-yellow-500';
    return 'text-red-500';
  };

  const getHealthBgColor = (score: number): string => {
    if (score >= 90) return 'bg-green-500';
    if (score >= 70) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const getCategoryIcon = (category: string): string => {
    const icons: { [key: string]: string } = {
      automation: '🤖',
      ai: '🧠',
      data: '📊',
      monitoring: '📡',
      communication: '💬',
      integration: '🔗',
      development: '💻',
      security: '🔒',
    };
    return icons[category.toLowerCase()] || '📦';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-800">Error: {error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <p className="text-gray-600">No plugin analytics data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-800">Plugin Analytics</h2>
        <span className="text-sm text-gray-500">
          Last updated: {new Date(data.timestamp).toLocaleTimeString()}
        </span>
      </div>

      {/* Global Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-lg p-4 text-white shadow-lg"
        >
          <div className="text-sm font-medium opacity-90">Total Plugins</div>
          <div className="text-3xl font-bold mt-2">{data.global_stats.total_plugins}</div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-gradient-to-br from-green-500 to-green-600 rounded-lg p-4 text-white shadow-lg"
        >
          <div className="text-sm font-medium opacity-90">Active Plugins</div>
          <div className="text-3xl font-bold mt-2">{data.global_stats.active_plugins}</div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-gradient-to-br from-purple-500 to-purple-600 rounded-lg p-4 text-white shadow-lg"
        >
          <div className="text-sm font-medium opacity-90">Total Invocations</div>
          <div className="text-3xl font-bold mt-2">
            {data.global_stats.total_invocations.toLocaleString()}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="bg-gradient-to-br from-orange-500 to-orange-600 rounded-lg p-4 text-white shadow-lg"
        >
          <div className="text-sm font-medium opacity-90">Total Errors</div>
          <div className="text-3xl font-bold mt-2">{data.global_stats.total_errors}</div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="bg-gradient-to-br from-teal-500 to-teal-600 rounded-lg p-4 text-white shadow-lg"
        >
          <div className="text-sm font-medium opacity-90">Avg Success Rate</div>
          <div className="text-3xl font-bold mt-2">
            {data.global_stats.avg_success_rate.toFixed(1)}%
          </div>
        </motion.div>
      </div>

      {/* Comparative Analysis */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="bg-white rounded-lg shadow-md p-6"
      >
        <h3 className="text-xl font-semibold text-gray-800 mb-4">🏆 Comparative Analysis</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-sm text-gray-500">⚡ Fastest</div>
            <div className="font-semibold text-gray-800">
              {data.comparative_analysis.fastest_plugin}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-500">🐌 Slowest</div>
            <div className="font-semibold text-gray-800">
              {data.comparative_analysis.slowest_plugin}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-500">✅ Most Reliable</div>
            <div className="font-semibold text-gray-800">
              {data.comparative_analysis.most_reliable}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-500">⚠️ Least Reliable</div>
            <div className="font-semibold text-gray-800">
              {data.comparative_analysis.least_reliable}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-500">📈 Most Used</div>
            <div className="font-semibold text-gray-800">
              {data.comparative_analysis.most_used}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-500">📉 Least Used</div>
            <div className="font-semibold text-gray-800">
              {data.comparative_analysis.least_used}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-500">💚 Healthiest</div>
            <div className="font-semibold text-gray-800">
              {data.comparative_analysis.healthiest}
            </div>
          </div>
        </div>
      </motion.div>

      {/* Top Plugins */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.6 }}
        className="bg-white rounded-lg shadow-md p-6"
      >
        <h3 className="text-xl font-semibold text-gray-800 mb-4">📊 Top Plugins</h3>
        <div className="space-y-4">
          {data.top_plugins.map((plugin, index) => (
            <motion.div
              key={plugin.plugin_id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.7 + index * 0.1 }}
              className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">{getCategoryIcon(plugin.category)}</span>
                    <div>
                      <h4 className="font-semibold text-gray-800">{plugin.plugin_name}</h4>
                      <p className="text-sm text-gray-500 capitalize">{plugin.category}</p>
                    </div>
                  </div>
                  
                  <div className="mt-4 grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div>
                      <div className="text-xs text-gray-500">Invocations</div>
                      <div className="font-semibold text-gray-800">
                        {plugin.total_invocations.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500">Success Rate</div>
                      <div className="font-semibold text-green-600">
                        {plugin.success_rate.toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500">Avg Time</div>
                      <div className="font-semibold text-gray-800">
                        {plugin.avg_execution_time_ms.toFixed(1)}ms
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500">Errors</div>
                      <div className="font-semibold text-red-600">
                        {plugin.failed_invocations}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500">Health Score</div>
                      <div className={`font-semibold ${getHealthColor(plugin.health_score)}`}>
                        {plugin.health_score.toFixed(1)}
                      </div>
                    </div>
                  </div>

                  {/* Health Bar */}
                  <div className="mt-3">
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${plugin.health_score}%` }}
                        transition={{ duration: 0.5, delay: 0.8 + index * 0.1 }}
                        className={`${getHealthBgColor(plugin.health_score)} h-2 rounded-full`}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </div>
  );
};

export default PluginAnalytics;
