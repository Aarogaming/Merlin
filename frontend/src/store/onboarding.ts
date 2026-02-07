/**
 * Onboarding Store (AD-129)
 * State management for onboarding flow
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface OnboardingState {
  // Configuration
  apiUrl: string;
  apiKey: string;
  databaseUrl: string;
  enableNotifications: boolean;
  autoRefresh: boolean;
  theme: 'light' | 'dark';

  // State
  isCompleted: boolean;
  currentStep: number;
  completedSteps: Set<string>;
  errors: Record<string, string>;
  isValidating: boolean;

  // Actions
  setConfig: (config: Partial<OnboardingState>) => void;
  setCurrentStep: (step: number) => void;
  markStepComplete: (stepId: string) => void;
  setError: (stepId: string, error: string) => void;
  clearError: (stepId: string) => void;
  setIsValidating: (isValidating: boolean) => void;
  completeOnboarding: () => void;
  resetOnboarding: () => void;
}

const initialState = {
  apiUrl: '',
  apiKey: '',
  databaseUrl: '',
  enableNotifications: true,
  autoRefresh: true,
  theme: 'light' as const,
  isCompleted: false,
  currentStep: 0,
  completedSteps: new Set<string>(),
  errors: {},
  isValidating: false,
};

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      ...initialState,

      setConfig: (config) =>
        set((state) => ({
          ...state,
          ...config,
        })),

      setCurrentStep: (step) =>
        set({
          currentStep: step,
        }),

      markStepComplete: (stepId) =>
        set((state) => ({
          completedSteps: new Set([...state.completedSteps, stepId]),
        })),

      setError: (stepId, error) =>
        set((state) => ({
          errors: {
            ...state.errors,
            [stepId]: error,
          },
        })),

      clearError: (stepId) =>
        set((state) => {
          const newErrors = { ...state.errors };
          delete newErrors[stepId];
          return { errors: newErrors };
        }),

      setIsValidating: (isValidating) =>
        set({
          isValidating,
        }),

      completeOnboarding: () =>
        set({
          isCompleted: true,
        }),

      resetOnboarding: () =>
        set(initialState),
    }),
    {
      name: 'onboarding-storage',
      partialize: (state) => ({
        apiUrl: state.apiUrl,
        databaseUrl: state.databaseUrl,
        enableNotifications: state.enableNotifications,
        autoRefresh: state.autoRefresh,
        theme: state.theme,
        isCompleted: state.isCompleted,
      }),
    }
  )
);
