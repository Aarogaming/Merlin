import { invoke } from '@tauri-apps/api/tauri';
import { DashboardStatus, ModelRequest, ModelResponse } from '../types';

export class MerlinApiService {
  private baseUrl: string;

  constructor(baseUrl: string = 'http://localhost:8000') {
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
}

export const merlinApi = new MerlinApiService();