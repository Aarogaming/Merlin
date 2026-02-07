import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Activity, Clock, CheckCircle, Star, TrendingUp } from 'lucide-react';
import { LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useDashboardStore } from '../store/dashboard';

const ModelDetails = () => {
  const { modelName } = useParams<{ modelName: string }>();
  const navigate = useNavigate();
  const { dashboardData } = useDashboardStore();

  const modelData = dashboardData?.models[decodeURIComponent(modelName || '')];

  useEffect(() => {
    if (!modelName) {
      navigate('/');
      return;
    }
  }, [modelName, navigate]);

  if (!modelData) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold mb-4">Model not found</h2>
        <p className="text-dark-muted mb-6">The requested model could not be found.</p>
        <button
          onClick={() => navigate('/')}
          className="btn btn-primary"
        >
          Back to Dashboard
        </button>
      </div>
    );
  }

  // Generate mock historical data for demonstration
  const historicalData = Array.from({ length: 24 }, (_, i) => ({
    time: `${i}:00`,
    latency: Math.max(0.5, modelData.avg_latency + (Math.random() - 0.5) * 2),
    successRate: Math.max(0.7, modelData.success_rate + (Math.random() - 0.5) * 0.3),
    requests: Math.floor(Math.random() * 100) + 50,
  }));

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/')}
            className="btn btn-secondary"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </button>
          <div>
            <h1 className="text-3xl font-bold text-gradient">
              {decodeURIComponent(modelName || '')}
            </h1>
            <p className="text-dark-muted">Detailed model performance metrics</p>
          </div>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="metric-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-dark-muted">Total Requests</p>
              <p className="text-2xl font-bold">{modelData.total_requests.toLocaleString()}</p>
            </div>
            <Activity className="w-8 h-8 text-merlin-blue" />
          </div>
        </div>

        <div className="metric-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-dark-muted">Success Rate</p>
              <p className="text-2xl font-bold text-success">
                {(modelData.success_rate * 100).toFixed(1)}%
              </p>
            </div>
            <CheckCircle className="w-8 h-8 text-success" />
          </div>
        </div>

        <div className="metric-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-dark-muted">Average Latency</p>
              <p className="text-2xl font-bold text-warning">
                {modelData.avg_latency.toFixed(2)}s
              </p>
            </div>
            <Clock className="w-8 h-8 text-warning" />
          </div>
        </div>

        <div className="metric-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-dark-muted">User Rating</p>
              <p className="text-2xl font-bold flex items-center">
                <Star className="w-6 h-6 text-yellow-500 mr-2" />
                {modelData.avg_rating.toFixed(1)}
              </p>
            </div>
            <TrendingUp className="w-8 h-8 text-merlin-purple" />
          </div>
        </div>
      </div>

      {/* Performance Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="text-lg font-semibold mb-4 text-merlin-blue">Latency Trend (24h)</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={historicalData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="time" stroke="#64748b" />
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
                dataKey="latency" 
                stroke="#00d4ff" 
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h3 className="text-lg font-semibold mb-4 text-merlin-green">Success Rate Trend (24h)</h3>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={historicalData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="time" stroke="#64748b" />
              <YAxis stroke="#64748b" domain={[0, 100]} />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1e293b', 
                  border: '1px solid #334155',
                  borderRadius: '8px' 
                }}
              />
              <Area 
                type="monotone" 
                dataKey="successRate" 
                stroke="#00ff88" 
                fill="#00ff88"
                fillOpacity={0.3}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recent History */}
      {modelData.recent_history && modelData.recent_history.length > 0 && (
        <div className="card">
          <h3 className="text-lg font-semibold mb-4 text-merlin-purple">Recent Performance</h3>
          <div className="space-y-3">
            {modelData.recent_history.slice(0, 10).map((entry, index) => (
              <div key={index} className="flex items-center justify-between p-3 bg-dark-border/30 rounded-lg">
                <div className="flex items-center space-x-3">
                  <div className={`w-2 h-2 rounded-full ${
                    entry.success_rate >= 0.9 ? 'bg-success' : 
                    entry.success_rate >= 0.7 ? 'bg-warning' : 'bg-danger'
                  }`} />
                  <div>
                    <p className="text-sm font-medium">{entry.model}</p>
                    <p className="text-xs text-dark-muted">
                      {new Date(entry.timestamp).toLocaleString()}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium">
                    {(entry.success_rate * 100).toFixed(1)}%
                  </p>
                  <p className="text-xs text-dark-muted">
                    {entry.avg_latency.toFixed(2)}s
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
};

export default ModelDetails;
