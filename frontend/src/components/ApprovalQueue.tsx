import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle, XCircle, ShieldCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import { ApprovalRequest } from '../types';
import { merlinApi } from '../services/api';

type ApprovalQueueProps = {
  apiUrl?: string;
  refreshInterval?: number;
  decidedBy?: string;
};

export default function ApprovalQueue({
  apiUrl,
  refreshInterval = 8000,
  decidedBy = 'Desktop',
}: ApprovalQueueProps) {
  const baseUrl = useMemo(() => apiUrl || 'http://localhost:8000', [apiUrl]);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const fetchApprovals = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`${baseUrl}/approvals?status=pending`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setApprovals(data.approvals || []);
    } catch (error) {
      console.error('Failed to fetch approvals:', error);
      toast.error('Failed to fetch approvals');
    } finally {
      setLoading(false);
    }
  }, [baseUrl]);

  useEffect(() => {
    merlinApi.setBaseUrl(baseUrl);
    fetchApprovals();
    const interval = setInterval(fetchApprovals, refreshInterval);

    const ws = merlinApi.createEventsWebSocketConnection();
    if (ws) {
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (typeof data?.event_type === 'string' && data.event_type.startsWith('approval.')) {
            fetchApprovals();
          }
        } catch (error) {
          console.error('Failed to parse approval WS message:', error);
        }
      };
    }

    return () => {
      clearInterval(interval);
      if (ws) {
        ws.close();
      }
    };
  }, [fetchApprovals, refreshInterval, baseUrl]);

  const handleApprove = async (approvalId: string) => {
    try {
      const note = notes[approvalId] || '';
      const response = await fetch(
        `${baseUrl}/approvals/${approvalId}/approve`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decided_by: decidedBy, note }),
        }
      );
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      toast.success('Approval granted');
      setNotes((prev) => ({ ...prev, [approvalId]: '' }));
      fetchApprovals();
    } catch (error) {
      console.error('Failed to approve:', error);
      toast.error('Failed to approve');
    }
  };

  const handleReject = async (approvalId: string) => {
    try {
      const note = notes[approvalId] || '';
      const response = await fetch(
        `${baseUrl}/approvals/${approvalId}/reject`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ decided_by: decidedBy, note }),
        }
      );
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      toast.success('Approval rejected');
      setNotes((prev) => ({ ...prev, [approvalId]: '' }));
      fetchApprovals();
    } catch (error) {
      console.error('Failed to reject:', error);
      toast.error('Failed to reject');
    }
  };

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-merlin-blue" />
          <h3 className="text-lg font-semibold">Pending Approvals</h3>
        </div>
        <span className="text-sm text-dark-muted">
          {loading ? 'Refreshing...' : `${approvals.length} pending`}
        </span>
      </div>

      {approvals.length === 0 ? (
        <div className="text-sm text-dark-muted">No pending approvals.</div>
      ) : (
        <div className="space-y-4">
          {approvals.map((approval) => (
            <div
              key={approval.approval_id}
              className="rounded-lg border border-slate-700/50 bg-slate-900/40 p-4"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-sm text-dark-muted">Task</div>
                  <div className="text-base font-semibold text-white">
                    {approval.task_id}
                  </div>
                  <div className="text-sm text-dark-muted mt-1">
                    Gate: <span className="text-white">{approval.gate}</span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-dark-muted">Requested</div>
                  <div className="text-sm text-white">
                    {new Date(approval.created_at).toLocaleTimeString()}
                  </div>
                </div>
              </div>

              <div className="mt-3 text-xs text-dark-muted">
                Requested by {approval.requested_by}
              </div>

              <div className="mt-4 flex flex-col gap-3">
                <input
                  type="text"
                  value={notes[approval.approval_id] || ''}
                  onChange={(e) =>
                    setNotes((prev) => ({
                      ...prev,
                      [approval.approval_id]: e.target.value,
                    }))
                  }
                  placeholder="Optional note..."
                  className="w-full rounded-md bg-slate-800/60 px-3 py-2 text-sm text-white placeholder:text-slate-500"
                />
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => handleApprove(approval.approval_id)}
                    className="inline-flex items-center gap-2 rounded-md bg-emerald-600/80 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-600"
                  >
                    <CheckCircle className="w-4 h-4" />
                    Approve
                  </button>
                  <button
                    onClick={() => handleReject(approval.approval_id)}
                    className="inline-flex items-center gap-2 rounded-md bg-rose-600/70 px-3 py-2 text-sm font-semibold text-white hover:bg-rose-600"
                  >
                    <XCircle className="w-4 h-4" />
                    Reject
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
