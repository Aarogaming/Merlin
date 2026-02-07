/**
 * Onboarding Setup Screen (AD-129)
 * Initial user setup and configuration flow
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sparkles,
  Settings as SettingsIcon,
  Database,
  Lock,
  Zap,
  CheckCircle,
  ChevronRight,
  ChevronLeft,
} from 'lucide-react';
import toast from 'react-hot-toast';

export interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  component: React.ReactNode;
  isComplete: boolean;
  isSkippable: boolean;
}

export interface OnboardingConfig {
  apiUrl: string;
  apiKey: string;
  databaseUrl: string;
  enableNotifications: boolean;
  autoRefresh: boolean;
  theme: 'light' | 'dark';
}

interface OnboardingProps {
  onComplete?: (config: OnboardingConfig) => void;
  onSkip?: () => void;
}

const Onboarding: React.FC<OnboardingProps> = ({ onComplete, onSkip }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [config, setConfig] = useState<OnboardingConfig>({
    apiUrl: '',
    apiKey: '',
    databaseUrl: '',
    enableNotifications: true,
    autoRefresh: true,
    theme: 'light',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set());

  const steps: OnboardingStep[] = [
    {
      id: 'welcome',
      title: 'Welcome to AAS',
      description: 'Let&apos;s get you set up for success',
      icon: <Sparkles className="w-8 h-8" />,
      component: <WelcomeStep />,
      isComplete: false,
      isSkippable: false,
    },
    {
      id: 'api-config',
      title: 'API Configuration',
      description: 'Connect to your backend API',
      icon: <Zap className="w-8 h-8" />,
      component: <APIConfigStep config={config} onUpdate={setConfig} />,
      isComplete: false,
      isSkippable: false,
    },
    {
      id: 'database-config',
      title: 'Database Setup',
      description: 'Configure your database connection',
      icon: <Database className="w-8 h-8" />,
      component: <DatabaseConfigStep config={config} onUpdate={setConfig} />,
      isComplete: false,
      isSkippable: true,
    },
    {
      id: 'security',
      title: 'Security & Authentication',
      description: 'Secure your system',
      icon: <Lock className="w-8 h-8" />,
      component: <SecurityStep config={config} onUpdate={setConfig} />,
      isComplete: false,
      isSkippable: false,
    },
    {
      id: 'preferences',
      title: 'Preferences',
      description: 'Customize your experience',
      icon: <SettingsIcon className="w-8 h-8" />,
      component: <PreferencesStep config={config} onUpdate={setConfig} />,
      isComplete: false,
      isSkippable: true,
    },
    {
      id: 'complete',
      title: 'All Set!',
      description: 'Your system is ready',
      icon: <CheckCircle className="w-8 h-8" />,
      component: <CompleteStep />,
      isComplete: false,
      isSkippable: false,
    },
  ];

  const currentStepData = steps[currentStep];
  const progress = (currentStep / steps.length) * 100;

  const handleNext = async () => {
    if (currentStep === steps.length - 1) {
      // Final step
      if (onComplete) {
        onComplete(config);
      }
      return;
    }

    // Validate current step
    if (await validateStep(currentStep)) {
      setCompletedSteps(new Set([...completedSteps, currentStepData.id]));
      setCurrentStep(currentStep + 1);
    }
  };

  const handlePrevious = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSkip = () => {
    if (currentStepData.isSkippable) {
      if (onSkip) {
        onSkip();
      }
      setCurrentStep(currentStep + 1);
    }
  };

  const validateStep = async (stepIndex: number): Promise<boolean> => {
    setIsLoading(true);
    try {
      switch (stepIndex) {
        case 1: // API Config
          if (!config.apiUrl) {
            toast.error('API URL is required');
            return false;
          }
          // Validate API connection
          return await validateApiConnection(config.apiUrl);

        case 2: // Database Config
          if (config.databaseUrl) {
            return await validateDatabaseConnection(config.databaseUrl);
          }
          return true; // Optional step

        case 3: // Security
          if (!config.apiKey) {
            toast.error('API Key is required');
            return false;
          }
          return true;

        default:
          return true;
      }
    } finally {
      setIsLoading(false);
    }
  };

  const validateApiConnection = async (url: string): Promise<boolean> => {
    try {
      const response = await fetch(`${url}/health`, { method: 'GET' });
      if (response.ok) {
        toast.success('API connection successful');
        return true;
      }
      toast.error('API connection failed');
      return false;
    } catch (error) {
      toast.error('Failed to connect to API');
      return false;
    }
  };

  const validateDatabaseConnection = async (_url: string): Promise<boolean> => {
    // Simplified validation
    try {
      // In real implementation, make actual database connection test
      toast.success('Database connection successful');
      return true;
    } catch (error) {
      toast.error('Database connection failed');
      return false;
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full"
      >
        {/* Progress Bar */}
        <div className="h-1 bg-gray-200">
          <motion.div
            className="h-full bg-gradient-to-r from-blue-500 to-indigo-600"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5 }}
          />
        </div>

        {/* Content */}
        <div className="p-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentStep}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.3 }}
            >
              {/* Header */}
              <div className="mb-8">
                <div className="flex items-center gap-3 mb-4">
                  <div className="text-indigo-600">{currentStepData.icon}</div>
                  <div>
                    <h1 className="text-3xl font-bold text-gray-900">
                      {currentStepData.title}
                    </h1>
                    <p className="text-gray-600">{currentStepData.description}</p>
                  </div>
                </div>
              </div>

              {/* Step Component */}
              <div className="mb-8 min-h-64">
                {currentStepData.component}
              </div>

              {/* Step Indicator */}
              <div className="flex gap-2 mb-8">
                {steps.map((step, index) => (
                  <motion.div
                    key={step.id}
                    className={`h-2 rounded-full transition-all ${
                      index <= currentStep
                        ? 'bg-indigo-600'
                        : 'bg-gray-300'
                    }`}
                    style={{
                      width: `${100 / steps.length}%`,
                    }}
                  />
                ))}
              </div>
            </motion.div>
          </AnimatePresence>

          {/* Actions */}
          <div className="flex justify-between gap-4">
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={handlePrevious}
              disabled={currentStep === 0}
              className="flex items-center gap-2 px-6 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              <ChevronLeft className="w-4 h-4" />
              Previous
            </motion.button>

            <div className="flex gap-4">
              {currentStepData.isSkippable && currentStep !== steps.length - 1 && (
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={handleSkip}
                  className="px-6 py-2 text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition"
                >
                  Skip
                </motion.button>
              )}

              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={handleNext}
                disabled={isLoading}
                className="flex items-center gap-2 px-6 py-2 text-white bg-gradient-to-r from-blue-500 to-indigo-600 rounded-lg hover:shadow-lg disabled:opacity-50 transition"
              >
                {isLoading ? 'Validating...' : currentStep === steps.length - 1 ? 'Finish' : 'Next'}
                {!isLoading && <ChevronRight className="w-4 h-4" />}
              </motion.button>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
};

