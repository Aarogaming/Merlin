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
  maturity_tier?: string;
  maturity_readiness_status?: string;
  maturity_regression_status?: string;
}

export interface MaturityStatusCard {
  tier: string;
  policy_version: string;
  readiness_status: string;
  regression_status: string;
  recommended_action: string;
  recommended_tier: string;
  critical_failure_count: number;
  missing_promotion_gate_count: number;
  report_generated_at?: string | null;
  report_path?: string | null;
}

export interface DashboardStatus {
  type: string;
  timestamp: string;
  strategy: string;
  learning_mode: boolean;
  models: Record<string, ModelMetrics>;
  summary: SummaryStats;
  maturity_status_card?: MaturityStatusCard;
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

export interface ApprovalRequest {
  approval_id: string;
  task_id: string;
  gate: string;
  status: 'pending' | 'approved' | 'rejected';
  requested_by: string;
  targets: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  decided_by?: string | null;
  decision_note?: string | null;
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
  myFortressUrl?: string;
  notifications: NotificationConfig;
  charts: {
    showHistoricalData: boolean;
    dataPoints: number;
    realTimeUpdates: boolean;
  };
}

export interface TaskItem {
  id: string;
  title: string;
  priority: string;
  status: string;
  assignee: string;
  depends_on: string;
  created: string;
  updated: string;
  execution_mode?: string;
  approvals?: string;
  preferred_role?: string;
  domain?: string;
}

export interface ResearchSource {
  url: string;
  title: string;
  snippet: string;
  relevance: number;
}

export interface ResearchReport {
  query: string;
  summary: string;
  findings: string[];
  sources: ResearchSource[];
  images_analyzed: number;
  code_results: Record<string, unknown>[];
  generated_at: string;
  confidence: number;
  metadata: Record<string, unknown>;
}

export interface ResearchResponse {
  ok: boolean;
  report: ResearchReport;
  formatted: string;
  image_analyses: Record<string, unknown>[];
  metadata: Record<string, unknown>;
}
