# Frontend - IT BOM Creation System

React-based frontend for the IT BOM Creation System. Unified application with both BOM chatbot creation and analytics dashboard.

## Tech Stack

- **React 18** - UI framework
- **Vite** - Build tool and dev server
- **Material-UI (MUI)** - Component library
- **Redux Toolkit** - State management
- **React Query** - Server state management
- **React Router** - Navigation
- **Chart.js** - Data visualization
- **Socket.io Client** - Real-time chat
- **Axios** - HTTP client

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── Layout.jsx              # Main layout with sidebar
│   │   └── chat/
│   │       ├── ChatWindow.jsx      # Chat interface
│   │       └── BOMPreview.jsx      # Live BOM preview
│   ├── pages/
│   │   ├── ChatPage.jsx            # BOM creation chat
│   │   ├── DashboardPage.jsx       # Analytics dashboard
│   │   ├── BOMLibraryPage.jsx      # Saved BOMs
│   │   ├── BOMReviewPage.jsx       # BOM detail view
│   │   └── AnalyticsPage.jsx       # Advanced analytics
│   ├── services/
│   │   ├── api.js                  # Axios client
│   │   └── bomApi.js               # API functions
│   ├── store/
│   │   ├── index.js                # Redux store
│   │   └── slices/
│   │       ├── authSlice.js        # Auth state
│   │       ├── chatSlice.js        # Chat state
│   │       ├── bomSlice.js         # BOM state
│   │       └── uiSlice.js          # UI state
│   ├── App.jsx                     # Main app with routing
│   ├── main.jsx                    # Entry point
│   ├── theme.js                    # MUI theme
│   └── index.css                   # Global styles
├── index.html
├── vite.config.js
└── package.json
```

## Getting Started

### Prerequisites

- Node.js 18+ and npm

### Installation

1. **Install dependencies:**
   ```bash
   cd frontend
   npm install
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   ```

3. **Start the development server:**
   ```bash
   npm run dev
   ```

   The app will run at http://localhost:5173

4. **Make sure the backend is running:**
   ```bash
   # In a separate terminal, from project root
   cd backend
   python main.py
   ```
   Backend should be running at http://localhost:8000

## Features

### BOM Chatbot (Chat Page)
- Category selection (Data Center, SD-WAN, Cloud, etc.)
- Conversational BOM creation with 5 questions
- Real-time BOM preview as you answer
- Export to Excel (coming soon)

### Analytics Dashboard
- KPI cards (Total Spend, BOMs Created, Avg Time, Vendors)
- Spending by Category (Pie Chart)
- Vendor Comparison (Bar Chart)
- Spending Trend (Line Chart)

### Navigation
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
