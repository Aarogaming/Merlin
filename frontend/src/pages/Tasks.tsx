import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Filter, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import toast from 'react-hot-toast';
import { useOnboardingStore } from '../store/onboarding';
import { merlinApi } from '../services/api';
import { TaskItem } from '../types';

const statusOptions = ['all', 'queued', 'in_progress', 'blocked', 'done', 'failed', 'cancelled'] as const;

const formatStatus = (status: string) => status.replace(/_/g, ' ');

const parseApprovals = (value?: string) => {
  if (!value || value === '-') {
    return [] as { gate: string; status: string }[];
  }
  return value
    .split(',')
    .map((entry) => {
      const [gate, status] = entry.split(':');
      return {
        gate: (gate || '').trim(),
        status: (status || '').trim(),
      };
    })
    .filter((entry) => entry.gate.length > 0);
};

const getPendingGates = (value: string | undefined) => {
  return parseApprovals(value).filter(
    (entry) => entry.status.toLowerCase() === 'pending'
  );
};

const Tasks = () => {
  const apiUrl = useOnboardingStore((state) => state.apiUrl);
  const baseUrl = useMemo(() => apiUrl || 'http://localhost:8000', [apiUrl]);
  const [statusFilter, setStatusFilter] = useState<typeof statusOptions[number]>('all');
  const [search, setSearch] = useState('');
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState<Record<string, boolean>>({});
  const [approvalNotes, setApprovalNotes] = useState<Record<string, string>>({});

  const fetchTasks = useCallback(async () => {
    try {
      setLoading(true);
      merlinApi.setBaseUrl(baseUrl);
      const data = await merlinApi.getTasksHttp();
      setTasks(data);
    } catch (error) {
      console.error('Failed to fetch tasks:', error);
      toast.error('Failed to fetch tasks');
    } finally {
      setLoading(false);
    }
  }, [baseUrl]);

  useEffect(() => {
    fetchTasks();
    const ws = merlinApi.createEventsWebSocketConnection();
    if (ws) {
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (typeof data?.event_type === 'string') {
            if (data.event_type.includes('task') || data.event_type.startsWith('approval.')) {
              fetchTasks();
            }
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
  }, [fetchTasks]);

  const filtered = tasks.filter((task) => {
    if (statusFilter !== 'all' && task.status !== statusFilter) {
      return false;
    }
    if (!search.trim()) {
      return true;
    }
    const haystack = `${task.id} ${task.title} ${task.status} ${task.priority} ${task.assignee} ${task.execution_mode || ''} ${task.approvals || ''} ${task.preferred_role || ''} ${task.domain || ''}`.toLowerCase();
    return haystack.includes(search.toLowerCase());
  });

  const requestExecuteGate = async (task: TaskItem) => {
    const key = `${task.id}-request`;
    setActionBusy((prev) => ({ ...prev, [key]: true }));
    try {
      merlinApi.setBaseUrl(baseUrl);
      await merlinApi.requestApprovalHttp(task.id, 'execute', 'Desktop', ['desktop', 'androidapp'], {
        title: task.title,
      });
      toast.success('Execute gate requested');
      fetchTasks();
    } catch (error) {
      console.error('Failed to request execute gate:', error);
      toast.error('Failed to request execute gate');
    } finally {
      setActionBusy((prev) => ({ ...prev, [key]: false }));
    }
  };

  const startExecution = async (task: TaskItem) => {
    const key = `${task.id}-start`;
    setActionBusy((prev) => ({ ...prev, [key]: true }));
    try {
      merlinApi.setBaseUrl(baseUrl);
      const result = await merlinApi.startTaskHttp(task.id, 'Desktop');
      if (!result.ok) {
        toast.error(result.error || 'Execution blocked');
      } else {
        toast.success('Execution started');
        fetchTasks();
      }
    } catch (error) {
      console.error('Failed to start execution:', error);
      toast.error('Failed to start execution');
    } finally {
      setActionBusy((prev) => ({ ...prev, [key]: false }));
    }
  };

  const approvePendingGate = async (task: TaskItem, gate: string) => {
    const approvals = parseApprovals(task.approvals);
    const pending = approvals.find(
      (entry) => entry.gate === gate && entry.status.toLowerCase() === 'pending'
    );
    if (!pending) {
      toast.error('No pending approval found');
      return;
    }
    const key = `${task.id}-approve-${gate}`;
    setActionBusy((prev) => ({ ...prev, [key]: true }));
    try {
      merlinApi.setBaseUrl(baseUrl);
      const approvalsList = await merlinApi.getApprovalsHttp('pending', task.id);
      const approval = approvalsList.find((item) => item.gate === gate);
      if (!approval) {
        toast.error('Approval request not found');
        return;
      }
      const note = approvalNotes[`${task.id}-${gate}`] || '';
      await merlinApi.approveApprovalHttp(approval.approval_id, 'Desktop', note);
      toast.success('Approval granted');
      setApprovalNotes((prev) => ({ ...prev, [`${task.id}-${gate}`]: '' }));
      fetchTasks();
    } catch (error) {
      console.error('Failed to approve:', error);
      toast.error('Failed to approve');
    } finally {
      setActionBusy((prev) => ({ ...prev, [key]: false }));
    }
  };

  const rejectPendingGate = async (task: TaskItem, gate: string) => {
    const approvals = parseApprovals(task.approvals);
    const pending = approvals.find(
      (entry) => entry.gate === gate && entry.status.toLowerCase() === 'pending'
    );
    if (!pending) {
      toast.error('No pending approval found');
      return;
    }
    const key = `${task.id}-reject-${gate}`;
    setActionBusy((prev) => ({ ...prev, [key]: true }));
    try {
      merlinApi.setBaseUrl(baseUrl);
      const approvalsList = await merlinApi.getApprovalsHttp('pending', task.id);
      const approval = approvalsList.find((item) => item.gate === gate);
      if (!approval) {
        toast.error('Approval request not found');
        return;
      }
      const note = approvalNotes[`${task.id}-${gate}`] || '';
      await merlinApi.rejectApprovalHttp(approval.approval_id, 'Desktop', note);
      toast.success('Approval rejected');
      setApprovalNotes((prev) => ({ ...prev, [`${task.id}-${gate}`]: '' }));
      fetchTasks();
    } catch (error) {
      console.error('Failed to reject:', error);
      toast.error('Failed to reject');
    } finally {
      setActionBusy((prev) => ({ ...prev, [key]: false }));
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
          <h1 className="text-3xl font-bold text-gradient mb-2">Tasks</h1>
          <p className="text-dark-muted">Browse tasks with execution modes and approvals</p>
        </div>
        <button
          onClick={fetchTasks}
          className="btn btn-secondary"
          disabled={loading}
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
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
                  {formatStatus(option)}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <Search className="w-4 h-4 text-dark-muted" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tasks"
              className="rounded-md bg-dark-border border border-dark-border px-3 py-2 text-sm text-dark-text"
            />
          </div>
        </div>
      </div>

      <div className="card">
        {loading && filtered.length === 0 ? (
          <div className="text-sm text-dark-muted">Loading tasks…</div>
        ) : filtered.length === 0 ? (
          <div className="text-sm text-dark-muted">No tasks match your filters.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-dark-border/30">
                  <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-dark-muted">ID</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-dark-muted">Task</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-dark-muted">Status</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-dark-muted">Assignee</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-dark-muted">Mode</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-dark-muted">Approvals</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-dark-muted">Role/Domain</th>
                  <th className="px-4 py-3 text-xs font-bold uppercase tracking-wider text-dark-muted">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-dark-border">
                {filtered.map((task) => {
  const pendingGates = getPendingGates(task.approvals);
                  const pendingExecute = pendingGates.some((entry) => entry.gate === 'execute');
                  const requestKey = `${task.id}-request`;
                  const startKey = `${task.id}-start`;
                  return (
                    <tr key={task.id} className="hover:bg-dark-border/20">
                      <td className="px-4 py-3 text-xs font-mono text-dark-muted">
                        <Link to={`/tasks/${task.id}`} className="text-merlin-blue hover:underline">
                          {task.id}
                        </Link>
                      </td>
                    <td className="px-4 py-3">
                      <div className="text-sm font-semibold text-dark-text">{task.title}</div>
                      <div className="text-xs text-dark-muted">{task.priority} priority</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-dark-text">{formatStatus(task.status)}</td>
                    <td className="px-4 py-3 text-sm text-dark-muted">{task.assignee}</td>
                    <td className="px-4 py-3 text-sm text-dark-muted">{task.execution_mode || 'auto'}</td>
                    <td className="px-4 py-3 text-sm text-dark-muted">
                      <div className="flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4 text-merlin-blue" />
                        {task.approvals || 'none'}
                        {pendingExecute && (
                          <span className="text-xs text-amber-300">pending</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-dark-muted">
                      {task.preferred_role || '-'} / {task.domain || '-'}
                    </td>
                    <td className="px-4 py-3 text-xs text-dark-muted">
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          onClick={() => requestExecuteGate(task)}
                          className="rounded-md bg-dark-border/60 px-2 py-1 text-xs text-dark-text hover:bg-dark-border"
                          disabled={actionBusy[requestKey]}
                        >
                          Request Gate
                        </button>
                        <button
                          onClick={() => startExecution(task)}
                          className="rounded-md bg-emerald-600/30 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-600/40"
                          disabled={actionBusy[startKey] || pendingExecute}
                        >
                          Start
                        </button>
                        {pendingExecute && (
                          <div className="flex flex-col gap-2">
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() =>
                                  pendingGates.forEach((entry) =>
                                    approvePendingGate(task, entry.gate)
                                  )
                                }
                                className="rounded-md bg-emerald-600/30 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-600/40"
                                disabled={pendingGates.length === 0}
                              >
                                Approve All
                              </button>
                              <button
                                onClick={() =>
                                  pendingGates.forEach((entry) =>
                                    rejectPendingGate(task, entry.gate)
                                  )
                                }
                                className="rounded-md bg-amber-600/30 px-2 py-1 text-xs text-amber-200 hover:bg-amber-600/40"
                                disabled={pendingGates.length === 0}
                              >
                                Reject All
                              </button>
                            </div>
                            {pendingGates.map((entry) => {
                              const approveKey = `${task.id}-approve-${entry.gate}`;
                              const rejectKey = `${task.id}-reject-${entry.gate}`;
                              return (
                                <div key={`${task.id}-${entry.gate}`} className="flex flex-wrap items-center gap-2">
                                  <span className="text-[10px] text-amber-300">{entry.gate} gate</span>
                                  <input
                                    value={approvalNotes[`${task.id}-${entry.gate}`] || ''}
                                    onChange={(event) =>
                                      setApprovalNotes((prev) => ({
                                        ...prev,
                                        [`${task.id}-${entry.gate}`]: event.target.value
                                      }))
                                    }
                                    placeholder="note"
                                    className="w-24 rounded bg-dark-border px-2 py-1 text-[10px] text-dark-text"
                                  />
                                  <button
                                    onClick={() => approvePendingGate(task, entry.gate)}
                                    className="rounded-md bg-emerald-600/30 px-2 py-1 text-xs text-emerald-200 hover:bg-emerald-600/40"
                                    disabled={actionBusy[approveKey]}
                                  >
                                    Approve
                                  </button>
                                  <button
                                    onClick={() => rejectPendingGate(task, entry.gate)}
                                    className="rounded-md bg-amber-600/30 px-2 py-1 text-xs text-amber-200 hover:bg-amber-600/40"
                                    disabled={actionBusy[rejectKey]}
                                  >
                                    Reject
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default Tasks;
