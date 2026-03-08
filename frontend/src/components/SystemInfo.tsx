import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Cpu,
  HardDrive,
  Network,
  Zap,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import toast from 'react-hot-toast';
import './SystemInfo.css';

interface SystemInfoData {
  os: string;
  os_release: string;
  os_version: string;
  architecture: string;
  hostname: string;
  cpu_count: number;
  cpu_usage_percent: number;
  memory_total_gb: number;
  memory_available_gb: number;
  memory_usage_percent: number;
  disk_total_gb: number;
  disk_free_gb: number;
  disk_usage_percent: number;
  network_interfaces: string[];
  error?: string;
}

interface SystemInfoProps {
  myFortressUrl?: string;
  refreshInterval?: number;
}

const SystemInfo = ({
  myFortressUrl = 'http://localhost:8001',
  refreshInterval = 5000,
}: SystemInfoProps) => {
  const [systemInfo, setSystemInfo] = useState<SystemInfoData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchSystemInfo = useCallback(async () => {
    try {
      setError(null);
      const response = await fetch(`${myFortressUrl}/system/info`);

      if (!response.ok) {
        throw new Error(`Failed to fetch system info: ${response.status}`);
      }

      const data: SystemInfoData = await response.json();

      if (data.error) {
        setError(data.error);
        setSystemInfo(null);
      } else {
        setSystemInfo(data);
        setLastUpdate(new Date());
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMsg);
      setSystemInfo(null);
      toast.error(`Failed to fetch system info: ${errorMsg}`);
    } finally {
      setLoading(false);
    }
  }, [myFortressUrl]);

  useEffect(() => {
    fetchSystemInfo();

    const interval = setInterval(() => {
      fetchSystemInfo();
    }, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval, fetchSystemInfo]);

  const getMemoryUsageColor = (percent: number): string => {
    if (percent < 50) return 'text-green-400';
    if (percent < 80) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getDiskUsageColor = (percent: number): string => {
    if (percent < 50) return 'text-green-400';
    if (percent < 80) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getCpuUsageColor = (percent: number): string => {
    if (percent < 50) return 'text-green-400';
    if (percent < 80) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getProgressBarColor = (percent: number): string => {
    if (percent < 50) return 'bg-green-400';
    if (percent < 80) return 'bg-yellow-400';
    return 'bg-red-400';
  };

  const hasHighUtilization =
    Boolean(systemInfo && systemInfo.cpu_usage_percent >= 90) ||
    Boolean(systemInfo && systemInfo.memory_usage_percent >= 90) ||
    Boolean(systemInfo && systemInfo.disk_usage_percent >= 90);

  const shouldShowRetryGuidance = Boolean(error) || hasHighUtilization;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="bg-dark-secondary rounded-lg border border-dark-border p-6 space-y-4 system-info-card"
      role="region"
      aria-label="System information panel"
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-bold text-gradient">MyFortress System Info</h2>
        <button
          onClick={() => fetchSystemInfo()}
          disabled={loading}
          title="Refresh system information"
          aria-label="Refresh system information"
          className="p-2 hover:bg-dark-hover rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 flex items-start gap-3"
          role="status"
          aria-live="polite"
        >
          <AlertCircle size={20} className="text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-red-400 font-medium">Error fetching system info</p>
            <p className="text-red-300 text-sm">{error}</p>
          </div>
        </motion.div>
      )}

      {shouldShowRetryGuidance && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 space-y-3 system-retry-guidance">
          <p className="text-sm font-semibold text-amber-200">Retry Guidance</p>
          <ul className="text-xs text-amber-100 space-y-1 list-disc pl-4">
            <li>Confirm <code>{myFortressUrl}/system/info</code> is reachable from this host.</li>
            <li>If usage remains high, wait for load to drop before re-querying diagnostics.</li>
            <li>Retry manually after backend restarts to clear stale fallback readings.</li>
          </ul>
          <button
            type="button"
            onClick={() => fetchSystemInfo()}
            disabled={loading}
            className="btn-secondary text-xs px-3 py-1.5"
            aria-label="Retry system information fetch"
          >
            {loading ? 'Retrying...' : 'Retry System Info Fetch'}
          </button>
        </div>
      )}

      {!loading && systemInfo && !error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="space-y-4"
        >
          {/* System Basics */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-dark-hover rounded p-3">
              <p className="text-dark-muted text-sm">Hostname</p>
              <p className="text-white font-medium text-lg">{systemInfo.hostname}</p>
            </div>
            <div className="bg-dark-hover rounded p-3">
              <p className="text-dark-muted text-sm">Operating System</p>
              <p className="text-white font-medium text-lg">{systemInfo.os}</p>
            </div>
            <div className="bg-dark-hover rounded p-3">
              <p className="text-dark-muted text-sm">Architecture</p>
              <p className="text-white font-medium text-lg">{systemInfo.architecture}</p>
            </div>
            <div className="bg-dark-hover rounded p-3">
              <p className="text-dark-muted text-sm">OS Version</p>
              <p className="text-white font-medium text-sm truncate">{systemInfo.os_release}</p>
            </div>
          </div>

          {/* Resource Usage */}
          <div className="space-y-3">
            {/* CPU */}
            <div className="bg-dark-hover rounded p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Cpu size={18} className="text-blue-400" />
                  <span className="text-dark-muted">CPU Usage</span>
                </div>
                <span className={`font-bold ${getCpuUsageColor(systemInfo.cpu_usage_percent)}`}>
                  {systemInfo.cpu_usage_percent.toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-dark-secondary rounded-full h-2 system-info-bar">
                <div
                  className={`h-full rounded-full transition-all ${getProgressBarColor(systemInfo.cpu_usage_percent)}`}
                  style={{ '--bar-width': `${Math.min(systemInfo.cpu_usage_percent, 100)}%` } as React.CSSProperties}
                />
              </div>
              <p className="text-dark-muted text-sm">{systemInfo.cpu_count} cores available</p>
            </div>

            {/* Memory */}
            <div className="bg-dark-hover rounded p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Zap size={18} className="text-purple-400" />
                  <span className="text-dark-muted">Memory Usage</span>
                </div>
                <span className={`font-bold ${getMemoryUsageColor(systemInfo.memory_usage_percent)}`}>
                  {systemInfo.memory_usage_percent.toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-dark-secondary rounded-full h-2 system-info-bar">
                <div
                  className={`h-full rounded-full transition-all ${getProgressBarColor(systemInfo.memory_usage_percent)}`}
                  style={{ '--bar-width': `${Math.min(systemInfo.memory_usage_percent, 100)}%` } as React.CSSProperties}
                />
              </div>
              <p className="text-dark-muted text-sm">
                {systemInfo.memory_available_gb.toFixed(1)} GB / {systemInfo.memory_total_gb.toFixed(1)} GB available
              </p>
            </div>

            {/* Disk */}
            <div className="bg-dark-hover rounded p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <HardDrive size={18} className="text-green-400" />
                  <span className="text-dark-muted">Disk Usage</span>
                </div>
                <span className={`font-bold ${getDiskUsageColor(systemInfo.disk_usage_percent)}`}>
                  {systemInfo.disk_usage_percent.toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-dark-secondary rounded-full h-2 system-info-bar">
                <div
                  className={`h-full rounded-full transition-all ${getProgressBarColor(systemInfo.disk_usage_percent)}`}
                  style={{ '--bar-width': `${Math.min(systemInfo.disk_usage_percent, 100)}%` } as React.CSSProperties}
                />
              </div>
              <p className="text-dark-muted text-sm">
                {systemInfo.disk_free_gb.toFixed(1)} GB free / {systemInfo.disk_total_gb.toFixed(1)} GB total
              </p>
            </div>
          </div>

          {/* Network Interfaces */}
          {systemInfo.network_interfaces.length > 0 && (
            <div className="bg-dark-hover rounded p-4">
              <div className="flex items-center gap-2 mb-2">
                <Network size={18} className="text-orange-400" />
                <span className="text-dark-muted">Network Interfaces</span>
              </div>
              <div className="flex flex-wrap gap-2 min-w-0">
                {systemInfo.network_interfaces.map((iface) => (
                  <span
                    key={iface}
                    className="bg-dark-secondary px-3 py-1 rounded-full text-sm text-light-muted max-w-full break-all"
                  >
                    {iface}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Last Update */}
          {lastUpdate && (
            <p className="text-dark-muted text-xs text-right">
              Last updated: {lastUpdate.toLocaleTimeString()}
            </p>
          )}
        </motion.div>
      )}

      {loading && !systemInfo && (
        <div className="flex items-center justify-center py-8" aria-live="polite">
          <div className="text-center">
            <div className="animate-spin w-8 h-8 border-2 border-merlin-blue border-t-transparent rounded-full mx-auto mb-4" />
            <p className="text-dark-muted">Loading system information...</p>
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default SystemInfo;
