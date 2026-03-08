/**
 * Onboarding API Service (AD-129)
 * API calls for onboarding validation
 */

import { merlinApi } from './api';

export interface OnboardingValidationResult {
  valid: boolean;
  error?: string;
}

export interface OnboardingData {
  apiUrl: string;
  apiKey: string;
  databaseUrl?: string;
  enableNotifications: boolean;
  autoRefresh: boolean;
  theme: 'light' | 'dark';
}

export interface ResearchSessionSummary {
  session_id: string;
  objective?: string;
  created_at?: string;
  updated_at?: string;
  status?: string;
  tags?: string[];
  signal_count?: number;
  archived?: boolean;
  [key: string]: unknown;
}

export interface ResearchSessionsListResult {
  sessions: ResearchSessionSummary[];
  next_cursor: string | null;
  query?: string;
}

export interface ResearchSessionDetailResult {
  session: Record<string, unknown>;
}

export interface ResearchSessionBriefResult {
  brief: Record<string, unknown>;
}

class OnboardingService {
  private buildAuthHeaders(apiKey?: string): HeadersInit {
    if (apiKey && apiKey.trim()) {
      return {
        'Authorization': `Bearer ${apiKey.trim()}`,
      };
    }
    return {};
  }

  /**
   * Validate API connection
   */
  async validateApiConnection(apiUrl: string): Promise<OnboardingValidationResult> {
    try {
      const response = await fetch(`${apiUrl}/health`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        timeout: 5000,
      } as RequestInit);

      if (response.ok) {
        return { valid: true };
      }

      return {
        valid: false,
        error: `API returned status ${response.status}`,
      };
    } catch (error) {
      return {
        valid: false,
        error: error instanceof Error ? error.message : 'Failed to connect to API',
      };
    }
  }

  /**
   * Validate API key
   */
  async validateApiKey(
    apiUrl: string,
    apiKey: string
  ): Promise<OnboardingValidationResult> {
    try {
      const response = await fetch(`${apiUrl}/validate-key`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`,
        },
      });

      if (response.ok) {
        return { valid: true };
      }

      if (response.status === 401) {
        return {
          valid: false,
          error: 'Invalid API key',
        };
      }

      return {
        valid: false,
        error: 'Failed to validate API key',
      };
    } catch (error) {
      return {
        valid: false,
        error: error instanceof Error ? error.message : 'Validation failed',
      };
    }
  }

  /**
   * Validate database connection
   */
  async validateDatabaseConnection(
    databaseUrl: string
  ): Promise<OnboardingValidationResult> {
    try {
      // This would typically be a call to the backend
      // which would then validate the database connection
      const response = await merlinApi.validateDatabase(databaseUrl);

      if (response.valid) {
        return { valid: true };
      }

      return {
        valid: false,
        error: response.error || 'Database connection failed',
      };
    } catch (error) {
      return {
        valid: false,
        error: error instanceof Error ? error.message : 'Database validation failed',
      };
    }
  }

  /**
   * Save onboarding configuration
   */
  async saveConfiguration(data: OnboardingData): Promise<OnboardingValidationResult> {
    try {
      const response = await fetch('/api/onboarding/save', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${data.apiKey}`,
        },
        body: JSON.stringify({
          apiUrl: data.apiUrl,
          databaseUrl: data.databaseUrl,
          enableNotifications: data.enableNotifications,
          autoRefresh: data.autoRefresh,
          theme: data.theme,
        }),
      });

      if (response.ok) {
        await response.json();
        return { valid: true };
      }

      return {
        valid: false,
        error: 'Failed to save configuration',
      };
    } catch (error) {
      return {
        valid: false,
        error: error instanceof Error ? error.message : 'Save failed',
      };
    }
  }

  /**
   * Check if onboarding is required
   */
  async isOnboardingRequired(): Promise<boolean> {
    try {
      const response = await fetch('/api/onboarding/required', {
        method: 'GET',
      });

      if (response.ok) {
        const data = await response.json();
        return data.required || false;
      }

      return true; // Assume required if can't check
    } catch {
      return true;
    }
  }

  /**
   * Get existing onboarding data
   */
  async getExistingConfiguration(): Promise<Partial<OnboardingData> | null> {
    try {
      const response = await fetch('/api/onboarding/config', {
        method: 'GET',
      });

      if (response.ok) {
        return await response.json();
      }

      return null;
    } catch {
      return null;
    }
  }

  /**
   * List research manager sessions with optional cursor/tag/topic filters.
   */
  async listResearchSessions(params?: {
    apiKey?: string;
    limit?: number;
    cursor?: string;
    tag?: string;
    topic?: string;
  }): Promise<ResearchSessionsListResult> {
    const limit = Math.max(1, Math.min(params?.limit ?? 20, 200));
    const searchParams = new URLSearchParams();
    searchParams.set('limit', String(limit));
    if (params?.cursor) {
      searchParams.set('cursor', params.cursor);
    }
    if (params?.tag) {
      searchParams.set('tag', params.tag);
    }
    if (params?.topic) {
      searchParams.set('topic', params.topic);
    }
    const query = searchParams.toString();
    const baseUrl = merlinApi.getBaseUrl();
    const response = await fetch(`${baseUrl}/merlin/research/manager/sessions?${query}`, {
      method: 'GET',
      headers: {
        ...this.buildAuthHeaders(params?.apiKey),
      },
    });
    if (!response.ok) {
      throw new Error(`Failed to list research sessions (${response.status})`);
    }
    const payload = await response.json();
    const sessions = Array.isArray(payload?.sessions) ? payload.sessions : [];
    return {
      sessions,
      next_cursor: typeof payload?.next_cursor === 'string' ? payload.next_cursor : null,
    };
  }

  /**
   * Search research manager sessions by objective/content keyword.
   */
  async searchResearchSessions(params: {
    query: string;
    apiKey?: string;
    limit?: number;
    cursor?: string;
    tag?: string;
  }): Promise<ResearchSessionsListResult> {
    const normalizedQuery = params.query.trim();
    if (!normalizedQuery) {
      return {
        sessions: [],
        next_cursor: null,
        query: '',
      };
    }
    const limit = Math.max(1, Math.min(params.limit ?? 20, 200));
    const searchParams = new URLSearchParams();
    searchParams.set('q', normalizedQuery);
    searchParams.set('limit', String(limit));
    if (params.cursor) {
      searchParams.set('cursor', params.cursor);
    }
    if (params.tag) {
      searchParams.set('tag', params.tag);
    }
    const baseUrl = merlinApi.getBaseUrl();
    const response = await fetch(
      `${baseUrl}/merlin/research/manager/search?${searchParams.toString()}`,
      {
        method: 'GET',
        headers: {
          ...this.buildAuthHeaders(params.apiKey),
        },
      }
    );
    if (!response.ok) {
      throw new Error(`Failed to search research sessions (${response.status})`);
    }
    const payload = await response.json();
    const sessions = Array.isArray(payload?.sessions) ? payload.sessions : [];
    return {
      sessions,
      next_cursor: typeof payload?.next_cursor === 'string' ? payload.next_cursor : null,
      query: typeof payload?.query === 'string' ? payload.query : normalizedQuery,
    };
  }

  async getResearchSession(
    sessionId: string,
    apiKey?: string
  ): Promise<ResearchSessionDetailResult> {
    const normalizedSessionId = sessionId.trim();
    if (!normalizedSessionId) {
      throw new Error('session_id is required');
    }
    const baseUrl = merlinApi.getBaseUrl();
    const response = await fetch(
      `${baseUrl}/merlin/research/manager/session/${encodeURIComponent(normalizedSessionId)}`,
      {
        method: 'GET',
        headers: {
          ...this.buildAuthHeaders(apiKey),
        },
      }
    );
    if (!response.ok) {
      throw new Error(`Failed to fetch research session (${response.status})`);
    }
    const payload = await response.json();
    return {
      session:
        payload && typeof payload.session === 'object' && payload.session !== null
          ? payload.session
          : {},
    };
  }

  async getResearchSessionBrief(
    sessionId: string,
    apiKey?: string
  ): Promise<ResearchSessionBriefResult> {
    const normalizedSessionId = sessionId.trim();
    if (!normalizedSessionId) {
      throw new Error('session_id is required');
    }
    const baseUrl = merlinApi.getBaseUrl();
    const response = await fetch(
      `${baseUrl}/merlin/research/manager/session/${encodeURIComponent(normalizedSessionId)}/brief`,
      {
        method: 'GET',
        headers: {
          ...this.buildAuthHeaders(apiKey),
        },
      }
    );
    if (!response.ok) {
      throw new Error(`Failed to fetch research brief (${response.status})`);
    }
    const payload = await response.json();
    return {
      brief:
        payload && typeof payload.brief === 'object' && payload.brief !== null
          ? payload.brief
          : {},
    };
  }
}

export const onboardingService = new OnboardingService();
