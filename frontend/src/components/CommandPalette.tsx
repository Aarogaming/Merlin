import { useEffect, useMemo, useState } from 'react';
import { Command, Play, Search, X } from 'lucide-react';
import type { OperationName } from '../services/operationContracts.generated';
import { merlinApi } from '../services/api';
import { useOnboardingStore } from '../store/onboarding';
import './CommandPalette.css';

interface ExecutionResult {
  operation: string;
  status: number;
  duration_ms: number;
  payload: unknown;
}

const DEFAULT_PAYLOAD_TEXT = '{}';

const emptyResult = (): ExecutionResult | null => null;

const parsePayloadText = (payloadText: string): unknown => {
  if (!payloadText.trim()) {
    return {};
  }
  const parsed = JSON.parse(payloadText);
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Payload must be a JSON object');
  }
  return parsed;
};

const buildOperationEnvelope = (operation: OperationName, payload: unknown) => ({
  schema_version: '1.0.0',
  operation: {
    name: operation,
    version: '1.0.0',
  },
  correlation_id: `palette-${Date.now()}`,
  payload,
});

const normalizeJson = (value: unknown): string => JSON.stringify(value, null, 2);

const CommandPalette = () => {
  const apiKey = useOnboardingStore((state) => state.apiKey);
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [payloadText, setPayloadText] = useState(DEFAULT_PAYLOAD_TEXT);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<ExecutionResult | null>(emptyResult);
  const [executionError, setExecutionError] = useState<string | null>(null);

  const operationNames = useMemo(
    () => [...merlinApi.getOperationContractNames()],
    []
  );

  const filteredOperationNames = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    if (!normalizedQuery) {
      return operationNames;
    }
    return operationNames.filter((operationName) =>
      operationName.toLowerCase().includes(normalizedQuery)
    );
  }, [operationNames, searchQuery]);

  const selectedOperation = filteredOperationNames[selectedIndex] ?? null;
  const selectedOperationFixture = selectedOperation
    ? merlinApi.getOperationContractFixture(selectedOperation)
    : null;

  const closePalette = () => {
    setIsOpen(false);
    setExecutionError(null);
  };

  const executeOperation = async (operation: OperationName) => {
    setIsExecuting(true);
    setExecutionError(null);
    setExecutionResult(null);

    const startedAt = performance.now();
    try {
      const payload = parsePayloadText(payloadText);
      const response = await fetch(`${merlinApi.getBaseUrl()}/merlin/operations`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
        },
        body: JSON.stringify(buildOperationEnvelope(operation, payload)),
      });
      const responseText = await response.text();
      const responsePayload = (() => {
        if (!responseText.trim()) {
          return {};
        }
        try {
          return JSON.parse(responseText);
        } catch {
          return responseText;
        }
      })();

      setExecutionResult({
        operation,
        status: response.status,
        duration_ms: Number((performance.now() - startedAt).toFixed(2)),
        payload: responsePayload,
      });
    } catch (error) {
      setExecutionError(error instanceof Error ? error.message : 'Operation execution failed');
    } finally {
      setIsExecuting(false);
    }
  };

  useEffect(() => {
    if (!isOpen) {
      return;
    }
    setSelectedIndex(0);
  }, [searchQuery, isOpen]);

  useEffect(() => {
    const onWindowKeyDown = (event: KeyboardEvent) => {
      const isOpenShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k';
      if (isOpenShortcut) {
        event.preventDefault();
        setIsOpen((currentlyOpen) => !currentlyOpen);
        return;
      }

      if (!isOpen) {
        return;
      }

      if (event.key === 'Escape') {
        event.preventDefault();
        closePalette();
        return;
      }

      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setSelectedIndex((currentIndex) =>
          Math.min(currentIndex + 1, Math.max(filteredOperationNames.length - 1, 0))
        );
        return;
      }

      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setSelectedIndex((currentIndex) => Math.max(currentIndex - 1, 0));
      }
    };

    window.addEventListener('keydown', onWindowKeyDown);
    return () => window.removeEventListener('keydown', onWindowKeyDown);
  }, [filteredOperationNames.length, isOpen]);

  if (!isOpen) {
    return (
      <button
        type="button"
        className="command-palette-trigger"
        onClick={() => setIsOpen(true)}
        aria-label="Open command palette"
      >
        <Command size={14} />
        <span>Command Palette</span>
        <kbd>Ctrl/⌘K</kbd>
      </button>
    );
  }

  return (
    <>
      <div className="command-palette-overlay" onClick={closePalette} aria-hidden="true" />
      <div
        className="command-palette"
        role="dialog"
        aria-modal="true"
        aria-labelledby="command-palette-title"
      >
        <div className="command-palette-header">
          <h2 id="command-palette-title">Operations Command Palette</h2>
          <button type="button" className="command-palette-close" onClick={closePalette} aria-label="Close command palette">
            <X size={16} />
          </button>
        </div>

        <label htmlFor="command-palette-search" className="command-palette-label">
          Search operations
        </label>
        <div className="command-palette-search-wrapper">
          <Search size={14} />
          <input
            id="command-palette-search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="merlin.research.manager..."
            autoFocus
          />
        </div>

        <div className="command-palette-content">
          <div className="command-palette-operations" role="listbox" aria-label="Operation list">
            {filteredOperationNames.length === 0 ? (
              <div className="command-palette-empty">No operations match the current query.</div>
            ) : (
              filteredOperationNames.map((operationName, index) => (
                <button
                  key={operationName}
                  type="button"
                  role="option"
                  aria-selected={selectedOperation === operationName}
                  className={`command-palette-operation ${selectedOperation === operationName ? 'is-selected' : ''}`}
                  onClick={() => setSelectedIndex(index)}
                >
                  {operationName}
                </button>
              ))
            )}
          </div>

          <div className="command-palette-panel">
            <div className="command-palette-meta">
              <p className="command-palette-meta-label">Selected Operation</p>
              <p className="command-palette-meta-value">{selectedOperation ?? 'None'}</p>
              {selectedOperationFixture?.requestFixture && (
                <p className="command-palette-meta-caption">
                  Fixture: {selectedOperationFixture.requestFixture}
                </p>
              )}
            </div>

            <label htmlFor="command-palette-payload" className="command-palette-label">
              Payload JSON
            </label>
            <textarea
              id="command-palette-payload"
              value={payloadText}
              onChange={(event) => setPayloadText(event.target.value)}
              className="command-palette-payload"
              aria-label="Operation payload JSON"
            />

            <button
              type="button"
              className="command-palette-execute"
              onClick={() => selectedOperation && executeOperation(selectedOperation)}
              disabled={!selectedOperation || isExecuting}
              aria-label="Execute selected operation"
            >
              <Play size={14} />
              {isExecuting ? 'Running...' : 'Execute'}
            </button>

            {executionError && (
              <p className="command-palette-error">{executionError}</p>
            )}

            {executionResult && (
              <div className="command-palette-result" aria-live="polite">
                <div className="command-palette-result-meta">
                  <span>Status: {executionResult.status}</span>
                  <span>Latency: {executionResult.duration_ms} ms</span>
                </div>
                <pre>{normalizeJson(executionResult.payload)}</pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
};

export default CommandPalette;
