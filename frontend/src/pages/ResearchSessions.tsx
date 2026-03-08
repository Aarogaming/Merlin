import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { AlertCircle, FileSearch, RefreshCw, Search, Tags } from 'lucide-react';
import {
  onboardingService,
  type ResearchSessionSummary,
} from '../services/onboarding';
import { useOnboardingStore } from '../store/onboarding';

const MAX_PAGE_SIZE = 20;

const safeString = (value: unknown, fallback = ''): string =>
  typeof value === 'string' ? value : fallback;

const safeStringArray = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

const formatTimestamp = (value: unknown): string => {
  if (typeof value !== 'string' || !value.trim()) {
    return 'Unknown';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString();
};

const sessionSignalCount = (session: ResearchSessionSummary): number => {
  const directCount = session.signal_count;
  if (typeof directCount === 'number' && Number.isFinite(directCount)) {
    return Math.max(0, Math.round(directCount));
  }
  const nestedCount = session.signals;
  if (Array.isArray(nestedCount)) {
    return nestedCount.length;
  }
  return 0;
};

const sessionStatus = (session: ResearchSessionSummary): string => {
  const rawStatus = safeString(session.status, '');
  if (rawStatus) {
    return rawStatus;
  }
  return session.archived ? 'archived' : 'active';
};

const sessionObjective = (session: ResearchSessionSummary): string =>
  safeString(session.objective, '(No objective provided)');

const ResearchSessions = () => {
  const apiKey = useOnboardingStore((state) => state.apiKey);
  const [sessions, setSessions] = useState<ResearchSessionSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<Record<string, unknown> | null>(null);
  const [selectedBrief, setSelectedBrief] = useState<Record<string, unknown> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const fetchSessions = useCallback(
    async (options?: { append?: boolean; cursor?: string | null; query?: string; tag?: string }) => {
      const shouldAppend = options?.append === true;
      const cursor = options?.cursor ?? null;
      const query = (options?.query ?? searchQuery).trim();
      const tag = (options?.tag ?? tagFilter).trim();

      if (shouldAppend) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }
      setError(null);

      try {
        const result = query
          ? await onboardingService.searchResearchSessions({
              query,
              tag: tag || undefined,
              cursor: cursor || undefined,
              limit: MAX_PAGE_SIZE,
              apiKey: apiKey || undefined,
            })
          : await onboardingService.listResearchSessions({
              topic: '',
              tag: tag || undefined,
              cursor: cursor || undefined,
              limit: MAX_PAGE_SIZE,
              apiKey: apiKey || undefined,
            });

        setNextCursor(result.next_cursor);
        setSessions((previousSessions) => {
          if (!shouldAppend) {
            return result.sessions;
          }
          const merged = [...previousSessions, ...result.sessions];
          const dedupedMap = new Map<string, ResearchSessionSummary>();
          for (const session of merged) {
            const sessionId = safeString(session.session_id, '');
            if (sessionId) {
              dedupedMap.set(sessionId, session);
            }
          }
          return [...dedupedMap.values()];
        });
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : 'Failed to load sessions');
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [apiKey, searchQuery, tagFilter]
  );

  const loadSessionDetail = useCallback(
    async (sessionId: string) => {
      const normalizedSessionId = sessionId.trim();
      if (!normalizedSessionId) {
        return;
      }
      setSelectedSessionId(normalizedSessionId);
      setDetailLoading(true);
      setDetailError(null);
      try {
        const [sessionResult, briefResult] = await Promise.all([
          onboardingService.getResearchSession(normalizedSessionId, apiKey || undefined),
          onboardingService.getResearchSessionBrief(normalizedSessionId, apiKey || undefined),
        ]);
        setSelectedSession(sessionResult.session);
        setSelectedBrief(briefResult.brief);
      } catch (fetchError) {
        setDetailError(fetchError instanceof Error ? fetchError.message : 'Failed to load session');
        setSelectedSession(null);
        setSelectedBrief(null);
      } finally {
        setDetailLoading(false);
      }
    },
    [apiKey]
  );

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  useEffect(() => {
    if (!sessions.length) {
      setSelectedSessionId(null);
      setSelectedSession(null);
      setSelectedBrief(null);
      return;
    }
    const selectedIdExists = sessions.some((session) => safeString(session.session_id) === selectedSessionId);
    if (selectedSessionId && selectedIdExists) {
      return;
    }
    const nextSelectedSessionId = safeString(sessions[0].session_id, '');
    if (nextSelectedSessionId) {
      loadSessionDetail(nextSelectedSessionId);
    }
  }, [sessions, selectedSessionId, loadSessionDetail]);

  const selectedObjective = useMemo(
    () => safeString(selectedSession?.objective, sessionObjective({ session_id: '', ...selectedSession })),
    [selectedSession]
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="space-y-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold text-gradient">Research Session Explorer</h1>
          <p className="text-dark-muted">
            Browse, filter, and inspect persisted research-manager sessions.
          </p>
        </div>
        <button
          type="button"
          onClick={() => fetchSessions({ query: searchQuery, tag: tagFilter })}
          className="btn-secondary inline-flex items-center gap-2"
          aria-label="Refresh research sessions list"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      <div className="card space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="md:col-span-2">
            <label htmlFor="research-search" className="block text-sm text-dark-muted mb-1">
              Search
            </label>
            <div className="relative">
              <Search
                className="absolute left-3 top-1/2 -translate-y-1/2 text-dark-muted"
                size={16}
                aria-hidden="true"
              />
              <input
                id="research-search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    fetchSessions({ query: searchQuery, tag: tagFilter });
                  }
                }}
                className="w-full rounded-md border border-dark-border bg-dark-card pl-9 pr-3 py-2 text-sm"
                placeholder="objective keyword"
                aria-label="Search research sessions by keyword"
              />
            </div>
          </div>
          <div>
            <label htmlFor="research-tag" className="block text-sm text-dark-muted mb-1">
              Tag Filter
            </label>
            <input
              id="research-tag"
              value={tagFilter}
              onChange={(event) => setTagFilter(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  fetchSessions({ query: searchQuery, tag: tagFilter });
                }
              }}
              className="w-full rounded-md border border-dark-border bg-dark-card px-3 py-2 text-sm"
              placeholder="tag"
              aria-label="Filter research sessions by tag"
            />
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/50 bg-red-500/10 p-4 text-red-300 flex items-start gap-2">
          <AlertCircle size={18} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[2fr_3fr] gap-6 min-w-0">
        <div className="card min-w-0">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-merlin-blue">Sessions</h2>
            <span className="text-xs text-dark-muted">{sessions.length} loaded</span>
          </div>

          {loading ? (
            <div className="py-8 text-center text-dark-muted">Loading sessions...</div>
          ) : sessions.length === 0 ? (
            <div className="py-8 text-center text-dark-muted">No sessions found for the current filters.</div>
          ) : (
            <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
              {sessions.map((session) => {
                const sessionId = safeString(session.session_id, '');
                const tags = safeStringArray(session.tags);
                const isSelected = sessionId === selectedSessionId;
                return (
                  <button
                    key={sessionId || Math.random()}
                    type="button"
                    className={`w-full text-left rounded-md border p-3 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-merlin-blue ${
                      isSelected
                        ? 'border-merlin-blue bg-merlin-blue/10'
                        : 'border-dark-border bg-dark-card hover:bg-dark-hover'
                    }`}
                    onClick={() => loadSessionDetail(sessionId)}
                    aria-label={`Open research session ${sessionId}`}
                  >
                    <div className="text-xs text-dark-muted truncate">{sessionId || '(missing session_id)'}</div>
                    <div className="font-medium text-dark-text mt-1 break-words">{sessionObjective(session)}</div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-dark-muted">
                      <span>Status: {sessionStatus(session)}</span>
                      <span>Signals: {sessionSignalCount(session)}</span>
                      <span>Updated: {formatTimestamp(session.updated_at || session.created_at)}</span>
                    </div>
                    {tags.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {tags.map((tag) => (
                          <span key={`${sessionId}-${tag}`} className="rounded-full bg-dark-hover px-2 py-0.5 text-xs">
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {nextCursor && (
            <div className="mt-4">
              <button
                type="button"
                onClick={() => fetchSessions({ append: true, cursor: nextCursor, query: searchQuery, tag: tagFilter })}
                className="btn-secondary w-full"
                disabled={loadingMore}
                aria-label="Load more research sessions"
              >
                {loadingMore ? 'Loading...' : 'Load More'}
              </button>
            </div>
          )}
        </div>

        <div className="card min-w-0">
          <h2 className="text-lg font-semibold text-merlin-green mb-3">Session Detail</h2>
          {detailLoading ? (
            <div className="py-8 text-center text-dark-muted">Loading session detail...</div>
          ) : detailError ? (
            <div className="rounded-lg border border-red-500/50 bg-red-500/10 p-3 text-red-300">
              {detailError}
            </div>
          ) : selectedSession ? (
            <div className="space-y-4">
              <div>
                <div className="text-xs text-dark-muted">Session</div>
                <div className="text-sm font-semibold break-all">{safeString(selectedSession.session_id, selectedSessionId || 'Unknown')}</div>
                <div className="mt-1 text-dark-text break-words">{selectedObjective}</div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="rounded-md border border-dark-border bg-dark-card p-3">
                  <div className="text-xs text-dark-muted mb-1 flex items-center gap-2">
                    <Tags size={14} aria-hidden="true" />
                    Tags
                  </div>
                  <div className="text-sm text-dark-text break-words">
                    {safeStringArray(selectedSession.tags).join(', ') || 'None'}
                  </div>
                </div>
                <div className="rounded-md border border-dark-border bg-dark-card p-3">
                  <div className="text-xs text-dark-muted mb-1 flex items-center gap-2">
                    <FileSearch size={14} aria-hidden="true" />
                    Brief Signals
                  </div>
                  <div className="text-sm text-dark-text">
                    {typeof selectedBrief?.signal_count === 'number'
                      ? Math.max(0, Math.round(selectedBrief.signal_count))
                      : 'N/A'}
                  </div>
                </div>
              </div>

              <div>
                <div className="text-xs text-dark-muted mb-1">Brief Preview</div>
                <pre className="rounded-md border border-dark-border bg-dark-card p-3 text-xs overflow-auto max-h-56 break-words whitespace-pre-wrap">
                  {selectedBrief ? JSON.stringify(selectedBrief, null, 2) : 'No brief payload available'}
                </pre>
              </div>
            </div>
          ) : (
            <div className="py-8 text-center text-dark-muted">
              Select a research session to view details.
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default ResearchSessions;
