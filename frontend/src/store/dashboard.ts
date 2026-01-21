import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { DashboardStatus, ConnectionStatus, DashboardSettings } from '../types';

interface DashboardState {
  // Data
  dashboardData: DashboardStatus | null;
  connectionStatus: ConnectionStatus;
  settings: DashboardSettings;
  
  // UI State
  selectedModel: string | null;
  isLoading: boolean;
  error: string | null;
  lastUpdate: string | null;
  
  // Actions
  setDashboardData: (data: DashboardStatus) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setSettings: (settings: DashboardSettings) => void;
  setSelectedModel: (model: string | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  updateLastUpdate: () => void;
  
  // Computed
  isConnected: () => boolean;
  getModelCount: () => number;
  getActiveModelCount: () => number;
  getBestModel: () => string | null;
}

const defaultSettings: DashboardSettings = {
  refreshInterval: 5000,
  theme: 'dark',
  notifications: {
    enabled: true,
    thresholds: {
      success_rate: 0.8,
      latency: 2.0,
      error_rate: 0.1,
    },
  },
  charts: {
    showHistoricalData: true,
    dataPoints: 50,
    realTimeUpdates: true,
  },
};

export const useDashboardStore = create<DashboardState>()(
  subscribeWithSelector((set, get) => ({
    // Initial state
    dashboardData: null,
    connectionStatus: { connected: false },
    settings: defaultSettings,
    selectedModel: null,
    isLoading: false,
    error: null,
    lastUpdate: null,

    // Actions
    setDashboardData: (data) => set({ dashboardData: data, error: null }),
    
    setConnectionStatus: (status) => set({ connectionStatus: status }),
    
    setSettings: (settings) => set({ settings }),
    
    setSelectedModel: (model) => set({ selectedModel: model }),
    
    setLoading: (loading) => set({ isLoading: loading }),
    
    setError: (error) => set({ error }),
    
    updateLastUpdate: () => set({ lastUpdate: new Date().toISOString() }),

    // Computed getters
    isConnected: () => get().connectionStatus.connected,
    
    getModelCount: () => get().dashboardData?.summary.model_count || 0,
    
    getActiveModelCount: () => get().dashboardData?.summary.active_models || 0,
    
    getBestModel: () => get().dashboardData?.summary.best_model || null,
  }))
);

// Subscribe to store changes for localStorage persistence
if (typeof window !== 'undefined') {
  useDashboardStore.subscribe(
    (state) => state.settings,
    (settings) => {
      localStorage.setItem('merlin-dashboard-settings', JSON.stringify(settings));
    }
  );

  // Load settings from localStorage on init
  const savedSettings = localStorage.getItem('merlin-dashboard-settings');
  if (savedSettings) {
    try {
      const settings = JSON.parse(savedSettings);
      useDashboardStore.setState({ settings });
    } catch (error) {
      console.error('Failed to load settings from localStorage:', error);
    }
  }
}