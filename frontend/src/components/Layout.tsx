import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { 
  LayoutDashboard, 
  Cpu, 
  Settings, 
  Activity,
  Menu,
  X
} from 'lucide-react';
import { motion } from 'framer-motion';
import { useDashboardStore } from '../store/dashboard';

const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  const { dashboardData, connectionStatus } = useDashboardStore();
  const [sidebarOpen, setSidebarOpen] = React.useState(false);

  const navigation = [
    { name: 'Dashboard', href: '/', icon: LayoutDashboard },
    { name: 'Models', href: '/models', icon: Cpu },
    { name: 'Activity', href: '/activity', icon: Activity },
    { name: 'Settings', href: '/settings', icon: Settings },
  ];

  const isActive = (href: string) => {
    if (href === '/') {
      return location.pathname === '/';
    }
    return location.pathname.startsWith(href);
  };

  return (
    <div className="flex h-screen bg-dark-bg">
      {/* Sidebar */}
      <motion.div
        initial={false}
        animate={{ x: sidebarOpen ? 0 : -280 }}
        className="fixed inset-y-0 left-0 z-50 w-64 bg-dark-card border-r border-dark-border lg:static lg:inset-0"
      >
        <div className="flex h-full flex-col">
          {/* Logo */}
          <div className="flex h-16 items-center justify-between px-6 border-b border-dark-border">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-gradient-to-br from-merlin-blue to-merlin-purple rounded-lg flex items-center justify-center">
                <Cpu className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-semibold text-gradient">Merlin</h1>
                <p className="text-xs text-dark-muted">Multi-Model Dashboard</p>
              </div>
            </div>
            <button
              onClick={() => setSidebarOpen(false)}
              className="lg:hidden text-dark-muted hover:text-dark-text"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 space-y-1 px-3 py-4">
            {navigation.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`${
                    isActive(item.href)
                      ? 'sidebar-item-active'
                      : 'sidebar-item-inactive'
                  }`}
                >
                  <Icon className="w-5 h-5 mr-3" />
                  {item.name}
                </Link>
              );
            })}
          </nav>

          {/* Connection Status */}
          <div className="border-t border-dark-border p-4">
            <div className="flex items-center space-x-2 mb-2">
              <div className={`status-${
                connectionStatus.connected ? 'online' : 'offline'
              }`} />
              <span className="text-sm text-dark-muted">
                {connectionStatus.connected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            {dashboardData && (
              <div className="text-xs text-dark-muted">
                <div>Strategy: {dashboardData.strategy}</div>
                <div>Models: {dashboardData.summary.model_count}</div>
                <div>Learning: {dashboardData.learning_mode ? 'ON' : 'OFF'}</div>
              </div>
            )}
          </div>
        </div>
      </motion.div>

      {/* Main Content */}
      <div className="flex-1 lg:ml-0">
        {/* Top Bar */}
        <header className="h-16 bg-dark-card border-b border-dark-border flex items-center justify-between px-6">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden text-dark-muted hover:text-dark-text"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="flex items-center space-x-4">
            <div className="text-right">
              <h2 className="text-sm font-medium text-dark-text">
                {navigation.find(item => isActive(item.href))?.name || 'Dashboard'}
              </h2>
              {dashboardData && (
                <p className="text-xs text-dark-muted">
                  Last updated: {new Date(dashboardData.timestamp).toLocaleTimeString()}
                </p>
              )}
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>

      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
};

export default Layout;