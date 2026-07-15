# IT BOM Creation System

AI-powered Bill of Materials (BOM) creation assistant and analytics dashboard for IT infrastructure projects.

## 🎯 Overview

This system helps IT teams:
- **Create BOMs in 15 minutes** (vs 2 hours manually) using AI-powered chat interface
- **Analyze spending patterns** from historical quotes
- **Generate vendor-ready exports** in Excel/PDF format
- **Learn from past projects** to suggest optimizations
- **Reduce vendor quote delays** from 2 weeks to 2-3 days

## 🏗️ Architecture

### Tech Stack
- **Frontend**: React 18, Vite, Redux Toolkit, Material-UI, Chart.js, React Router
- **Backend**: Python FastAPI, LangChain/LangGraph, Pydantic
- **AI**: Anthropic Claude (Sonnet, Opus, Haiku models)
- **Database**: Azure Cosmos DB (NoSQL) with local mock for development
- **Storage**: Azure Data Lake Storage Gen2 with local filesystem mock
- **Document Repo**: SharePoint Online (pending setup)
- **Auth**: Azure AD B2C (planned)

### Key Components
1. **Chat-based BOM Builder**: AI agents ask questions, generate complete BOMs
2. **Analytics Dashboard**: Spending insights, vendor performance, pattern analysis
3. **BOM Library**: Version control, templates, search
4. **SharePoint Integration**: Sync historical BOMs, push generated BOMs
5. **Export Engine**: Excel/PDF in client-specific formats

## 📂 Project Structure

```
it-contracting-dashboard/
├── backend/                    # Python FastAPI backend
│   ├── ai/                    # AI agents and LLM integration (TODO)
│   ├── api/                   # REST API endpoints (TODO)
│   ├── db/                    # Database clients and schemas ✓
│   │   ├── cosmos_client.py   # Real Cosmos DB operations ✓
│   │   ├── adls_client.py     # Real Azure Storage operations ✓
│   │   ├── mock_cosmos_client.py # Local dev mock ✓
│   │   ├── mock_adls_client.py   # Local dev mock ✓
│   │   └── schemas.py         # Pydantic data models ✓
│   ├── services/              # Business logic services (TODO)
│   ├── config.py              # Configuration with feature flags ✓
│   ├── main.py                # FastAPI application ✓
│   ├── requirements.txt       # Python dependencies ✓
│   └── .env.example           # Environment template ✓
├── frontend/                   # React frontend ✓
│   ├── src/
│   │   ├── components/        # Reusable components ✓
│   │   ├── pages/             # Page components ✓
│   │   ├── services/          # API layer ✓
│   │   ├── store/             # Redux state management ✓
│   │   ├── App.jsx            # Main app with routing ✓
│   │   └── main.jsx           # Entry point ✓
│   ├── package.json           # Dependencies ✓
│   └── vite.config.js         # Vite configuration ✓
├── extractor/                  # BOM extraction and analysis ✓
├── quotes/                     # Sample vendor quotes ✓
├── Colo_BOM_Rev5.xlsx         # Client BOM example ✓
├── Data Center BoM - Honeywell (1).xlsx  # Client BOM example ✓
├── catalog_data.json          # Historical BOM data ✓
├── IMPLEMENTATION_PLAN.md     # Detailed implementation roadmap ✓
└── README.md                  # This file ✓
```

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Node.js 18+ and npm
- Azure subscription (optional - can use dummy data for local dev)
- Anthropic API key (optional - can use dummy responses for local dev)

### Quick Start (Local Development with Dummy Data)

The easiest way to get started is using the included startup scripts with dummy data (no Azure setup needed):

**Option 1: Using startup scripts**
```bash
# Terminal 1 - Start Backend
start-backend.bat

# Terminal 2 - Start Frontend
start-frontend.bat
```

**Option 2: Manual start**

1. **Backend Setup**:
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
cp .env.example .env
# Edit .env: Set USE_DUMMY_COSMOS=True, USE_DUMMY_ADLS=True
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. **Frontend Setup**:
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

3. **Access the application**:
- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Feature Flags (Local Development)

In `backend/.env`, set these flags to use dummy data:
```env
USE_DUMMY_COSMOS=True    # Use in-memory mock instead of real Cosmos DB
USE_DUMMY_ADLS=True      # Use local filesystem instead of Azure Storage
USE_DUMMY_SHAREPOINT=True # Skip SharePoint integration
USE_DUMMY_CLAUDE=False   # Set to True to use dummy AI responses (no API key needed)
```

