import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Compass, ExternalLink, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import ConnectionStatus from '../components/ConnectionStatus';
import { useOnboardingStore } from '../store/onboarding';
import { useDashboardStore } from '../store/dashboard';

type ControlLink = {
  id: string;
  label: string;
  description: string;
  url: string;
  status: string;
  meta?: string;
};

type InventoryNode = {
  id: string;
  name?: string;
  type?: string;
  version?: string;
  source?: string;
  installed?: boolean;
  running?: boolean;
  mesh_registered?: boolean;
  health?: string;
  capabilities?: string[];
  interfaces?: Array<{ endpoint?: string | null }>;
};

type RegistryCapabilities = Record<string, Array<{ plugin?: string }>>;

type RegistryStatus = {
  total?: number;
  installed?: number;
  running?: number;
  mesh_registered?: number;
  services?: number;
};

type UiImageEntry = {
  name: string;
  path: string;
  size_bytes?: number;
  updated_at?: string;
};

const statusTone = (status: string) => {
  const key = status.toLowerCase();
  if (['healthy', 'ok', 'online', 'connected', 'ready'].includes(key)) {
    return 'bg-green-500/10 border-green-500/30 text-green-200';
  }
  if (['warning', 'degraded', 'partial'].includes(key)) {
    return 'bg-amber-500/10 border-amber-500/30 text-amber-200';
  }
  if (['offline', 'error', 'failed', 'down'].includes(key)) {
    return 'bg-red-500/10 border-red-500/30 text-red-200';
  }
  return 'bg-slate-800 border-slate-700 text-slate-300';
};

const formatStatusLabel = (status: string) => status.replace(/_/g, ' ').toUpperCase();

