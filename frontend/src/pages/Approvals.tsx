import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { CheckCircle, Filter, Search, ShieldCheck, XCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { useOnboardingStore } from '../store/onboarding';
import { merlinApi } from '../services/api';
import { ApprovalRequest } from '../types';

const statusOptions = ['all', 'pending', 'approved', 'rejected'] as const;

const Approvals = () => {
  const apiUrl = useOnboardingStore((state) => state.apiUrl);
  const baseUrl = useMemo(() => apiUrl || 'http://localhost:8000', [apiUrl]);
  const [statusFilter, setStatusFilter] = useState<typeof statusOptions[number]>('pending');
  const [search, setSearch] = useState('');
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const fetchApprovals = useCallback(async () => {
    try {
      setLoading(true);
      merlinApi.setBaseUrl(baseUrl);
      const data = await merlinApi.getApprovalsHttp(
        statusFilter === 'all' ? '' : statusFilter
      );
      setApprovals(data);
    } catch (error) {
      console.error('Failed to fetch approvals:', error);
      toast.error('Failed to fetch approvals');
    } finally {
      setLoading(false);
    }
  }, [baseUrl, statusFilter]);

  useEffect(() => {
    fetchApprovals();
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
      if (ws) {
        ws.close();
      }
    };
  }, [fetchApprovals]);

  const filtered = approvals.filter((approval) => {
    const haystack = `${approval.approval_id} ${approval.task_id} ${approval.gate}`.toLowerCase();
    return haystack.includes(search.toLowerCase());
  });

  const handleApprove = async (approvalId: string) => {
    try {
      const note = notes[approvalId] || '';
      await merlinApi.approveApprovalHttp(approvalId, 'Desktop', note);
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
      await merlinApi.rejectApprovalHttp(approvalId, 'Desktop', note);
      toast.success('Approval rejected');
      setNotes((prev) => ({ ...prev, [approvalId]: '' }));
      fetchApprovals();
    } catch (error) {
      console.error('Failed to reject:', error);
      toast.error('Failed to reject');
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-6"
    >
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gradient mb-2">Approvals</h1>
          <p className="text-dark-muted">Review and approve pending gates</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-dark-muted">
          <ShieldCheck className="w-4 h-4" />
          {loading ? 'Refreshing...' : `${filtered.length} approvals`}
        </div>
      </div>

      <div className="card">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-dark-muted" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as typeof statusOptions[number])}
              className="rounded-md bg-dark-border border border-dark-border px-3 py-2 text-sm text-dark-text"
            >
              {statusOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <Search className="w-4 h-4 text-dark-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by task or approval ID"
              className="rounded-md bg-dark-border border border-dark-border px-3 py-2 text-sm text-dark-text"
            />
          </div>
        </div>
      </div>

      <div className="space-y-4">
        {filtered.length === 0 ? (
          <div className="card text-sm text-dark-muted">No approvals found.</div>
        ) : (
          filtered.map((approval) => (
            <div key={approval.approval_id} className="card">
              <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                <div>
                  <div className="text-xs text-dark-muted">Task</div>
                  <Link
                    to={`/tasks/${approval.task_id}`}
                    className="text-lg font-semibold text-merlin-blue hover:underline"
                  >
                    {approval.task_id}
                  </Link>
                  <div className="text-sm text-dark-muted mt-1">
                    Gate: <span className="text-dark-text">{approval.gate}</span>
                  </div>
                  <div className="text-xs text-dark-muted mt-2">
                    Requested by {approval.requested_by}
                  </div>
                </div>
                <div className="text-right text-sm text-dark-muted">
                  <div>Status: {approval.status}</div>
                  <div>Requested: {new Date(approval.created_at).toLocaleString()}</div>
                </div>
              </div>

              {approval.status === 'pending' && (
                <div className="mt-4 flex flex-col md:flex-row md:items-center gap-3">
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
                    className="flex-1 rounded-md bg-dark-border border border-dark-border px-3 py-2 text-sm text-dark-text"
                  />
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleApprove(approval.approval_id)}
                      className="btn btn-primary"
                    >
                      <CheckCircle className="w-4 h-4 mr-2" />
                      Approve
                    </button>
                    <button
                      onClick={() => handleReject(approval.approval_id)}
                      className="btn btn-secondary"
                    >
                      <XCircle className="w-4 h-4 mr-2" />
                      Reject
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </motion.div>
  );
};

export default Approvals;
