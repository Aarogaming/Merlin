import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  CheckCircle,
  XCircle,
  AlertCircle,
  RefreshCw,
  Home,
  Video,
  Activity,
} from 'lucide-react';
import toast from 'react-hot-toast';
import './SnapshotSummary.css';

interface EntityReading {
  entity_id: string;
  state: unknown;
  attributes: Record<string, unknown>;
  error?: string;
}

interface HomeMerlinSnapshot {
  healthy: boolean;
  readings: Record<string, EntityReading>;
  error?: string;
}

interface FrigateVersion {
  version?: string;
  extra?: Record<string, unknown>;
}

interface FrigateSnapshot {
  healthy: boolean;
  version?: FrigateVersion;
  error?: string;
  cameras?: string[];
}

interface GatewaySnapshot {
  home_assistant?: HomeMerlinSnapshot;
  frigate?: FrigateSnapshot;
}

interface SnapshotSummaryProps {
  myFortressUrl?: string;
  refreshInterval?: number;
  includeHomeAssistant?: boolean;
  includeFrigate?: boolean;
  homeAssistantEntities?: string[];
}

const SnapshotSummary = ({
  myFortressUrl = 'http://localhost:8001',
  refreshInterval = 10000,
  includeHomeAssistant = true,
  includeFrigate = true,
  homeAssistantEntities = [],
}: SnapshotSummaryProps) => {
  const [snapshot, setSnapshot] = useState<GatewaySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchSnapshot = useCallback(async () => {
    try {
      setError(null);
      const response = await fetch(`${myFortressUrl}/snapshot`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          include_home_assistant: includeHomeAssistant,
          include_frigate: includeFrigate,
          include_frigate_cameras: true,
          home_assistant_entities: homeAssistantEntities,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch snapshot: ${response.status}`);
      }

      const data: GatewaySnapshot = await response.json();
      setSnapshot(data);
      setLastUpdate(new Date());
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Unknown error';
      setError(errorMsg);
      toast.error(`Failed to fetch snapshot: ${errorMsg}`);
    } finally {
      setLoading(false);
    }
  }, [myFortressUrl, includeHomeAssistant, includeFrigate, homeAssistantEntities]);

  useEffect(() => {
    fetchSnapshot();

    const interval = setInterval(() => {
      fetchSnapshot();
    }, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval, fetchSnapshot]);

  const getHealthIcon = (healthy: boolean) => {
    return healthy ? (
      <CheckCircle size={18} className="text-green-400" />
    ) : (
      <XCircle size={18} className="text-red-400" />
    );
  };

  const getHealthColor = (healthy: boolean) => {
    return healthy ? 'text-green-400' : 'text-red-400';
  };

  const getHealthBgColor = (healthy: boolean) => {
    return healthy ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30';
  };

  const hasUnhealthySubsystem =
    Boolean(snapshot?.home_assistant && !snapshot.home_assistant.healthy) ||
    Boolean(snapshot?.frigate && !snapshot.frigate.healthy);

  const shouldShowRetryGuidance = Boolean(error) || hasUnhealthySubsystem;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="bg-dark-secondary rounded-lg border border-dark-border p-6 space-y-4 snapshot-summary-card"
      role="region"
      aria-label="Gateway snapshot summary"
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Activity size={20} className="text-merlin-blue" />
          <h2 className="text-xl font-bold text-gradient">Gateway Snapshot</h2>
        </div>
        <button
          onClick={() => fetchSnapshot()}
          disabled={loading}
          title="Refresh snapshot"
          aria-label="Refresh gateway snapshot"
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
            <p className="text-red-400 font-medium">Error fetching snapshot</p>
            <p className="text-red-300 text-sm">{error}</p>
          </div>
        </motion.div>
      )}

      {shouldShowRetryGuidance && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 space-y-3 snapshot-retry-guidance">
          <p className="text-sm font-semibold text-amber-200">Retry Guidance</p>
          <ul className="text-xs text-amber-100 space-y-1 list-disc pl-4">
            <li>Confirm the MyFortress gateway process is reachable at <code>{myFortressUrl}</code>.</li>
            <li>Check Home Assistant and Frigate service health before retrying.</li>
            <li>Use manual refresh after dependency recovery to clear fallback state.</li>
          </ul>
          <button
            type="button"
            onClick={() => fetchSnapshot()}
            disabled={loading}
            className="btn-secondary text-xs px-3 py-1.5"
            aria-label="Retry gateway snapshot fetch"
          >
            {loading ? 'Retrying...' : 'Retry Snapshot Fetch'}
          </button>
        </div>
      )}

      {!loading && snapshot && !error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="space-y-4"
        >
          {/* Home Assistant Section */}
          {snapshot.home_assistant && (
            <div className={`rounded-lg border p-4 ${getHealthBgColor(snapshot.home_assistant.healthy)}`}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Home size={18} className={getHealthColor(snapshot.home_assistant.healthy)} />
                  <h3 className="font-semibold text-white">Home Assistant</h3>
                </div>
                {getHealthIcon(snapshot.home_assistant.healthy)}
              </div>

              {snapshot.home_assistant.error && (
                <div className="bg-red-500/10 rounded p-2 mb-3">
                  <p className="text-red-300 text-sm">{snapshot.home_assistant.error}</p>
                </div>
              )}

              {snapshot.home_assistant.readings && Object.keys(snapshot.home_assistant.readings).length > 0 && (
                <div className="space-y-2">
                  <p className="text-dark-muted text-sm font-medium">
                    Entities: {Object.keys(snapshot.home_assistant.readings).length}
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {Object.entries(snapshot.home_assistant.readings).slice(0, 6).map(([id, reading]) => (
                    <div key={id} className="bg-dark-secondary rounded p-2 min-w-0">
                        <p className="text-xs text-dark-muted truncate">{reading.entity_id}</p>
                        <p className="text-sm text-white font-medium truncate">
                          {reading.error ? (
                            <span className="text-red-400">Error</span>
                          ) : (
                            String(reading.state)
                          )}
                        </p>
                      </div>
                    ))}
                  </div>
                  {Object.keys(snapshot.home_assistant.readings).length > 6 && (
                    <p className="text-xs text-dark-muted">
                      +{Object.keys(snapshot.home_assistant.readings).length - 6} more entities
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Frigate Section */}
          {snapshot.frigate && (
            <div className={`rounded-lg border p-4 ${getHealthBgColor(snapshot.frigate.healthy)}`}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Video size={18} className={getHealthColor(snapshot.frigate.healthy)} />
                  <h3 className="font-semibold text-white">Frigate</h3>
                </div>
                {getHealthIcon(snapshot.frigate.healthy)}
              </div>

              {snapshot.frigate.error && (
                <div className="bg-red-500/10 rounded p-2 mb-3">
                  <p className="text-red-300 text-sm">{snapshot.frigate.error}</p>
                </div>
              )}

              <div className="space-y-2">
                {snapshot.frigate.version && (
                  <div className="bg-dark-secondary rounded p-2">
                    <p className="text-xs text-dark-muted">Version</p>
                    <p className="text-sm text-white font-medium">
                      {snapshot.frigate.version.version || 'Unknown'}
                    </p>
                  </div>
                )}

                {snapshot.frigate.cameras && snapshot.frigate.cameras.length > 0 && (
                  <div className="bg-dark-secondary rounded p-2">
                    <p className="text-xs text-dark-muted mb-1">
                      Cameras: {snapshot.frigate.cameras.length}
                    </p>
                    <div className="flex flex-wrap gap-1 min-w-0">
                      {snapshot.frigate.cameras.slice(0, 8).map((camera) => (
                        <span
                          key={camera}
                          className="bg-dark-hover px-2 py-1 rounded text-xs text-light-muted max-w-full break-all"
                        >
                          {camera}
                        </span>
                      ))}
                    </div>
                    {snapshot.frigate.cameras.length > 8 && (
                      <p className="text-xs text-dark-muted mt-1">
                        +{snapshot.frigate.cameras.length - 8} more cameras
                      </p>
                    )}
                  </div>
                )}
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

      {loading && !snapshot && (
        <div className="flex items-center justify-center py-8" aria-live="polite">
          <div className="text-center">
            <div className="animate-spin w-8 h-8 border-2 border-merlin-blue border-t-transparent rounded-full mx-auto mb-4" />
            <p className="text-dark-muted">Loading snapshot...</p>
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default SnapshotSummary;
