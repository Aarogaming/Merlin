# Merlin Frontend Dashboard

A modern, responsive frontend for Merlin's multi-model LLM dashboard, built with Tauri, React, and TypeScript.

## 🚀 AAS-228/229/230 Implementation Status

### ✅ AAS-228: Frontend Framework Setup
- **Tauri-based desktop application** with native performance
- **React 18** with TypeScript for type safety
- **Vite** for fast development and building
- **Tailwind CSS** for modern, responsive styling
- **Framer Motion** for smooth animations

### ✅ AAS-229: API Integration  
- **Real-time WebSocket connection** for live metrics
- **RESTful API client** with fallback HTTP support
- **Zustand** for efficient state management
- **React Query** for server state management
- **Error handling** and reconnection logic

### ✅ AAS-230: UI Components
- **Dashboard with real-time metrics** visualization
- **Model performance cards** with detailed statistics
- **Interactive charts** using Recharts library
- **Responsive design** for mobile and desktop
- **Settings page** for customization
- **Model detail pages** with historical data

## 🛠 Tech Stack

### Core Framework
- **Tauri** - Lightweight, secure desktop app framework
- **React 18** - Modern UI library with hooks
- **TypeScript** - Type-safe development
- **Vite** - Fast build tool and dev server

### UI & Styling
- **Tailwind CSS** - Utility-first CSS framework
- **Framer Motion** - Animation library
- **Lucide React** - Modern icon library
- **Custom CSS** with glassmorphism effects

### State & Data
- **Zustand** - Lightweight state management
- **React Query** - Server state synchronization
- **Recharts** - Data visualization library

### Development Tools
- **ESLint** - Code linting and formatting
- **PostCSS** - CSS processing
- **Hot Module Replacement** - Fast development

## 📁 Project Structure

```
frontend/
├── src/                          # Source code
│   ├── components/               # Reusable UI components
│   │   ├── Layout.tsx           # Main app layout with sidebar
│   │   ├── MetricCard.tsx       # Dashboard metric cards
│   │   ├── ModelPerformanceGrid.tsx # Model performance display
│   │   └── ConnectionStatus.tsx # Connection indicator
│   ├── pages/                    # Page components
│   │   ├── Dashboard.tsx        # Main dashboard page
│   │   ├── ModelDetails.tsx     # Individual model details
│   │   └── Settings.tsx         # Application settings
│   ├── services/                 # API services
│   │   └── api.ts               # Merlin API integration
│   ├── store/                    # State management
│   │   └── dashboard.ts         # Zustand store
│   ├── types/                    # TypeScript types
│   │   └── index.ts             # Type definitions
│   ├── utils/                    # Utility functions
│   ├── hooks/                    # Custom React hooks
│   ├── App.tsx                   # Main app component
│   ├── main.jsx                  # App entry point
│   └── index.css                 # Global styles
├── src-tauri/                    # Tauri backend
│   ├── src/
│   │   └── main.rs              # Rust backend code
│   ├── Cargo.toml               # Rust dependencies
│   └── tauri.conf.json          # Tauri configuration
├── public/                       # Static assets
├── package.json                  # Node.js dependencies
├── vite.config.js               # Vite configuration
├── tailwind.config.js           # Tailwind CSS config
├── tsconfig.json                # TypeScript config
└── README.md                    # This file
```

## 🚀 Getting Started

### Prerequisites

1. **Node.js 18+** and npm
2. **Rust** and Cargo
3. **Tauri CLI**

```bash
# Install Node.js from https://nodejs.org
# Install Rust from https://rustup.rs/

# Install Tauri CLI
npm install -g @tauri-apps/cli

# Or install locally
npm install --save-dev @tauri-apps/cli
```

### Installation

1. **Navigate to the frontend directory:**
```bash
cd "AaroneousAutomationSuite/Merlin/frontend"
```

2. **Install dependencies:**
```bash
npm install
```

3. **Start development server:**
```bash
npm run tauri:dev
```

This will start both the Vite dev server and Tauri application in development mode.

### Available Scripts

- `npm run dev` - Start Vite development server (web only)
- `npm run tauri:dev` - Start Tauri development app
- `npm run build` - Build for web
- `npm run tauri:build` - Build desktop application
- `npm run lint` - Run ESLint
- `npm run lint:fix` - Fix linting issues
- `npm run typecheck` - Run TypeScript type checking

## 🔧 Configuration

### API Connection

The frontend automatically connects to the Merlin backend. You can configure the API URL:

```typescript
// In src/services/api.ts
const api = new MerlinApiService('http://localhost:8000');
```

### WebSocket Integration

Real-time updates are handled through WebSocket connections to `/ws/dashboard`. The frontend includes:

- Automatic reconnection
- Error handling
- Fallback to HTTP polling
- Connection status indicators

### Settings Configuration

Dashboard settings are persisted to localStorage and include:

- **Refresh Interval** - How often to fetch new data
- **Theme** - Light/dark/auto theme switching
- **Notifications** - Threshold-based alerts
- **Charts** - Data visualization preferences

## 🎨 Features

### Real-time Dashboard
- Live metrics from multiple LLM models
- Performance charts and visualizations
- Request distribution analytics
- Model comparison and ranking

### Model Performance
- Individual model statistics
- Historical performance data
- Success rate and latency tracking
- User rating integration

### Responsive Design
- Mobile-friendly interface
- Collapsible sidebar
- Adaptive layouts
- Touch support

### Desktop Integration
- Native window controls
- System notifications
- File system access
- Cross-platform support

## 🔌 API Integration

### WebSocket Events

```typescript
// Dashboard status updates
{
  "type": "status",
  "timestamp": "2024-01-01T00:00:00Z",
  "strategy": "adaptive",
  "learning_mode": true,
  "models": { ... },
  "summary": { ... }
}
```

### REST Endpoints

- `GET /api/dashboard/status` - Get current dashboard status
- `POST /api/chat` - Send requests to specific models
- `GET /api/models` - List available models

## 🎯 Key Features

### Enhanced Visualization
- **Interactive Charts**: Bar charts for latency, line charts for trends
- **Real-time Updates**: WebSocket-based live data streaming
- **Performance Metrics**: Success rates, latency, request counts
- **Model Comparison**: Side-by-side performance analysis

### User Experience
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Dark Theme**: Easy on the eyes for extended use
- **Animations**: Smooth transitions and micro-interactions
- **Accessibility**: Keyboard navigation and screen reader support

### Developer Experience
- **TypeScript**: Full type safety and IntelliSense
- **Hot Reload**: Fast development iteration
- **Component Architecture**: Reusable, maintainable code
- **Modern Tooling**: Vite, ESLint, Prettier integration

## 🚀 Deployment

### Development
```bash
npm run tauri:dev
```

### Production Build
```bash
npm run tauri:build
```

This creates platform-specific installers in `src-tauri/target/release/bundle/`.

### Web Deployment
```bash
npm run build
# Deploy the 'dist' folder to your web server
```

## 🤝 Contributing

1. Follow the existing code style and patterns
2. Use TypeScript for type safety
3. Test on multiple screen sizes
4. Ensure accessibility standards
5. Document new components and features

## 📝 License

MIT License - see LICENSE file for details.

---

**Note**: This frontend is designed to work with Merlin's existing backend API and WebSocket endpoints. Ensure the backend is running on the configured port for full functionality.