import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { CheckCircle, ChevronLeft, ShieldCheck, XCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { merlinApi } from '../services/api';
import { useOnboardingStore } from '../store/onboarding';
import { ApprovalRequest, TaskItem } from '../types';

const TaskDetails = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const apiUrl = useOnboardingStore((state) => state.apiUrl);
  const baseUrl = useMemo(() => apiUrl || 'http://localhost:8000', [apiUrl]);
  const [task, setTask] = useState<TaskItem | null>(null);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);

  const fetchTask = useCallback(async () => {
    if (!taskId) {
      return;
    }
    try {
      setLoading(true);
      merlinApi.setBaseUrl(baseUrl);
      const data = await merlinApi.getTaskHttp(taskId);
      setTask(data);
      const approvalList = await merlinApi.getApprovalsHttp('', taskId);
      setApprovals(approvalList);
    } catch (error) {
      console.error('Failed to fetch task:', error);
      toast.error('Failed to fetch task');
    } finally {
      setLoading(false);
    }
  }, [taskId, baseUrl]);

  useEffect(() => {
    fetchTask();
    const ws = merlinApi.createEventsWebSocketConnection();
    if (ws) {
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (typeof data?.event_type === 'string' && data.event_type.startsWith('approval.')) {
            fetchTask();
          }
        } catch (error) {
          console.error('Failed to parse task WS message:', error);
        }
      };
    }
    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [fetchTask]);

  const handleRequestExecuteGate = async () => {
    if (!taskId) {
      return;
    }
    try {
      await merlinApi.requestApprovalHttp(taskId, 'execute', 'Desktop', ['desktop', 'androidapp'], {
        title: task?.title,
      });
      toast.success('Execute gate requested');
      fetchTask();
    } catch (error) {
      console.error('Failed to request execute gate:', error);
      toast.error('Failed to request execute gate');
    }
  };

  const handleApprove = async (approvalId: string) => {
    try {
      await merlinApi.approveApprovalHttp(approvalId, 'Desktop', notes[approvalId]);
      toast.success('Approval granted');
      setNotes((prev) => ({ ...prev, [approvalId]: '' }));
      fetchTask();
    } catch (error) {
      console.error('Failed to approve:', error);
      toast.error('Failed to approve');
    }
  };

  const handleReject = async (approvalId: string) => {
    try {
      await merlinApi.rejectApprovalHttp(approvalId, 'Desktop', notes[approvalId]);
      toast.success('Approval rejected');
      setNotes((prev) => ({ ...prev, [approvalId]: '' }));
      fetchTask();
    } catch (error) {
      console.error('Failed to reject:', error);
      toast.error('Failed to reject');
    }
  };

  const handleStartExecution = async () => {
    if (!taskId) {
      return;
    }
    try {
      const result = await merlinApi.startTaskHttp(taskId, 'Desktop');
      if (!result.ok) {
        toast.error(result.error || 'Execution blocked');
        return;
      }
      toast.success('Execution started');
      fetchTask();
    } catch (error) {
      console.error('Failed to start execution:', error);
      toast.error('Failed to start execution');
    }
  };

  if (!taskId) {
    return (
      <div className="card text-sm text-dark-muted">Task not found.</div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-6"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/approvals" className="btn btn-secondary">
            <ChevronLeft className="w-4 h-4 mr-2" />
            Approvals
          </Link>
          <div>
            <h1 className="text-3xl font-bold text-gradient">Task {taskId}</h1>
            <p className="text-dark-muted">Execute gate controls and task details</p>
          </div>
        </div>
        <button onClick={fetchTask} className="btn btn-secondary">
          Refresh
        </button>
      </div>

      <div className="card">
        {loading ? (
          <div className="text-sm text-dark-muted">Loading...</div>
        ) : task ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-dark-muted">Title</div>
              <div className="text-lg font-semibold text-white">{task.title}</div>
            </div>
            <div>
              <div className="text-xs text-dark-muted">Status</div>
              <div className="text-sm text-white">{task.status}</div>
            </div>
            <div>
              <div className="text-xs text-dark-muted">Priority</div>
              <div className="text-sm text-white">{task.priority}</div>
            </div>
            <div>
              <div className="text-xs text-dark-muted">Assignee</div>
              <div className="text-sm text-white">{task.assignee}</div>
            </div>
            <div>
              <div className="text-xs text-dark-muted">Execution Mode</div>
              <div className="text-sm text-white">{task.execution_mode || 'auto'}</div>
            </div>
            <div>
              <div className="text-xs text-dark-muted">Approvals</div>
              <div className="text-sm text-white">{task.approvals || 'none'}</div>
            </div>
            <div>
              <div className="text-xs text-dark-muted">Preferred Role</div>
              <div className="text-sm text-white">{task.preferred_role || '-'}</div>
            </div>
            <div>
              <div className="text-xs text-dark-muted">Domain</div>
              <div className="text-sm text-white">{task.domain || '-'}</div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-dark-muted">Task not found.</div>
        )}
      </div>

      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-merlin-blue" />
            <h2 className="text-lg font-semibold">Execute Gate</h2>
          </div>
          <button onClick={handleRequestExecuteGate} className="btn btn-secondary">
            Request Execute Gate
          </button>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={handleStartExecution} className="btn btn-primary">
            Start Execution
          </button>
          <span className="text-sm text-dark-muted">
            Requires execute approval if gate is pending.
          </span>
        </div>
      </div>

      <div className="card">
        <h3 className="text-lg font-semibold mb-4">Approvals</h3>
        {approvals.length === 0 ? (
          <div className="text-sm text-dark-muted">No approvals for this task.</div>
        ) : (
          <div className="space-y-4">
            {approvals.map((approval) => (
              <div key={approval.approval_id} className="rounded-lg border border-dark-border p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm text-dark-muted">Gate</div>
                    <div className="text-white font-semibold">{approval.gate}</div>
                  </div>
                  <div className="text-sm text-dark-muted">{approval.status}</div>
                </div>
                {approval.status === 'pending' && (
                  <div className="mt-3 flex flex-col md:flex-row md:items-center gap-3">
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
                      <button onClick={() => handleApprove(approval.approval_id)} className="btn btn-primary">
                        <CheckCircle className="w-4 h-4 mr-2" />
                        Approve
                      </button>
                      <button onClick={() => handleReject(approval.approval_id)} className="btn btn-secondary">
                        <XCircle className="w-4 h-4 mr-2" />
                        Reject
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default TaskDetails;
