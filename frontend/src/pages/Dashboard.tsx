import { useCallback, useEffect } from 'react';
import { motion } from 'framer-motion';
import { 
  Activity, 
  Zap, 
  TrendingUp, 
  Cpu, 
  Clock,
  CheckCircle,
  AlertTriangle
} from 'lucide-react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { useDashboardStore } from '../store/dashboard';
import { merlinApi } from '../services/api';
import ModelPerformanceGrid from '../components/ModelPerformanceGrid';
import MetricCard from '../components/MetricCard';
import ConnectionStatus from '../components/ConnectionStatus';
import SystemInfo from '../components/SystemInfo';
import SnapshotSummary from '../components/SnapshotSummary';
import AgentAnalytics from '../components/AgentAnalytics';
import PluginAnalytics from '../components/PluginAnalytics';
import MaturityStatusCard from '../components/MaturityStatusCard';
import toast from 'react-hot-toast';

const Dashboard = () => {
  const {
    dashboardData,
    setDashboardData,
    setConnectionStatus,
    setLoading,
    setError,
    updateLastUpdate,
    settings,
  } = useDashboardStore();

  // Fetch dashboard data
  const fetchDashboardData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      const data = await merlinApi.getDashboardStatus();
      setDashboardData(data);
      setConnectionStatus({ connected: true });
      updateLastUpdate();
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
      setError(error instanceof Error ? error.message : 'Failed to fetch data');
      setConnectionStatus({ 
        connected: false, 
        error: error instanceof Error ? error.message : 'Connection failed' 
      });
      toast.error('Failed to fetch dashboard data');
    } finally {
      setLoading(false);
    }
  }, [setLoading, setError, setDashboardData, setConnectionStatus, updateLastUpdate]);

  // Initial load and periodic updates
  useEffect(() => {
    fetchDashboardData();
    
    if (settings.charts.realTimeUpdates) {
      const interval = setInterval(fetchDashboardData, settings.refreshInterval);
      return () => clearInterval(interval);
    }
  }, [fetchDashboardData, settings.charts.realTimeUpdates, settings.refreshInterval]);

  // Setup WebSocket for real-time updates
  useEffect(() => {
    const ws = merlinApi.createWebSocketConnection();
    
    if (ws) {
      ws.onopen = () => {
        setConnectionStatus({ connected: true });
        console.log('WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'status') {
            setDashboardData(data);
            updateLastUpdate();
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionStatus({ 
          connected: false, 
          error: 'WebSocket connection error' 
        });
      };

      ws.onclose = () => {
        setConnectionStatus({ connected: false });
        console.log('WebSocket disconnected');
      };

      return () => {
        ws.close();
      };
    }
  }, [setConnectionStatus, setDashboardData, updateLastUpdate]);

  // Prepare chart data
  const latencyData = dashboardData?.models ? 
    Object.entries(dashboardData.models).map(([name, metrics]) => ({
      name: name.split('-')[0], // Shorten name for display
      latency: parseFloat(metrics.avg_latency.toFixed(2)),
      successRate: parseFloat((metrics.success_rate * 100).toFixed(1)),
      requests: metrics.total_requests,
    })) : [];

  const pieData = dashboardData?.models ?
    Object.entries(dashboardData.models).map(([name, metrics]) => ({
      name,
      value: metrics.total_requests,
    })) : [];

  const COLORS = ['#00d4ff', '#8b5cf6', '#00ff88', '#f59e0b', '#ef4444', '#10b981'];

  if (!dashboardData) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-merlin-blue border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-dark-muted">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gradient mb-2">Merlin Dashboard</h1>
          <p className="text-dark-muted">Real-time multi-model performance monitoring</p>
        </div>
        <ConnectionStatus />
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard
          title="Total Requests"
          value={dashboardData.summary.total_requests.toLocaleString()}
          icon={<Activity className="w-6 h-6" />}
          trend={null}
          color="blue"
        />
        <MetricCard
          title="Success Rate"
          value={`${(dashboardData.summary.overall_success_rate * 100).toFixed(1)}%`}
          icon={<CheckCircle className="w-6 h-6" />}
          trend={null}
          color="green"
        />
        <MetricCard
          title="Avg Latency"
          value={`${dashboardData.summary.overall_avg_latency.toFixed(2)}s`}
          icon={<Clock className="w-6 h-6" />}
          trend={null}
          color="yellow"
        />
        <MetricCard
          title="Active Models"
          value={dashboardData.summary.active_models}
          icon={<Cpu className="w-6 h-6" />}
          subtitle={`of ${dashboardData.summary.model_count} total`}
          trend={null}
          color="purple"
        />
      </div>

      <MaturityStatusCard card={dashboardData.maturity_status_card} />

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 min-w-0">
        {/* Latency Chart */}
        <div className="card min-w-0 overflow-x-auto">
          <h3 className="text-lg font-semibold mb-4 text-merlin-blue">Model Latency</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={latencyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" stroke="#64748b" />
              <YAxis stroke="#64748b" />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1e293b', 
                  border: '1px solid #334155',
                  borderRadius: '8px' 
                }}
              />
              <Bar dataKey="latency" fill="#00d4ff" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Success Rate Chart */}
        <div className="card min-w-0 overflow-x-auto">
          <h3 className="text-lg font-semibold mb-4 text-merlin-green">Success Rates</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={latencyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" stroke="#64748b" />
              <YAxis stroke="#64748b" />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1e293b', 
                  border: '1px solid #334155',
                  borderRadius: '8px' 
                }}
              />
              <Line 
                type="monotone" 
                dataKey="successRate" 
                stroke="#00ff88" 
                strokeWidth={3}
                dot={{ fill: '#00ff88', r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Request Distribution & Model Performance */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 min-w-0">
        {/* Request Distribution Pie Chart */}
        <div className="card min-w-0 overflow-x-auto">
          <h3 className="text-lg font-semibold mb-4 text-merlin-purple">Request Distribution</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={pieData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, percent }) => `${name.split('-')[0]} ${(percent * 100).toFixed(0)}%`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {pieData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1e293b', 
                  border: '1px solid #334155',
                  borderRadius: '8px' 
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Best Model & Strategy Info */}
        <div className="lg:col-span-2 space-y-4">
          <div className="card">
            <h3 className="text-lg font-semibold mb-4 text-merlin-blue">System Status</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-merlin-green/20 rounded-lg flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-merlin-green" />
                </div>
                <div>
                  <p className="text-sm text-dark-muted">Best Model</p>
                  <p className="font-semibold">{dashboardData.summary.best_model || 'N/A'}</p>
                </div>
              </div>
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-merlin-blue/20 rounded-lg flex items-center justify-center">
                  <Zap className="w-5 h-5 text-merlin-blue" />
                </div>
                <div>
                  <p className="text-sm text-dark-muted">Strategy</p>
                  <p className="font-semibold">{dashboardData.strategy.toUpperCase()}</p>
                </div>
              </div>
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-merlin-purple/20 rounded-lg flex items-center justify-center">
                  <Cpu className="w-5 h-5 text-merlin-purple" />
                </div>
                <div>
                  <p className="text-sm text-dark-muted">Learning Mode</p>
                  <p className="font-semibold">{dashboardData.learning_mode ? 'ENABLED' : 'DISABLED'}</p>
                </div>
              </div>
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 bg-warning/20 rounded-lg flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-warning" />
                </div>
                <div>
                  <p className="text-sm text-dark-muted">Last Update</p>
                  <p className="font-semibold">{new Date(dashboardData.timestamp).toLocaleTimeString()}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Model Performance Grid */}
      <ModelPerformanceGrid />

      {/* Gateway Snapshot Summary */}
      <SnapshotSummary 
        myFortressUrl={settings.myFortressUrl} 
        refreshInterval={15000}
        includeHomeAssistant={true}
        includeFrigate={true}
      />

      {/* MyFortress System Info */}
      <SystemInfo myFortressUrl={settings.myFortressUrl} refreshInterval={10000} />

      {/* AI Agent Analytics */}
      <AgentAnalytics apiUrl={settings.myFortressUrl} refreshInterval={15000} />

      {/* Plugin Analytics */}
      <PluginAnalytics />
    </motion.div>
  );
};

export default Dashboard;