### Production Setup (with Azure)

For production deployment, you'll need:

1. **Azure Resources**:
   - Cosmos DB account
   - Storage Account (ADLS Gen2)
   - Key Vault
   - Azure AD B2C tenant

2. **Backend Configuration** (`backend/.env`):
```env
# Set all USE_DUMMY_* flags to False
USE_DUMMY_COSMOS=False
USE_DUMMY_ADLS=False
USE_DUMMY_SHAREPOINT=False
USE_DUMMY_CLAUDE=False

# Add your Azure credentials
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
ADLS_ACCOUNT_NAME=your-storage-account
ADLS_ACCOUNT_KEY=your-storage-key
ANTHROPIC_API_KEY=your-anthropic-key
# ... etc
```

## 📊 Current Progress

### ✅ Completed (Phase 0.1 - Foundation & Phase 0.2 - Dummy Data Support)
- [x] Analyzed client BOMs (Colo_BOM_Rev5 $3.6M, Honeywell $1.2M)
- [x] Created comprehensive 107-task implementation plan
- [x] Set up backend project structure
- [x] Created configuration management with feature flags
- [x] Defined complete database schemas (Pydantic models for BOM, Chat, User, etc.)
- [x] Built Cosmos DB client with CRUD operations
- [x] Built ADLS client for file storage
- [x] Built mock Cosmos DB client (in-memory dict storage)
- [x] Built mock ADLS client (local filesystem)
- [x] Smart client getters with feature flag switching
- [x] Set up FastAPI application with health checks
- [x] **React frontend setup with Vite**
- [x] **Redux state management (auth, chat, bom, ui slices)**
- [x] **Material-UI components and theme**
- [x] **Unified app navigation (chatbot + dashboard)**
- [x] **Chat page with category selection**
- [x] **ChatWindow component with simulated AI**
- [x] **BOMPreview component with real-time updates**
- [x] **Dashboard page with Chart.js visualizations**
- [x] **API service layer with Axios**

### 🚧 In Progress (Phase 1 - Data Layer & Phase 2 - AI Agents)
- [ ] Backend API endpoints (chat, BOM management)
- [ ] WebSocket integration for real-time chat
- [ ] AI agent orchestration with LangChain/LangGraph
- [ ] Requirement gatherer agent
- [ ] Hardware selector agent
- [ ] Software recommender agent
- [ ] Services estimator agent
- [ ] BOM validator agent

### 📋 Next Steps (Phase 3 - Integration)
- [ ] Connect frontend to real backend API
- [ ] BOM collection system (scan workspace for BOMs)
- [ ] Format detection (identify BOM structures)
- [ ] Universal parser (handle multiple formats)
- [ ] Pattern learning engine (extract rules from BOMs)
- [ ] Template generator (create reusable templates)
- [ ] Azure infrastructure setup (when ready)
- [ ] SharePoint integration (when ready)

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for complete 10-week roadmap.

## 📝 API Endpoints (Planned)

### Health & Status
- `GET /health` - Basic health check ✓
- `GET /health/ready` - Readiness check with dependencies

### Chat (TODO)
- `POST /api/bom/start` - Start new BOM session
- `POST /api/bom/chat` - Send message, get response
- `GET /api/bom/session/{id}` - Get session state
- `WebSocket /ws/chat/{session_id}` - Real-time chat

### BOM Management (TODO)
- `GET /api/bom/{id}` - Get BOM by ID
- `PUT /api/bom/{id}` - Update BOM
- `POST /api/bom/validate` - Validate BOM
- `POST /api/bom/export/excel` - Export to Excel
- `POST /api/bom/export/pdf` - Export to PDF

### Analytics (TODO)
- `GET /api/analytics/spending` - Spending by category
- `GET /api/analytics/vendors` - Vendor performance
- `GET /api/analytics/patterns` - Pattern insights

## 🤝 Team & Contacts

**Project Lead**: [Your Name]  
**Client**: IT Procurement Team  
**Timeline**: 10 weeks (Started: June 2026)

---

**Status**: 🟡 Phase 0.1 Complete, Phase 0.2 Starting  
**Last Updated**: 2026-06-26