const ControlCenter = () => {
  const apiUrl = useOnboardingStore((state) => state.apiUrl);
  const { connectionStatus } = useDashboardStore();
  const baseUrl = useMemo(
    () => (apiUrl || 'http://localhost:8000').replace(/\/$/, ''),
    [apiUrl]
  );
  const [hubHealth, setHubHealth] = useState<Record<string, unknown> | null>(null);
  const [hubLatency, setHubLatency] = useState<number | null>(null);
  const [hubError, setHubError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [registryNodes, setRegistryNodes] = useState<InventoryNode[]>([]);
  const [registryStatus, setRegistryStatus] = useState<RegistryStatus | null>(null);
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [registryCapabilities, setRegistryCapabilities] = useState<RegistryCapabilities>({});
  const [capabilityName, setCapabilityName] = useState('');
  const [capabilityArgs, setCapabilityArgs] = useState('{}');
  const [capabilityProvider, setCapabilityProvider] = useState('');
  const [capabilityResult, setCapabilityResult] = useState<string | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [capabilityBusy, setCapabilityBusy] = useState(false);
  const [uiImages, setUiImages] = useState<UiImageEntry[]>([]);
  const [uiImageError, setUiImageError] = useState<string | null>(null);
  const [uiImageAutoRefresh, setUiImageAutoRefresh] = useState(false);
  const [uiImageIntervalSec, setUiImageIntervalSec] = useState(60);
  const [uiImageCaptureBusy, setUiImageCaptureBusy] = useState(false);
  const [uiImageCaptureError, setUiImageCaptureError] = useState<string | null>(null);
  const [uiImageCaptureResult, setUiImageCaptureResult] = useState<Record<string, unknown> | null>(null);

  const fetchHubHealth = useCallback(async () => {
    setChecking(true);
    setHubError(null);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 1500);
    try {
      const started = performance.now();
      const response = await fetch(`${baseUrl}/health`, { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`Hub health check failed (${response.status})`);
      }
      const data = await response.json();
      setHubHealth(data);
      setHubLatency(Math.round(performance.now() - started));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to reach hub';
      setHubHealth(null);
      setHubLatency(null);
      setHubError(message);
    } finally {
      window.clearTimeout(timer);
      setChecking(false);
    }
  }, [baseUrl]);

  const fetchRegistry = useCallback(async () => {
    try {
      setRegistryError(null);
      let nodesRes = await fetch(`${baseUrl}/plugins/inventory`);
      if (!nodesRes.ok) {
        nodesRes = await fetch(`${baseUrl}/registry/nodes`);
      }
      if (!nodesRes.ok) {
        throw new Error(`Registry nodes failed (${nodesRes.status})`);
      }
      const nodesPayload = await nodesRes.json();
      const nodes = nodesPayload.nodes || nodesPayload.plugins || [];
      setRegistryNodes(Array.isArray(nodes) ? nodes : []);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load registry nodes';
      setRegistryNodes([]);
      setRegistryError(message);
    }

    try {
      let statusRes = await fetch(`${baseUrl}/plugins/status`);
      if (!statusRes.ok) {
        statusRes = await fetch(`${baseUrl}/registry/status`);
      }
      if (!statusRes.ok) {
        throw new Error(`Registry status failed (${statusRes.status})`);
      }
      const statusPayload = await statusRes.json();
      setRegistryStatus(statusPayload.status || null);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load registry status';
      setRegistryStatus(null);
      setRegistryError((prev) => prev || message);
    }

    try {
      let capsRes = await fetch(`${baseUrl}/capabilities`);
      if (!capsRes.ok) {
        capsRes = await fetch(`${baseUrl}/registry/capabilities`);
      }
      if (!capsRes.ok) {
        throw new Error(`Registry capabilities failed (${capsRes.status})`);
      }
      const capsPayload = await capsRes.json();
      setRegistryCapabilities(capsPayload.capabilities || {});
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load registry capabilities';
      setRegistryCapabilities({});
      setRegistryError((prev) => prev || message);
    }
  }, [baseUrl]);

  const fetchUiImages = useCallback(async () => {
    try {
      setUiImageError(null);
      const response = await fetch(`${baseUrl}/ui-imaging/list?limit=24`);
      if (!response.ok) {
        throw new Error(`UI images failed (${response.status})`);
      }
      const payload = await response.json();
      setUiImages(Array.isArray(payload.images) ? payload.images : []);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load UI images';
      setUiImages([]);
      setUiImageError(message);
    }
  }, [baseUrl]);

  useEffect(() => {
    fetchHubHealth();
    fetchRegistry();
    fetchUiImages();
  }, [fetchHubHealth, fetchRegistry, fetchUiImages]);

  useEffect(() => {
    if (!uiImageAutoRefresh) return undefined;
    const intervalMs = Math.max(10, uiImageIntervalSec) * 1000;
    const timer = window.setInterval(() => {
      fetchUiImages();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [fetchUiImages, uiImageAutoRefresh, uiImageIntervalSec]);

  const hubStatus = useMemo(() => {
    const status = hubHealth?.status || hubHealth?.overall_status;
    if (status) return String(status);
    if (hubError) return 'offline';
    if (connectionStatus.connected) return 'connected';
    return 'unknown';
  }, [hubHealth, hubError, connectionStatus.connected]);

  const merlinUrl = useMemo(() => {
    if (typeof window === 'undefined') return `${baseUrl}/merlin`;
    const origin = window.location.origin;
    if (window.location.pathname.startsWith('/merlin')) {
      return `${origin}/merlin`;
    }
    return origin;
  }, [baseUrl]);

  const controlLinks = useMemo<ControlLink[]>(
    () => [
      {
        id: 'mission-control',
        label: 'Mission Control',
        description: 'Primary AAS command dashboard',
        url: baseUrl,
        status: hubStatus,
        meta: hubLatency ? `${hubLatency} ms` : undefined,
      },
      {
        id: 'merlin',
        label: 'Merlin',
        description: 'Planning, research, and assistance',
        url: merlinUrl,
        status: connectionStatus.connected ? 'connected' : 'idle',
      },
      {
        id: 'fortress',
        label: 'Fortress',
        description: 'Home-link sector and automation',
        url: `${baseUrl}/fortress`,
        status: 'unknown',
      },
      {
        id: 'hive',
        label: 'Hive',
        description: 'Coordinator layer and swarm registry',
        url: `${baseUrl}/hive`,
        status: 'unknown',
      },
      {
        id: 'swarm',
        label: 'Swarm',
        description: 'Distributed agents and task mesh',
        url: `${baseUrl}/swarm`,
        status: 'unknown',
      },
      {
        id: 'plugins',
        label: 'Plugins',
        description: 'Plugin catalog and runtime controls',
        url: `${baseUrl}/plugins`,
        status: 'catalog',
      },
    ],
    [baseUrl, connectionStatus.connected, hubLatency, hubStatus, merlinUrl]
  );

  const registryCapabilityEntries = useMemo(() => {
    return Object.entries(registryCapabilities)
      .map(([name, providers]) => ({
        name,
        providers: (providers || []).map((provider) => provider.plugin || 'unknown').filter(Boolean)
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [registryCapabilities]);

  const openControlLink = useCallback((url: string) => {
    try {
      window.open(url, '_blank', 'noopener');
    } catch {
      toast.error('Unable to open link');
    }
  }, []);

  const resolveUiImageUrl = useCallback(
    (path: string) => `${baseUrl}/ui-imaging/file?path=${encodeURIComponent(path)}`,
    [baseUrl]
  );

  const invokeCapability = useCallback(async () => {
    const capability = capabilityName.trim();
    if (!capability) {
      setCapabilityError('Capability name is required.');
      return;
    }

    let parsedArgs: unknown = {};
    if (capabilityArgs.trim()) {
      try {
        parsedArgs = JSON.parse(capabilityArgs);
      } catch {
        setCapabilityError('Args must be valid JSON.');
        return;
      }
    }

    const provider = capabilityProvider.trim();
    setCapabilityBusy(true);
    setCapabilityError(null);
    setCapabilityResult(null);
    try {
      const response = await fetch(`${baseUrl}/capabilities/invoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          capability,
          args: parsedArgs,
          provider: provider || undefined,
        }),
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.detail || payload.error || `Invoke failed (${response.status})`);
      }
      setCapabilityResult(JSON.stringify(payload.result ?? payload, null, 2));
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Capability invoke failed';
      setCapabilityError(message);
    } finally {
      setCapabilityBusy(false);
    }
  }, [baseUrl, capabilityArgs, capabilityName, capabilityProvider]);

  const captureUiAudit = useCallback(async () => {
    setUiImageCaptureBusy(true);
    setUiImageCaptureError(null);
    setUiImageCaptureResult(null);
    try {
      const response = await fetch(`${baseUrl}/ui/self-review/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: 'mission_control', close_on_finish: true, output_tag: 'control-center' }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || `Self-review failed (${response.status})`);
      }
      setUiImageCaptureResult(payload);
      await fetchUiImages();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'UI capture failed';
      setUiImageCaptureError(message);
    } finally {
      setUiImageCaptureBusy(false);
    }
  }, [baseUrl, fetchUiImages]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-6"
    >
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Compass className="w-5 h-5 text-merlin-blue" />
            <h1 className="text-3xl font-bold text-gradient">Control Center</h1>
          </div>
          <p className="text-dark-muted">Jump between AAS subsystems, dashboards, and services.</p>
        </div>
        <ConnectionStatus />
      </div>

      <div className="card">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <p className="text-sm text-dark-muted">AAS Base URL</p>
            <p className="text-sm font-mono text-dark-text break-all">{baseUrl}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
              <span className={`inline-flex items-center rounded-full border px-2 py-1 ${statusTone(hubStatus)}`}>
                {formatStatusLabel(hubStatus)}
              </span>
              {hubLatency !== null && (
                <span className="text-dark-muted">Latency {hubLatency} ms</span>
              )}
              {hubError && (
                <span className="text-red-300">{hubError}</span>
              )}
            </div>
          </div>
          <button
            onClick={() => {
              fetchHubHealth();
              fetchRegistry();
              fetchUiImages();
            }}
            disabled={checking}
            className="btn-secondary flex items-center gap-2 text-sm disabled:opacity-60"
          >
            <RefreshCw size={16} className={checking ? 'animate-spin' : ''} />
            {checking ? 'Checking...' : 'Refresh Status'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {controlLinks.map((link) => (
          <div key={link.id} className="card space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-dark-text">{link.label}</p>
                <p className="text-xs text-dark-muted mt-1">{link.description}</p>
                {link.meta && (
                  <p className="text-xs text-dark-muted mt-2">{link.meta}</p>
                )}
              </div>
              <span className={`text-[10px] px-2 py-1 rounded-full border ${statusTone(link.status)}`}>
                {formatStatusLabel(link.status)}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-[10px] text-dark-muted truncate" title={link.url}>
                {link.url}
              </span>
              <button
                onClick={() => openControlLink(link.url)}
                className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold text-dark-text bg-dark-border rounded-md hover:bg-dark-hover transition"
              >
                <ExternalLink size={14} />
                Open
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <p className="text-sm font-semibold text-dark-text">Plugin Inventory</p>
            <p className="text-xs text-dark-muted">Runtime, local, and service nodes reconciled by the hub.</p>
          </div>
          <div className="flex items-center gap-3 text-xs text-dark-muted">
            <span>Total {registryStatus?.total ?? registryNodes.length}</span>
            <span>Running {registryStatus?.running ?? 0}</span>
            <span>Mesh {registryStatus?.mesh_registered ?? 0}</span>
          </div>
        </div>

        {registryError && (
          <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            {registryError}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {registryNodes.map((node) => {
            const statusLabel = node.health || (node.running ? 'running' : 'unknown');
            const statusClass = node.running
              ? 'bg-green-500/10 border-green-500/30 text-green-200'
              : 'bg-slate-800 border-slate-700 text-slate-300';
            const endpoint = node.interfaces?.[0]?.endpoint || '';

            return (
              <div key={node.id} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-dark-text">{node.name || node.id}</p>
                    <p className="text-xs text-dark-muted mt-1">{node.type || 'plugin'} · {node.source || 'local'}</p>
                    <p className="text-[10px] text-dark-muted mt-1">v{node.version || '0.0.0'}</p>
                  </div>
                  <span className={`text-[10px] px-2 py-1 rounded-full border ${statusClass}`}>
                    {formatStatusLabel(statusLabel)}
                  </span>
                </div>
                <div className="text-[10px] text-dark-muted">
                  Capabilities {node.capabilities?.length ?? 0}
                  {node.mesh_registered ? ' · mesh' : ''}
                </div>
                {endpoint && (
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] text-dark-muted truncate" title={endpoint}>{endpoint}</span>
                    <button
                      onClick={() => openControlLink(endpoint)}
                      className="px-3 py-1.5 text-xs font-semibold text-dark-text bg-dark-border rounded-md hover:bg-dark-hover transition"
                    >
                      Open
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <p className="text-sm font-semibold text-dark-text">Capability Catalog</p>
            <p className="text-xs text-dark-muted">Provider mapping from the hub registry.</p>
          </div>
          <span className="text-xs text-dark-muted">{registryCapabilityEntries.length} capabilities</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {registryCapabilityEntries.map((entry) => (
            <div key={entry.name} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-2">
              <p className="text-sm font-semibold text-dark-text">{entry.name}</p>
              <p className="text-[10px] text-dark-muted">
                Providers: {entry.providers.length ? entry.providers.join(', ') : '—'}
              </p>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <p className="text-sm font-semibold text-dark-text">Local UI Imaging</p>
            <p className="text-xs text-dark-muted">Latest local agent screenshots from `artifacts/ui_audits/`.</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-[10px] text-dark-muted">
              <input
                type="checkbox"
                checked={uiImageAutoRefresh}
                onChange={(event) => setUiImageAutoRefresh(event.target.checked)}
                className="accent-merlin-blue"
              />
              Auto refresh
            </label>
            <select
              value={uiImageIntervalSec}
              onChange={(event) => setUiImageIntervalSec(Number(event.target.value))}
              className="text-[10px] bg-slate-900 border border-slate-700 rounded px-2 py-1 text-dark-muted"
            >
              <option value={30}>30s</option>
              <option value={60}>60s</option>
              <option value={120}>2m</option>
              <option value={300}>5m</option>
            </select>
            <button
              onClick={fetchUiImages}
              className="text-xs text-dark-muted hover:text-dark-text"
            >
              Refresh
            </button>
            <button
              onClick={captureUiAudit}
              disabled={uiImageCaptureBusy}
              className="px-3 py-1.5 text-xs font-semibold text-emerald-200 bg-emerald-500/10 border border-emerald-500/30 rounded-lg hover:bg-emerald-500/20 disabled:opacity-60"
            >
              {uiImageCaptureBusy ? 'Capturing…' : 'Capture Now'}
            </button>
          </div>
        </div>

        {uiImageCaptureError && (
          <div className="mb-4 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
            Capture failed: {uiImageCaptureError}
          </div>
        )}
        {uiImageCaptureResult && (
          <div className="mb-4 text-[10px] text-dark-muted">
            Last capture: {String(uiImageCaptureResult.run_id || '')}
          </div>
        )}
        {uiImageError && (
          <div className="mb-4 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
            UI imaging error: {uiImageError}
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
          {uiImages.map((image) => (
            <button
              key={image.path}
              onClick={() => openControlLink(resolveUiImageUrl(image.path))}
              className="group text-left rounded-xl border border-slate-800 bg-slate-900/60 overflow-hidden"
            >
              <img
                src={resolveUiImageUrl(image.path)}
                alt={image.name}
                loading="lazy"
                className="w-full h-28 object-cover group-hover:opacity-90"
              />
              <div className="p-2">
                <p className="text-[10px] text-dark-text truncate">{image.name}</p>
                {image.updated_at && (
                  <p className="text-[10px] text-dark-muted">
                    {new Date(image.updated_at).toLocaleString()}
                  </p>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <p className="text-sm font-semibold text-dark-text">Capability Invoke</p>
            <p className="text-xs text-dark-muted">Run a capability through the hub router.</p>
          </div>
          <button
            onClick={() => {
              setCapabilityResult(null);
              setCapabilityError(null);
            }}
            className="text-xs text-dark-muted hover:text-dark-text"
          >
            Clear
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 space-y-4">
            <div>
              <label className="block text-[10px] uppercase tracking-wider text-dark-muted">Capability</label>
              <input
                list="merlin-capability-options"
                value={capabilityName}
                onChange={(event) => setCapabilityName(event.target.value)}
                placeholder="assistant.chat"
                className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-xs text-dark-text focus:outline-none focus:ring-1 focus:ring-merlin-blue/40"
              />
              <datalist id="merlin-capability-options">
                {registryCapabilityEntries.map((entry) => (
                  <option key={entry.name} value={entry.name} />
                ))}
              </datalist>
            </div>

            <div>
              <label className="block text-[10px] uppercase tracking-wider text-dark-muted">Provider (optional)</label>
              <input
                list="merlin-capability-provider-options"
                value={capabilityProvider}
                onChange={(event) => setCapabilityProvider(event.target.value)}
                placeholder="runtime_echo"
                className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-xs text-dark-text focus:outline-none focus:ring-1 focus:ring-merlin-blue/40"
              />
              <datalist id="merlin-capability-provider-options">
                {registryNodes.map((node) => (
                  <option key={node.id} value={node.id}>{node.name || node.id}</option>
                ))}
              </datalist>
            </div>

            <div>
              <label className="block text-[10px] uppercase tracking-wider text-dark-muted">Args (JSON)</label>
              <textarea
                value={capabilityArgs}
                onChange={(event) => setCapabilityArgs(event.target.value)}
                rows={4}
                className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-[11px] text-dark-text focus:outline-none focus:ring-1 focus:ring-merlin-blue/40"
              />
            </div>

            {capabilityError && (
              <p className="text-xs text-rose-300">{capabilityError}</p>
            )}
            <button
              onClick={invokeCapability}
              disabled={capabilityBusy}
              className="px-3 py-2 text-xs font-semibold text-emerald-200 bg-emerald-500/10 border border-emerald-500/30 rounded-lg hover:bg-emerald-500/20 disabled:opacity-60"
            >
              {capabilityBusy ? 'Invoking…' : 'Invoke Capability'}
            </button>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <div className="flex items-center justify-between">
              <p className="text-[10px] uppercase tracking-wider text-dark-muted">Result</p>
              {capabilityResult && (
                <button
                  onClick={() => navigator.clipboard.writeText(capabilityResult)}
                  className="text-[10px] text-dark-muted hover:text-dark-text"
                >
                  Copy
                </button>
              )}
            </div>
            <pre className="mt-3 text-[11px] text-dark-text whitespace-pre-wrap">
              {capabilityResult || 'No capability invoked yet.'}
            </pre>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default ControlCenter;