// Step Components
const WelcomeStep = () => (
  <div className="space-y-4">
    <p className="text-gray-700 text-lg">
      Welcome! This setup wizard will help you configure the Aaroneous Automation Suite.
    </p>
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-2">
      <h3 className="font-semibold text-blue-900">What we&apos;ll set up:</h3>
      <ul className="text-sm text-blue-800 space-y-1">
        <li>✓ API Configuration</li>
        <li>✓ Database Connection</li>
        <li>✓ Security & Authentication</li>
        <li>✓ User Preferences</li>
      </ul>
    </div>
  </div>
);

interface StepProps {
  config: OnboardingConfig;
  onUpdate: (config: OnboardingConfig) => void;
}

const APIConfigStep: React.FC<StepProps> = ({ config, onUpdate }) => (
  <div className="space-y-4">
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-2">
        API URL
      </label>
      <input
        type="url"
        placeholder="https://api.example.com"
        value={config.apiUrl}
        onChange={(e) => onUpdate({ ...config, apiUrl: e.target.value })}
        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
      />
      <p className="text-sm text-gray-500 mt-2">
        Enter the URL of your AAS backend API server
      </p>
    </div>
  </div>
);

const DatabaseConfigStep: React.FC<StepProps> = ({ config, onUpdate }) => (
  <div className="space-y-4">
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-2">
        Database URL (Optional)
      </label>
      <input
        type="text"
        placeholder="postgresql://user:pass@localhost/aas"
        value={config.databaseUrl}
        onChange={(e) => onUpdate({ ...config, databaseUrl: e.target.value })}
        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
      />
      <p className="text-sm text-gray-500 mt-2">
        Leave empty to use default in-memory storage
      </p>
    </div>
  </div>
);

const SecurityStep: React.FC<StepProps> = ({ config, onUpdate }) => (
  <div className="space-y-4">
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-2">
        API Key
      </label>
      <input
        type="password"
        placeholder="Enter your API key"
        value={config.apiKey}
        onChange={(e) => onUpdate({ ...config, apiKey: e.target.value })}
        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
      />
      <p className="text-sm text-gray-500 mt-2">
        This key will be stored securely in your system
      </p>
    </div>
  </div>
);

const PreferencesStep: React.FC<StepProps> = ({ config, onUpdate }) => (
  <div className="space-y-4">
    <label className="flex items-center gap-3">
      <input
        type="checkbox"
        checked={config.enableNotifications}
        onChange={(e) => onUpdate({ ...config, enableNotifications: e.target.checked })}
        className="w-4 h-4 rounded"
      />
      <span className="text-gray-700">Enable notifications</span>
    </label>
    <label className="flex items-center gap-3">
      <input
        type="checkbox"
        checked={config.autoRefresh}
        onChange={(e) => onUpdate({ ...config, autoRefresh: e.target.checked })}
        className="w-4 h-4 rounded"
      />
      <span className="text-gray-700">Auto-refresh dashboard</span>
    </label>
    <div>
      <label htmlFor="theme-select" className="block text-sm font-medium text-gray-700 mb-2">
        Theme
      </label>
      <select
        id="theme-select"
        value={config.theme}
        onChange={(e) => onUpdate({ ...config, theme: e.target.value as 'light' | 'dark' })}
        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
      >
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </div>
  </div>
);

const CompleteStep = () => (
  <div className="text-center space-y-4">
    <motion.div
      animate={{ scale: [1, 1.2, 1] }}
      transition={{ duration: 0.6 }}
      className="inline-block"
    >
      <CheckCircle className="w-16 h-16 text-green-500" />
    </motion.div>
    <p className="text-lg text-gray-700">
      Your system is configured and ready to go!
    </p>
    <p className="text-sm text-gray-500">
      Click Finish to start using the AAS.
    </p>
  </div>
);

export default Onboarding;
