# Frontend - IT BOM Creation System

React-based web application providing an intuitive interface for AI-powered BOM creation, analytics, and management.

## 📋 Table of Contents
- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Setup & Installation](#setup--installation)
- [Features](#features)
- [Development](#development)
- [Build & Deployment](#build--deployment)
- [Configuration](#configuration)

## 🏗️ Architecture

The frontend follows a modern React architecture with Redux Toolkit for state management:

```
┌─────────────────────────────────────────┐
│         React Components Layer          │
│     (Pages, UI Components, Layout)      │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│      Redux Toolkit State Layer          │
│  (auth, chat, bom, ui, analytics)      │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│       Services Layer (API)              │
│  (Axios interceptors, API wrappers)    │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│         Backend REST API                │
│     (FastAPI @ localhost:8001)         │
└─────────────────────────────────────────┘
```

### Tech Stack
- **Framework**: React 18.2 with Vite 5
- **UI Library**: Material-UI (MUI) v5
- **State Management**: Redux Toolkit + React Query
- **Routing**: React Router v6
- **Styling**: Emotion (CSS-in-JS)
- **Charts**: Chart.js + react-chartjs-2
- **HTTP Client**: Axios
- **Dev Server**: Vite (HMR)

## 📂 Directory Structure

```
frontend/
├── src/
│   ├── components/              # Reusable UI components
│   │   ├── BOMPreview.jsx       # Real-time BOM preview panel
│   │   ├── CategoryCard.jsx     # BOM category selector cards
│   │   ├── ChatWindow.jsx       # Chat interface with message bubbles
│   │   ├── Layout.jsx           # Main app layout with sidebar
│   │   ├── Navigation.jsx       # Sidebar navigation
│   │   └── ProgressBar.jsx      # Phase progress indicator
│   ├── pages/                   # Page-level components
│   │   ├── ChatPage.jsx         # Main BOM creation chat interface
│   │   ├── OverviewPage.jsx     # Analytics dashboard
│   │   ├── BOMLibraryPage.jsx   # BOM library with search/filter
│   │   ├── VendorPriceSelectorPage.jsx  # Catalog browser
│   │   ├── RFQBuilderPage.jsx   # RFQ cart and export
│   │   ├── QuoteExtractorPage.jsx  # Upload vendor quotes
│   │   └── BOMReviewPage.jsx    # 3-party approval workflow
│   ├── services/                # API layer
│   │   ├── api.js               # Axios instance + interceptors
│   │   ├── bomApi.js            # BOM CRUD operations
│   │   ├── chatApi.js           # Chat/streaming API
│   │   └── analyticsApi.js      # Analytics queries
│   ├── store/                   # Redux state management
│   │   ├── index.js             # Store configuration
│   │   └── slices/
│   │       ├── authSlice.js     # Authentication state
│   │       ├── chatSlice.js     # Chat session state
│   │       ├── bomSlice.js      # BOM data state
│   │       ├── uiSlice.js       # UI state (sidebar, modals)
│   │       └── analyticsSlice.js  # Analytics data cache
│   ├── theme/                   # MUI theme customization
│   │   └── theme.js             # Color palette, typography
│   ├── utils/                   # Utility functions
│   │   ├── formatters.js        # Currency, date formatting
│   │   └── validators.js        # Form validation
│   ├── App.jsx                  # Root component with routing
│   ├── main.jsx                 # Entry point
│   └── index.css                # Global styles
├── public/                      # Static assets
│   ├── favicon.ico
│   └── logo.svg
├── index.html                   # HTML template
├── package.json                 # Dependencies
├── vite.config.js               # Vite configuration
├── nginx.conf                   # Nginx config (for Docker)
├── Dockerfile                   # Docker container definition
└── .env.example                 # Environment variables template
```

## 🚀 Setup & Installation

### Prerequisites
- Node.js 18+ and npm 9+
- Backend server running (see [backend/README.md](../backend/README.md))

### Installation

1. **Install dependencies**:
   ```bash
   cd frontend
   npm install
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with backend URL (see Configuration section)
   ```

3. **Start development server**:
   ```bash
   npm run dev
   
   # Or use the startup script from root
   ..\start-frontend.bat
   ```

4. **Access the application**:
   - Frontend: http://localhost:5173
   - Vite DevTools: http://localhost:5173/__vite_ping

### Quick Start Script
From the project root:
```bash
# Start both frontend and backend
start-all.bat

# Or start just frontend
start-frontend.bat
```

## ✨ Features

### 1. AI-Powered BOM Creation (`ChatPage.jsx`)
- **Category Selection**: Choose from 8+ IT categories (Network, Data Center, SD-WAN, etc.)
- **Conversational Interface**: Chat with AI agent that guides you through BOM creation
- **Phase Progress**: Visual 10-phase progress indicator
- **Real-time BOM Preview**: Right panel shows BOM building in real-time
- **Domain Pre-selection**: Smart defaults for Network categories (Day-1 assumption)
- **Streaming Responses**: SSE-based streaming for immediate AI feedback

**Key Components**:
- `CategoryCard.jsx` - Category selection with icons and descriptions
- `ChatWindow.jsx` - Message bubbles, typing indicators, auto-scroll
- `BOMPreview.jsx` - Live-updating BOM table
- `ProgressBar.jsx` - 10-phase visual progress

### 2. Analytics Dashboard (`OverviewPage.jsx`)
- **KPI Cards**: Total spend, active BOMs, avg cycle time, vendor count
- **Spending Charts**: Bar chart by category, pie chart by vendor
- **Recent BOMs**: Table with status badges and action buttons
- **Live Alerts**: BOM status change notifications (from Redux)
- **Chart.js Integration**: Interactive, responsive visualizations

### 3. BOM Library (`BOMLibraryPage.jsx`)
- **Search & Filter**: Full-text search, status filter, category filter
- **Inline Editing**: Click-to-edit cells with validation
- **BOM Comparison**: Select 2+ BOMs to compare side-by-side
- **Approval Status**: Visual badges (Draft, Pending, Approved)
- **Bulk Actions**: Export multiple BOMs to CSV/Excel
- **Version History**: Track all BOM revisions

### 4. Vendor Price Selector (`VendorPriceSelectorPage.jsx`)
- **Catalog Browser**: Search 48+ services across 6 categories
- **Category Filters**: Compute, Storage, Network, Security, Cloud, Licenses
- **Add to BOM**: One-click add items to active BOM
- **Price Display**: Unit price, term (monthly/one-time), vendor
- **Shopping Cart**: Review selections before adding to BOM

### 5. RFQ Builder (`RFQBuilderPage.jsx`)
- **Cart System**: Add/remove items, update quantities
- **Pre-populate**: Load items from active BOM
- **CSV Export**: Generate vendor-ready RFQ file
- **Email Draft**: Generate email body for vendor submission
- **Vendor Selection**: Choose target vendor from dropdown

### 6. Quote Extractor (`QuoteExtractorPage.jsx`)
- **File Upload**: Drag-and-drop or click to upload vendor quotes
- **Format Detection**: Auto-detect CSV, JSON, Excel formats
- **Intelligent Parsing**: Extract line items, prices, SKUs
- **Confidence Scoring**: AI-based extraction confidence (High/Medium/Low)
- **Map to BOM**: Match extracted items to existing BOM structure

### 7. BOM Review (`BOMReviewPage.jsx`)
- **3-Party Approval**: Buyer IT, Seller IT, SI sign-off workflow
- **Approval Status**: Visual padlock until all 3 approved
- **Comments**: Reviewers can add comments per approval
- **Audit Trail**: Who approved when, full history
- **Export Lock**: BOM cannot be exported until fully approved

## 🛠️ Development

### Running Development Server
```bash
npm run dev          # Start with HMR at http://localhost:5173
npm run dev -- --host  # Expose to network (useful for mobile testing)
```

### Building for Production
```bash
npm run build        # Build optimized production bundle → dist/
npm run preview      # Preview production build locally
```

### Code Quality
```bash
# Linting
npm run lint         # ESLint check
npm run lint:fix     # Auto-fix linting issues

# Type checking (if using TypeScript)
npm run type-check

# Format code
npm run format       # Prettier
```

### Testing
```bash
# Unit tests (with Vitest)
npm test

# E2E tests (with Playwright)
npm run test:e2e

# Coverage
npm run test:coverage
```

### Development Tools

**Redux DevTools**:
Install [Redux DevTools Extension](https://github.com/reduxjs/redux-devtools) to inspect state changes in browser.

**React DevTools**:
Install [React Developer Tools](https://react.dev/learn/react-developer-tools) for component inspection.

**Vite Inspector**:
Press `Shift + Option + C` (Mac) or `Shift + Alt + C` (Windows) to inspect components.

## 🐳 Build & Deployment

### Docker Build & Run

**Build image**:
```bash
docker build -t vc-frontend:v9 -f frontend/Dockerfile frontend/
```

**Run container**:
```bash
docker run -p 80:80 \
  -e VITE_API_URL=https://api.example.com \
  vc-frontend:v9
```

### Azure Container Apps Deployment

**Build & push to ACR**:
```bash
az acr build \
  --registry <YOUR_ACR_NAME> \
  --image vc-frontend:v9 \
  --file frontend/Dockerfile \
  frontend/
```

**Deploy to Container Apps**:
```bash
az containerapp update \
  --name vc-frontend \
  --resource-group <YOUR_RG> \
  --image <YOUR_ACR_NAME>.azurecr.io/vc-frontend:v9
```

### Static Hosting (Azure Static Web Apps, Netlify, Vercel)

**Build static site**:
```bash
npm run build  # Output → dist/
```

**Deploy to Azure Static Web Apps**:
```bash
az staticwebapp create \
  --name vc-frontend \
  --resource-group <YOUR_RG> \
  --source dist/ \
  --location eastus2
```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the `frontend/` directory:

```env
# Backend API URL (proxied by Vite in dev, hardcoded in nginx for prod)
VITE_API_URL=http://localhost:8001

# Feature flags
VITE_ENABLE_ANALYTICS=true
VITE_ENABLE_MOCK_DATA=false

# Auth (Azure AD B2C)
VITE_AUTH_CLIENT_ID=your-client-id
VITE_AUTH_TENANT=your-tenant.onmicrosoft.com

# Application
VITE_APP_NAME="IT BOM Creation System"
VITE_APP_VERSION=1.0.0
```

### Vite Proxy Configuration (`vite.config.js`)

In development, Vite proxies API requests to avoid CORS:

```javascript
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',  // Backend server
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
});
```

### Nginx Configuration (Production)

For Docker deployment, `nginx.conf` routes API calls:

```nginx
location /api/ {
    resolver 168.63.129.16 valid=30s ipv6=off;
    set $backend "https://vc-backend.proudplant-8cd7e7db.eastus.azurecontainerapps.io";
    proxy_pass $backend;
    proxy_set_header Host vc-backend.proudplant-8cd7e7db.eastus.azurecontainerapps.io;
    proxy_ssl_server_name on;
}
```

## 🎨 Customization

### Theme Customization (`src/theme/theme.js`)

```javascript
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',  // Change primary color
    },
    secondary: {
      main: '#dc004e',  // Change secondary color
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
  },
});
```

### Adding New Routes

1. **Create page component** in `src/pages/`:
   ```javascript
   // src/pages/NewPage.jsx
   export default function NewPage() {
     return <div>New Page Content</div>;
   }
   ```

2. **Register route** in `src/App.jsx`:
   ```javascript
   import NewPage from './pages/NewPage';
   
   <Route path="/new-page" element={<NewPage />} />
   ```

3. **Add navigation link** in `src/components/Navigation.jsx`:
   ```javascript
   <ListItem button component={Link} to="/new-page">
     <ListItemText primary="New Page" />
   </ListItem>
   ```

## 🔍 Troubleshooting

### Common Issues

**1. CORS errors when calling API**
```bash
# Verify backend is running at correct port
# Check vite.config.js proxy configuration
# Ensure backend CORS_ORIGINS includes http://localhost:5173
```

**2. Redux state not persisting**
```bash
# Check redux-persist configuration in src/store/index.js
# Clear browser localStorage if corrupted
localStorage.clear()
```

**3. Build fails with "out of memory"**
```bash
# Increase Node.js memory limit
NODE_OPTIONS=--max-old-space-size=4096 npm run build
```

**4. Hot reload not working**
```bash
# Clear Vite cache
rm -rf node_modules/.vite
npm run dev
```

## 📚 Additional Resources

- [React Documentation](https://react.dev)
- [Material-UI Documentation](https://mui.com)
- [Redux Toolkit Documentation](https://redux-toolkit.js.org)
- [Vite Documentation](https://vitejs.dev)
- [Backend API Documentation](../backend/README.md)
- [Main README](../README.md)

## 🤝 Contributing

See the main [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

## 📄 License

See [LICENSE](../LICENSE) for details.

- Unified sidebar navigation
- Persistent state across pages
- Responsive design

## Development

### Available Scripts

- `npm run dev` - Start dev server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Lint code

### API Proxy

Vite dev server is configured to proxy API requests to the backend:
- `/api/*` → `http://localhost:8000/api/*`
- `/ws/*` → `ws://localhost:8000/ws/*`

### State Management

- **Auth**: User authentication state (placeholder for Azure AD)
- **Chat**: Chat session, messages, context, partial BOM
- **BOM**: Current BOM, BOM list, loading state
- **UI**: Sidebar open/close, theme, notifications

### Dummy Data

Currently using dummy data for:
- Chat responses (simulated AI conversation)
- BOM generation (hardcoded line items)
- Dashboard metrics (static charts)

Once backend API endpoints are ready, these will be replaced with real data fetching.

## Next Steps

1. ✅ Frontend setup complete
2. ⏳ Connect to backend API endpoints (when ready)
3. ⏳ Add WebSocket for real-time chat
4. ⏳ Implement BOM export functionality
5. ⏳ Add Azure AD B2C authentication
6. ⏳ Migrate all chart functionality from vanilla JS

## Notes

- Backend must be running at `http://localhost:8000` for API calls to work
- Feature flags in backend control whether to use real Azure services or dummy data
- Authentication is currently disabled (placeholder for Azure AD integration)
