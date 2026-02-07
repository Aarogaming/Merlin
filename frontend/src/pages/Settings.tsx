import { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  Settings as SettingsIcon, 
  RefreshCw, 
  Bell, 
  Database
} from 'lucide-react';
import { useDashboardStore } from '../store/dashboard';
import type { DashboardSettings } from '../types';
import toast from 'react-hot-toast';

type NestedSettingsKey = 'notifications' | 'charts';

const Settings = () => {
  const { settings, setSettings } = useDashboardStore();
  const [isSaving, setIsSaving] = useState(false);

  const handleSettingChange = <K extends keyof DashboardSettings>(
    key: K,
    value: DashboardSettings[K]
  ) => {
    setSettings({
      ...settings,
      [key]: value,
    });
  };

  const handleNestedSettingChange = <
    K extends NestedSettingsKey,
    NK extends keyof DashboardSettings[K]
  >(
    parent: K,
    key: NK,
    value: DashboardSettings[K][NK]
  ) => {
    setSettings({
      ...settings,
      [parent]: {
        ...settings[parent],
        [key]: value,
      },
    });
  };

  const saveSettings = async () => {
    setIsSaving(true);
    try {
      // Simulate saving settings
      await new Promise(resolve => setTimeout(resolve, 1000));
      toast.success('Settings saved successfully');
    } catch (error) {
      toast.error('Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  };

  const resetSettings = () => {
    const defaultSettings: DashboardSettings = {
      refreshInterval: 5000,
      theme: 'dark' as const,
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
    setSettings(defaultSettings);
    toast.success('Settings reset to defaults');
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="space-y-6"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gradient mb-2">Settings</h1>
          <p className="text-dark-muted">Configure your Merlin dashboard experience</p>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={resetSettings}
            className="btn btn-secondary"
          >
            Reset to Defaults
          </button>
          <button
            onClick={saveSettings}
            disabled={isSaving}
            className="btn btn-primary"
          >
            {isSaving ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              'Save Settings'
            )}
          </button>
        </div>
      </div>

      {/* General Settings */}
      <div className="card">
        <div className="flex items-center mb-6">
          <SettingsIcon className="w-6 h-6 text-merlin-blue mr-3" />
          <h2 className="text-xl font-semibold">General Settings</h2>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">
              Refresh Interval (ms)
            </label>
            <input
              type="number"
              min="1000"
              max="60000"
              step="1000"
              value={settings.refreshInterval}
              onChange={(e) => handleSettingChange('refreshInterval', parseInt(e.target.value))}
              className="w-full px-3 py-2 bg-dark-border border border-dark-border rounded-md text-dark-text focus:outline-none focus:ring-2 focus:ring-merlin-blue"
            />
            <p className="text-xs text-dark-muted mt-1">
              How often to refresh dashboard data (1-60 seconds)
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              Theme
            </label>
            <select
              value={settings.theme}
              onChange={(e) => handleSettingChange('theme', e.target.value as DashboardSettings['theme'])}
              className="w-full px-3 py-2 bg-dark-border border border-dark-border rounded-md text-dark-text focus:outline-none focus:ring-2 focus:ring-merlin-blue"
            >
              <option value="light">Light</option>
              <option value="dark">Dark</option>
              <option value="auto">Auto</option>
            </select>
          </div>
        </div>
      </div>

      {/* Notification Settings */}
      <div className="card">
        <div className="flex items-center mb-6">
          <Bell className="w-6 h-6 text-merlin-green mr-3" />
          <h2 className="text-xl font-semibold">Notifications</h2>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium">
              Enable Notifications
            </label>
            <button
              onClick={() => handleNestedSettingChange('notifications', 'enabled', !settings.notifications.enabled)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                settings.notifications.enabled ? 'bg-merlin-blue' : 'bg-dark-border'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  settings.notifications.enabled ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          {settings.notifications.enabled && (
            <>
              <div>
                <label className="block text-sm font-medium mb-2">
                  Success Rate Threshold (%)
                </label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="5"
                  value={(settings.notifications.thresholds.success_rate * 100).toFixed(0)}
                  onChange={(e) => handleNestedSettingChange('notifications', 'thresholds', {
                    ...settings.notifications.thresholds,
                    success_rate: parseInt(e.target.value) / 100,
                  })}
                  className="w-full px-3 py-2 bg-dark-border border border-dark-border rounded-md text-dark-text focus:outline-none focus:ring-2 focus:ring-merlin-blue"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">
                  Latency Threshold (seconds)
                </label>
                <input
                  type="number"
                  min="0.1"
                  max="10"
                  step="0.1"
                  value={settings.notifications.thresholds.latency}
                  onChange={(e) => handleNestedSettingChange('notifications', 'thresholds', {
                    ...settings.notifications.thresholds,
                    latency: parseFloat(e.target.value),
                  })}
                  className="w-full px-3 py-2 bg-dark-border border border-dark-border rounded-md text-dark-text focus:outline-none focus:ring-2 focus:ring-merlin-blue"
                />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Chart Settings */}
      <div className="card">
        <div className="flex items-center mb-6">
          <Database className="w-6 h-6 text-merlin-purple mr-3" />
          <h2 className="text-xl font-semibold">Charts & Data</h2>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium">
              Real-time Updates
            </label>
            <button
              onClick={() => handleNestedSettingChange('charts', 'realTimeUpdates', !settings.charts.realTimeUpdates)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                settings.charts.realTimeUpdates ? 'bg-merlin-blue' : 'bg-dark-border'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  settings.charts.realTimeUpdates ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <div className="flex items-center justify-between">
            <label className="text-sm font-medium">
              Show Historical Data
            </label>
            <button
              onClick={() => handleNestedSettingChange('charts', 'showHistoricalData', !settings.charts.showHistoricalData)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                settings.charts.showHistoricalData ? 'bg-merlin-blue' : 'bg-dark-border'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  settings.charts.showHistoricalData ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              Data Points to Display
            </label>
            <input
              type="number"
              min="10"
              max="200"
              step="10"
              value={settings.charts.dataPoints}
              onChange={(e) => handleNestedSettingChange('charts', 'dataPoints', parseInt(e.target.value))}
              className="w-full px-3 py-2 bg-dark-border border border-dark-border rounded-md text-dark-text focus:outline-none focus:ring-2 focus:ring-merlin-blue"
            />
            <p className="text-xs text-dark-muted mt-1">
              Number of data points to show in historical charts
            </p>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default Settings;
