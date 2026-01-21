export interface ModelMetrics {
  total_requests: number;
  success_rate: number;
  avg_latency: number;
  avg_rating: number;
  recent_history?: ModelHistoryEntry[];
}

export interface ModelHistoryEntry {
  timestamp: string;
  model: string;
  total_requests: number;
  success_rate: number;
  avg_latency: number;
  avg_rating: number;
}

export interface SummaryStats {
  total_requests: number;
  overall_success_rate: number;
  overall_avg_latency: number;
  best_model: string | null;
  model_count: number;
  active_models: number;
}

export interface DashboardStatus {
  type: string;
  timestamp: string;
  strategy: string;
  learning_mode: boolean;
  models: Record<string, ModelMetrics>;
  summary: SummaryStats;
}

export interface ModelRequest {
  model_name: string;
  prompt: string;
}

export interface ModelResponse {
  response: string;
  model: string;
  latency: number;
  success: boolean;
  error?: string;
}

export interface ConnectionStatus {
  connected: boolean;
  lastUpdate?: string;
  error?: string;
}

export interface PerformanceChart {
  timestamp: string;
  latency: number;
  success_rate: number;
  requests: number;
}

export interface ModelConfig {
  name: string;
  endpoint: string;
  apiKey?: string;
  enabled: boolean;
  maxTokens?: number;
  temperature?: number;
}

export interface NotificationConfig {
  enabled: boolean;
  thresholds: {
    success_rate: number;
    latency: number;
    error_rate: number;
  };
}

export interface DashboardSettings {
  refreshInterval: number;
  theme: 'light' | 'dark' | 'auto';
  notifications: NotificationConfig;
  charts: {
    showHistoricalData: boolean;
    dataPoints: number;
    realTimeUpdates: boolean;
  };
}