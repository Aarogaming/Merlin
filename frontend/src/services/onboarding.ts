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

class OnboardingService {
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
}

export const onboardingService = new OnboardingService();
