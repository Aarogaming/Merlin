import { useCallback, useEffect, useState, type CSSProperties } from 'react';
import { Activity, Users, TrendingUp, Clock, CheckCircle, AlertCircle } from 'lucide-react';
import './AgentAnalytics.css';

interface AgentPerformanceMetrics {
  agent_id: string;
  agent_name: string;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  success_rate: number;
  avg_completion_time: number;
  current_load: number;
  status: string;
  capabilities: string[];
  last_activity: string | null;
}

interface AgentAnalyticsData {
  total_agents: number;
  active_agents: number;
  total_tasks_completed: number;
  overall_success_rate: number;
  avg_completion_time: number;
  agents: AgentPerformanceMetrics[];
  timestamp: string;
  fallback_taxonomy_counts?: Record<string, unknown>;
  error?: string;
}

interface AgentAnalyticsProps {
  apiUrl?: string;
  refreshInterval?: number; // milliseconds
}

interface FallbackTrendPoint {
  timestamp: number;
  counts: Record<string, number>;
}

const FALLBACK_TREND_MAX_POINTS = 20;
const FALLBACK_TAXONOMY_COLORS = ['#38bdf8', '#f59e0b', '#22c55e', '#f43f5e', '#a78bfa'];

const normalizeFallbackTaxonomyCounts = (value: unknown): Record<string, number> => {
  if (!value || typeof value !== 'object') {
    return {};
  }
  const normalized: Record<string, number> = {};
  for (const [key, rawCount] of Object.entries(value)) {
    if (typeof key !== 'string') {
      continue;
    }
    const count = Number(rawCount);
    if (Number.isFinite(count) && count >= 0) {
      normalized[key] = Math.round(count);
    }
  }
  return normalized;
};

const formatFallbackTaxonomyLabel = (taxonomy: string): string =>
  taxonomy
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());

