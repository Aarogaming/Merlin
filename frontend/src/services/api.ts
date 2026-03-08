import { invoke } from '@tauri-apps/api/tauri';
import { DashboardStatus, ModelRequest, ModelResponse, ApprovalRequest, TaskItem, ResearchResponse } from '../types';
import {
  OPERATION_CONTRACT_FIXTURES,
  OPERATION_NAMES,
  type OperationName,
} from './operationContracts.generated';

export class MerlinApiService {
  private baseUrl: string;

  constructor(baseUrl = 'http://localhost:8000') {
    this.baseUrl = baseUrl;
  }

  async getDashboardStatus(): Promise<DashboardStatus> {
    try {
      return await invoke('get_dashboard_status', { apiUrl: this.baseUrl });
    } catch (error) {
      console.error('Failed to fetch dashboard status from Tauri:', error);
      throw error;
    }
  }

  async getCachedDashboardStatus(): Promise<DashboardStatus | null> {
    try {
      return await invoke('get_cached_dashboard_status');
    } catch (error) {
      console.error('Failed to get cached dashboard status:', error);
      return null;
    }
  }

  async sendModelRequest(request: ModelRequest): Promise<ModelResponse> {
    try {
      const response = await invoke('send_model_request', {
        modelName: request.model_name,
        prompt: request.prompt,
        apiUrl: this.baseUrl,
      });
      return response as ModelResponse;
    } catch (error) {
      console.error('Failed to send model request:', error);
      throw error;
    }
  }

  // Fallback HTTP methods for web mode
  async getDashboardStatusHttp(): Promise<DashboardStatus> {
    const response = await fetch(`${this.baseUrl}/api/dashboard/status`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  }

  async sendModelRequestHttp(request: ModelRequest): Promise<ModelResponse> {
    const response = await fetch(`${this.baseUrl}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        prompt: request.prompt,
        model: request.model_name,
      }),
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return response.json();
  }

  async validateDatabase(databaseUrl: string): Promise<{ valid: boolean; error?: string }> {
    if (!databaseUrl) {
      return { valid: false, error: 'Database URL is required' };
    }
    try {
      const response = await fetch(`${this.baseUrl}/api/onboarding/validate/database`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ databaseUrl }),
      });
      if (response.ok) {
        return response.json();
      }
      if (response.status === 404) {
        return { valid: true };
      }
      return { valid: false, error: `Database validation failed (${response.status})` };
    } catch (error) {
      return {
        valid: false,
        error: error instanceof Error ? error.message : 'Database validation failed',
      };
    }
  }

  async getApprovalsHttp(status = 'pending', taskId?: string): Promise<ApprovalRequest[]> {
    const params = new URLSearchParams();
    if (status) {
      params.set('status', status);
    }
    if (taskId) {
      params.set('task_id', taskId);
    }
    const query = params.toString() ? `?${params.toString()}` : '';
    const response = await fetch(`${this.baseUrl}/approvals${query}`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    return data.approvals || [];
  }

  async requestApprovalHttp(
    taskId: string,
    gate: string,
    requestedBy: string,
    targets: string[] = [],
    metadata: Record<string, unknown> = {}
  ) {
    const response = await fetch(`${this.baseUrl}/approvals/request`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        task_id: taskId,
        gate,
        requested_by: requestedBy,
        targets,
        metadata,
      }),
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  }

  async approveApprovalHttp(approvalId: string, decidedBy: string, note?: string) {
    const response = await fetch(`${this.baseUrl}/approvals/${approvalId}/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ decided_by: decidedBy, note }),
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  }

  async rejectApprovalHttp(approvalId: string, decidedBy: string, note?: string) {
    const response = await fetch(`${this.baseUrl}/approvals/${approvalId}/reject`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ decided_by: decidedBy, note }),
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  }

  async getTasksHttp(): Promise<TaskItem[]> {
    const response = await fetch(`${this.baseUrl}/tasks`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    return data.tasks || [];
  }

  async getTaskHttp(taskId: string): Promise<TaskItem> {
    const response = await fetch(`${this.baseUrl}/tasks/${taskId}`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    return data.task;
  }

  async startTaskHttp(taskId: string, actor: string): Promise<{ ok: boolean; error?: string }>{
    const response = await fetch(`${this.baseUrl}/tasks/${taskId}/start?actor=${encodeURIComponent(actor)}`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  }

  async runResearchHttp(payload: {
    query: string;
    include_web_search?: boolean;
    include_code_analysis?: boolean;
    image_paths?: string[];
    code_snippets?: string[];
    max_sources?: number;
    output_format?: 'markdown' | 'json';
    use_local_vision?: boolean;
    store_to_knowledge?: boolean;
    metadata?: Record<string, unknown>;
  }): Promise<ResearchResponse> {
    const response = await fetch(`${this.baseUrl}/research`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  }

  async writeFileBase64(path: string, base64Content: string, overwrite = true) {
    const response = await fetch(`${this.baseUrl}/files/write`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        path,
        content: base64Content,
        mode: 'base64',
        overwrite,
        create_parents: true,
      }),
    });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    return response.json();
  }

  createEventsWebSocketConnection(): WebSocket | null {
    if (typeof window !== 'undefined') {
      const url = new URL(this.baseUrl);
      const protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      return new WebSocket(`${protocol}//${url.host}/ws/events`);
    }
    return null;
  }

  // WebSocket connection for real-time updates
  createWebSocketConnection(): WebSocket | null {
    if (typeof window !== 'undefined') {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;
      return new WebSocket(wsUrl);
    }
    return null;
  }

  setBaseUrl(url: string) {
    this.baseUrl = url;
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  getOperationContractNames(): readonly OperationName[] {
    return OPERATION_NAMES;
  }

  getOperationContractFixture(operation: OperationName) {
    return OPERATION_CONTRACT_FIXTURES[operation];
  }
}

export const merlinApi = new MerlinApiService();
