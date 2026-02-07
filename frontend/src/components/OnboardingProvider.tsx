/**
 * Main App Integration for Onboarding (AD-129)
 * Integration point for onboarding in main App component
 */

import { useEffect, useState } from 'react';
import { useOnboardingStore } from '../store/onboarding';
import { onboardingService } from '../services/onboarding';
import Onboarding from '../pages/Onboarding';
import type { OnboardingConfig } from '../pages/Onboarding';

interface OnboardingIntegrationProps {
  children: React.ReactNode;
}

export const OnboardingProvider: React.FC<OnboardingIntegrationProps> = ({ children }) => {
  const { isCompleted, completeOnboarding } = useOnboardingStore();
  const [onboardingRequired, setOnboardingRequired] = useState<boolean | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const checkOnboarding = async () => {
      try {
        // Check if onboarding is already completed
        if (isCompleted) {
          setOnboardingRequired(false);
          setIsLoading(false);
          return;
        }

        // Check if onboarding is required
        const required = await onboardingService.isOnboardingRequired();
        setOnboardingRequired(required);

        // If not required, try to load existing config
        if (!required) {
          const existingConfig = await onboardingService.getExistingConfiguration();
          if (existingConfig) {
            completeOnboarding();
          }
        }
      } catch (error) {
        console.error('Failed to check onboarding status:', error);
        setOnboardingRequired(true);
      } finally {
        setIsLoading(false);
      }
    };

    checkOnboarding();
  }, [isCompleted, completeOnboarding]);

  const handleOnboardingComplete = async (config: OnboardingConfig) => {
    try {
      // Save configuration
      const result = await onboardingService.saveConfiguration(config);

      if (result.valid) {
        // Store in local state
        const { setConfig } = useOnboardingStore.getState();
        setConfig(config);
        completeOnboarding();
      } else {
        throw new Error(result.error || 'Failed to save configuration');
      }
    } catch (error) {
      console.error('Failed to complete onboarding:', error);
      // Show error toast or notification
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto" />
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (onboardingRequired && !isCompleted) {
    return (
      <Onboarding onComplete={handleOnboardingComplete} />
    );
  }

  return <>{children}</>;
};

export default OnboardingProvider;