const buildSparklinePoints = (samples: number[]): string => {
  if (!samples.length) {
    return '';
  }
  const max = Math.max(...samples, 1);
  const denominator = Math.max(samples.length - 1, 1);
  return samples
    .map((value, index) => {
      const x = (index / denominator) * 100;
      const y = 28 - (value / max) * 24;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
};

export default function AgentAnalytics({
  apiUrl = 'http://localhost:8001',
  refreshInterval = 15000
}: AgentAnalyticsProps) {
  const [analyticsData, setAnalyticsData] = useState<AgentAnalyticsData | null>(null);
  const [fallbackTrend, setFallbackTrend] = useState<FallbackTrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchAnalytics = useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/agent/analytics`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data: AgentAnalyticsData = await response.json();
      
      if (data.error) {
        setError(data.error);
      } else {
        setAnalyticsData(data);
        const normalizedCounts = normalizeFallbackTaxonomyCounts(data.fallback_taxonomy_counts);
        if (Object.keys(normalizedCounts).length > 0) {
          setFallbackTrend((previousTrend) => {
            const nextSample: FallbackTrendPoint = {
              timestamp: Date.now(),
              counts: normalizedCounts,
            };
            const nextTrend = [...previousTrend, nextSample];
            return nextTrend.slice(-FALLBACK_TREND_MAX_POINTS);
          });
        }
        setError(null);
      }
      
      setLastUpdate(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch analytics');
      console.error('Failed to fetch agent analytics:', err);
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchAnalytics();
    const interval = setInterval(fetchAnalytics, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchAnalytics, refreshInterval]);

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'busy':
        return 'text-yellow-500';
      case 'idle':
        return 'text-green-500';
      case 'offline':
        return 'text-gray-500';
      default:
        return 'text-blue-500';
    }
  };

  const getLoadColor = (load: number) => {
    if (load >= 0.8) return 'bg-red-500';
    if (load >= 0.5) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  if (loading && !analyticsData) {
    return (
      <div className="bg-gray-800 p-6 rounded-lg">
        <div className="animate-pulse flex space-x-4">
          <div className="flex-1 space-y-4 py-1">
            <div className="h-4 bg-gray-700 rounded w-3/4"></div>
            <div className="space-y-2">
              <div className="h-4 bg-gray-700 rounded"></div>
              <div className="h-4 bg-gray-700 rounded w-5/6"></div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-800 p-6 rounded-lg">
        <div className="flex items-center text-red-500 mb-2">
          <AlertCircle className="mr-2" size={20} />
          <h3 className="text-lg font-semibold">Error Loading Agent Analytics</h3>
        </div>
        <p className="text-gray-400">{error}</p>
        <button
          onClick={fetchAnalytics}
          className="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!analyticsData) {
    return null;
  }

  const fallbackTaxonomyEntries = Object.entries(
    normalizeFallbackTaxonomyCounts(analyticsData.fallback_taxonomy_counts)
  ).sort((left, right) => right[1] - left[1]);
  const fallbackTaxonomyTop = fallbackTaxonomyEntries.slice(0, 3);
  const fallbackTrendReady = fallbackTrend.length > 1 && fallbackTaxonomyTop.length > 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-white flex items-center">
          <Activity className="mr-2" size={28} />
          AI Agent Analytics
        </h2>
        {lastUpdate && (
          <span className="text-sm text-gray-400">
            Updated: {lastUpdate.toLocaleTimeString()}
          </span>
        )}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Agents */}
        <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
          <div className="flex items-center justify-between">
            <Users className="text-blue-500" size={24} />
            <span className="text-2xl font-bold text-white">{analyticsData.total_agents}</span>
          </div>
          <p className="text-gray-400 mt-2 text-sm">Total Agents</p>
          <p className="text-green-500 text-xs mt-1">
            {analyticsData.active_agents} active
          </p>
        </div>

        {/* Tasks Completed */}
        <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
          <div className="flex items-center justify-between">
            <CheckCircle className="text-green-500" size={24} />
            <span className="text-2xl font-bold text-white">
              {analyticsData.total_tasks_completed}
            </span>
          </div>
          <p className="text-gray-400 mt-2 text-sm">Tasks Completed</p>
        </div>

        {/* Success Rate */}
        <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
          <div className="flex items-center justify-between">
            <TrendingUp className="text-yellow-500" size={24} />
            <span className="text-2xl font-bold text-white">
              {analyticsData.overall_success_rate}%
            </span>
          </div>
          <p className="text-gray-400 mt-2 text-sm">Success Rate</p>
        </div>

        {/* Avg Completion Time */}
        <div className="bg-gray-800 p-4 rounded-lg border border-gray-700">
          <div className="flex items-center justify-between">
            <Clock className="text-purple-500" size={24} />
            <span className="text-2xl font-bold text-white">
              {analyticsData.avg_completion_time}m
            </span>
          </div>
          <p className="text-gray-400 mt-2 text-sm">Avg Time</p>
        </div>
      </div>

      {/* Fallback Taxonomy Panel */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 fallback-taxonomy-panel">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-lg font-semibold text-white">Fallback Taxonomy</h3>
          <span className="text-xs text-gray-400">
            {fallbackTaxonomyEntries.length
              ? `${fallbackTaxonomyEntries.length} categories observed`
              : 'No fallback events reported'}
          </span>
        </div>
        {fallbackTaxonomyEntries.length > 0 ? (
          <>
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {fallbackTaxonomyEntries.map(([taxonomy, count], index) => (
                <div
                  key={taxonomy}
                  className="fallback-taxonomy-item bg-gray-900 border border-gray-700 rounded-md px-3 py-2"
                >
                  <div className="text-xs text-gray-400">{formatFallbackTaxonomyLabel(taxonomy)}</div>
                  <div className="text-lg font-semibold text-white">{count.toLocaleString()}</div>
                  <div
                    className="fallback-taxonomy-swatch"
                    style={{ ['--fallback-color' as string]: FALLBACK_TAXONOMY_COLORS[index % FALLBACK_TAXONOMY_COLORS.length] } as CSSProperties}
                    aria-hidden="true"
                  />
                </div>
              ))}
            </div>
            <div className="mt-4">
              <p className="text-xs text-gray-400 mb-2">Trend line (recent refreshes)</p>
              {fallbackTrendReady ? (
                <div className="space-y-2">
                  {fallbackTaxonomyTop.map(([taxonomy, count], index) => {
                    const color = FALLBACK_TAXONOMY_COLORS[index % FALLBACK_TAXONOMY_COLORS.length];
                    const samples = fallbackTrend.map((point) => point.counts[taxonomy] ?? 0);
                    return (
                      <div key={taxonomy} className="grid grid-cols-[minmax(120px,1fr)_4fr_auto] items-center gap-3">
                        <span className="text-xs text-gray-300 truncate">
                          {formatFallbackTaxonomyLabel(taxonomy)}
                        </span>
                        <svg
                          className="w-full h-8 overflow-visible"
                          viewBox="0 0 100 28"
                          role="img"
                          aria-label={`${formatFallbackTaxonomyLabel(taxonomy)} trend`}
                        >
                          <polyline
                            fill="none"
                            stroke={color}
                            strokeWidth="2"
                            points={buildSparklinePoints(samples)}
                          />
                        </svg>
                        <span className="text-xs text-gray-300">{count.toLocaleString()}</span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-gray-500">
                  Collecting trend data. Refresh a few more times to display spark lines.
                </p>
              )}
            </div>
          </>
        ) : (
          <p className="mt-3 text-sm text-gray-500">
            No fallback taxonomy counts are currently available in this analytics payload.
          </p>
        )}
      </div>

      {/* Agent Details */}
      <div className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-700">
          <h3 className="text-xl font-semibold text-white">Agent Performance</h3>
        </div>
        <div className="p-6">
          <div className="space-y-4">
            {analyticsData.agents.map((agent) => (
              <div
                key={agent.agent_id}
                className="bg-gray-900 p-4 rounded-lg border border-gray-700"
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h4 className="text-lg font-semibold text-white">{agent.agent_name}</h4>
                    <span className={`text-sm ${getStatusColor(agent.status)}`}>
                      {agent.status.toUpperCase()}
                    </span>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-gray-400">Load</div>
                    <div className="w-24 h-2 bg-gray-700 rounded-full mt-1">
                      <div
                        className={`h-full rounded-full agent-load-bar ${getLoadColor(agent.current_load)}`}
                        style={{ ['--bar-width' as string]: `${agent.current_load * 100}%` } as CSSProperties}
                      ></div>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
                  <div>
                    <div className="text-xs text-gray-400">Total Tasks</div>
                    <div className="text-lg font-semibold text-white">{agent.total_tasks}</div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400">Completed</div>
                    <div className="text-lg font-semibold text-green-500">
                      {agent.completed_tasks}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400">Success Rate</div>
                    <div className="text-lg font-semibold text-white">
                      {agent.success_rate.toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400">Avg Time</div>
                    <div className="text-lg font-semibold text-white">
                      {agent.avg_completion_time.toFixed(1)}m
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {agent.capabilities.map((capability) => (
                    <span
                      key={capability}
                      className="px-2 py-1 bg-blue-900 text-blue-300 text-xs rounded"
                    >
                      {capability.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>

                {agent.last_activity && (
                  <div className="mt-2 text-xs text-gray-500">
                    Last active: {new Date(agent.last_activity).toLocaleString()}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
