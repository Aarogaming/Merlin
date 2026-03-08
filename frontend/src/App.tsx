import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import { QueryClient, QueryClientProvider } from 'react-query';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import ModelDetails from './pages/ModelDetails';
import Settings from './pages/Settings';
import Approvals from './pages/Approvals';
import TaskDetails from './pages/TaskDetails';
import Tasks from './pages/Tasks';
import ControlCenter from './pages/ControlCenter';
import ResearchSessions from './pages/ResearchSessions';
import CommandPalette from './components/CommandPalette';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 3,
      staleTime: 5000,
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <div className="min-h-screen bg-dark-bg text-dark-text">
          <div className="fixed top-3 right-3 z-[95]">
            <CommandPalette />
          </div>
          <Layout>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/control-center" element={<ControlCenter />} />
              <Route path="/research-sessions" element={<ResearchSessions />} />
              <Route path="/model/:modelName" element={<ModelDetails />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/approvals" element={<Approvals />} />
              <Route path="/tasks/:taskId" element={<TaskDetails />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </Layout>
          <Toaster
            position="top-right"
            toastOptions={{
              duration: 4000,
              style: {
                background: '#1e293b',
                color: '#f1f5f9',
                border: '1px solid #334155',
              },
              success: {
                iconTheme: {
                  primary: '#10b981',
                  secondary: '#f1f5f9',
                },
              },
              error: {
                iconTheme: {
                  primary: '#ef4444',
                  secondary: '#f1f5f9',
                },
              },
            }}
          />
        </div>
      </Router>
    </QueryClientProvider>
  );
}

export default App;
