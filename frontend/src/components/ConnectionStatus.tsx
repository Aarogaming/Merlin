import React from 'react';
import { useDashboardStore } from '../store/dashboard';

const ConnectionStatus: React.FC = () => {
  const { connectionStatus } = useDashboardStore();

  return (
    <div className="flex items-center space-x-3 px-4 py-2 rounded-lg bg-dark-card border border-dark-border">
      <div className={`w-2 h-2 rounded-full ${
        connectionStatus.connected ? 'bg-success animate-pulse' : 'bg-danger'
      }`} />
      <span className="text-sm text-dark-muted">
        {connectionStatus.connected ? 'Connected' : 'Disconnected'}
      </span>
      {connectionStatus.error && (
        <span className="text-xs text-danger ml-2">
          {connectionStatus.error}
        </span>
      )}
    </div>
  );
};

export default ConnectionStatus;