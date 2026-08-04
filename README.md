# IT BOM Creation System

AI-powered Bill of Materials (BOM) creation assistant and analytics dashboard for IT infrastructure projects in M&A contexts.

## 🎯 Overview

This system helps IT teams accelerate M&A technology integration by:
- **Create vendor-ready BOMs in <1 hour** (vs 2-3 weeks manually) using AI-powered conversational interface
- **Enforce 3-party approval workflow** (Buyer IT, Seller IT, SI) to eliminate email back-and-forth
- **Analyze spending patterns** from historical quotes across 6 technology categories
- **Generate vendor-ready exports** in Excel format with proper sequencing
- **Learn from 1000+ historical BOMs** via RAG (Retrieval-Augmented Generation)
- **Reduce BOM cycle time from 14 days → 3 days** (target KPI)

### Target Users
- **IT Procurement Teams** (PwC M&A practice)
- **M&A Integration Managers**
- **Systems Integrators** (NTT Data, JBR, etc.)

## 🏗️ Architecture

### Tech Stack
- **Frontend**: React 18, Vite, Redux Toolkit, Material-UI v5, Chart.js, React Router v6
- **Backend**: FastAPI 0.109, Uvicorn, Pydantic
- **AI/LLM**: LangGraph 0.0.20 + Anthropic Claude (via Azure AI Foundry)
- **Database**: Azure Cosmos DB (NoSQL) with local mock for development
- **Storage**: Azure Data Lake Storage Gen2 with local filesystem mock
- **Search**: Azure AI Search (vector embeddings for RAG)
- **Document Repo**: SharePoint Online via Microsoft Graph API
- **Auth**: JWT (Azure AD B2C planned)

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Frontend (React + MUI)                      │
│  ChatPage | OverviewPage | BOMLibraryPage | RFQBuilder      │
└────────────────────────┬────────────────────────────────────┘
                         │ REST API + SSE Streaming
┌────────────────────────▼────────────────────────────────────┐
│              Backend (FastAPI + Python)                      │
│  /api/chat | /api/bom | /api/analytics | /api/catalog      │
└────────────────────────┬────────────────────────────────────┘
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
┌───▼────┐     ┌─────────▼─────────┐    ┌───▼────┐
│ Cosmos │     │ AI Agents Layer   │    │  ADLS  │
│   DB   │     │ (LangGraph)       │    │  Gen2  │
└────────┘     │ - BOMOrchestrator │    └────────┘
               │ - Gatherer Agent  │
               │ - Validator Agent │
               └─────────┬─────────┘
                         │
               ┌─────────▼──────────┐
               │  Azure AI Foundry  │
               │ (Anthropic Claude) │
               └────────────────────┘
```

### Key Components
1. **Chat-based BOM Builder**: 10-phase guided conversation with AI agent
2. **3-Party Approval Workflow**: Sequential Buyer IT → Seller IT → SI sign-off
3. **Analytics Dashboard**: Spending insights, vendor performance, KPI tracking
4. **BOM Library**: Version control, templates, search, inline editing
5. **SharePoint Integration**: Sync historical BOMs, push generated BOMs
6. **Catalog System**: 1200+ SKUs extracted from historical BOMs
7. **Export Engine**: Excel with order sequencing (racks → networking → compute → cables → licenses)

## 📂 Project Structure

```
vendor-contracting-dashboard/
├── backend/                    # Python FastAPI backend
│   ├── ai/                    # AI agents and LLM integration
│   │   ├── agents/            # BOMOrchestrator, analytics agent
│   │   ├── prompts/           # System prompts + category addenda
│   │   ├── skills/            # Specialist skill files (markdown)
│   │   └── client.py          # Azure AI Foundry client wrapper
│   ├── api/                   # REST API endpoints
│   │   ├── chat.py            # Chat + streaming endpoints
│   │   ├── bom.py             # BOM CRUD + export
│   │   ├── analytics.py       # Analytics queries
│   │   ├── catalog.py         # Catalog search
│   │   └── sharepoint.py      # SharePoint integration
│   ├── db/                    # Database clients and schemas
│   │   ├── cosmos_client.py   # Real Cosmos DB operations
│   │   ├── mock_cosmos_client.py # Local dev mock
│   │   ├── adls_client.py     # Azure Storage operations
│   │   ├── mock_adls_client.py   # Local dev mock
│   │   └── schemas.py         # Pydantic data models
│   ├── services/              # Business logic services
│   │   ├── bom_delta_pipeline.py # BOM diff detection
│   │   ├── bom_ingest.py      # BOM file ingestion
│   │   └── search_service.py  # Azure AI Search integration
│   ├── config.py              # Configuration with feature flags
│   ├── main.py                # FastAPI application
│   ├── requirements.txt       # Python dependencies
│   ├── Dockerfile             # Docker container definition
│   └── README.md              # → 📘 Backend documentation
├── frontend/                   # React frontend
│   ├── src/
│   │   ├── components/        # Reusable components
│   │   │   ├── ChatWindow.jsx
│   │   │   ├── BOMPreview.jsx
│   │   │   ├── CategoryCard.jsx
│   │   │   └── Layout.jsx
│   │   ├── pages/             # Page components
│   │   │   ├── ChatPage.jsx
│   │   │   ├── OverviewPage.jsx
│   │   │   ├── BOMLibraryPage.jsx
│   │   │   ├── VendorPriceSelectorPage.jsx
│   │   │   └── BOMReviewPage.jsx
│   │   ├── services/          # API layer
│   │   │   ├── api.js
│   │   │   ├── bomApi.js
│   │   │   └── chatApi.js
│   │   ├── store/             # Redux state management
│   │   │   └── slices/
│   │   ├── App.jsx            # Main app with routing
│   │   └── main.jsx           # Entry point
│   ├── package.json           # Dependencies
│   ├── vite.config.js         # Vite configuration
│   ├── nginx.conf             # Nginx config (Docker)
│   ├── Dockerfile             # Docker container definition
│   └── README.md              # → 📘 Frontend documentation
├── app/                        # AI agents & domain logic
│   ├── agents/
│   │   ├── bom_creation_agent.py    # LangGraph BOM workflow
│   │   ├── bom_prompt_config.py     # Dynamic prompt builder
│   │   └── bom_extraction_config.py # BOM extraction rules
│   ├── instructions/           # Specialist skill files
│   │   ├── Shared.md
│   │   └── BOM/
│   │       └── Skill_Network_Telecom.md
│   └── README.md              # → 📘 Agent system documentation
├── framework/                  # Reusable agentic AI framework
│   ├── agents/                # Agent execution framework
│   ├── api/                   # API utilities (middleware)
│   ├── auth/                  # JWT + Azure AD
│   ├── graph/                 # LangGraph utilities
│   ├── infra/                 # Infrastructure clients
│   ├── memory/                # Session memory management
│   ├── web/                   # SSE streaming, CORS
│   ├── workflow/              # Phase state machine
│   └── README.md              # → 📘 Framework documentation
├── catalog_data.json          # Historical BOM data (static catalog)
├── start-all.bat              # Start both frontend + backend
├── start-backend.bat          # Start backend only
├── start-frontend.bat         # Start frontend only
├── ARCHITECTURE.md            # → 📘 Detailed architecture documentation
├── ROADMAP.md                 # → 📘 Development roadmap (5 sprints)
├── QUICKSTART.md              # → 📘 Quick start guide
└── README.md                  # This file
```

### 📘 Section-Specific Documentation

Each major component has its own detailed README:

| Component | Path | Documentation |
|-----------|------|---------------|
| **Backend** | [`backend/`](backend/) | [backend/README.md](backend/README.md) - API endpoints, configuration, deployment |
| **Frontend** | [`frontend/`](frontend/) | [frontend/README.md](frontend/README.md) - React components, pages, Redux setup |
| **AI Agents** | [`app/`](app/) | [app/README.md](app/README.md) - Agent system, specialist skills |
| **Framework** | [`framework/`](framework/) | [framework/README.md](framework/README.md) - Reusable agentic AI framework |

## 🚀 Getting Started

### Quick Start (Single Command)

The fastest way to get started is using the included startup script:

```bash
# Start both backend and frontend servers
start-all.bat
```

This opens two terminals:
- **Backend**: http://localhost:8000 (FastAPI + Uvicorn)
- **Frontend**: http://localhost:5173 (React + Vite)

### Prerequisites
- **Backend**: Python 3.11+, pip
- **Frontend**: Node.js 18+, npm 9+
- **Optional**: Azure subscription (can use mock mode for local dev)

### Detailed Setup

#### 1. Backend Setup

See [backend/README.md](backend/README.md) for complete instructions.

**Quick version**:
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: Set USE_DUMMY_COSMOS=True, USE_DUMMY_ADLS=True for local dev
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### 2. Frontend Setup

See [frontend/README.md](frontend/README.md) for complete instructions.

**Quick version**:
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

#### 3. Extractor Setup (Optional - for catalog building)

See [extractor/README.md](extractor/README.md) for complete instructions.

**Quick version**:
```bash
cd extractor
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
# Place BOM files in ../quotes/ folder
python main.py
# Output: ../catalog_data.json
```

### Access Points

After starting the servers:

| Service | URL | Description |
|---------|-----|-------------|
| **Frontend** | http://localhost:5173 | Main web application |
| **Backend API** | http://localhost:8000 | REST API endpoints |
| **API Docs** | http://localhost:8000/docs | Interactive Swagger UI |
| **Health Check** | http://localhost:8000/health | Server health status |

### Feature Flags (Development Mode)

For local development **without Azure credentials**, use mock mode in `backend/.env`:

```env
# Mock mode (no Azure subscription needed)
USE_DUMMY_COSMOS=True    # Use in-memory dict instead of Cosmos DB
USE_DUMMY_ADLS=True      # Use local filesystem instead of Azure Storage
USE_AZURE_OPENAI=True    # Use Azure AI Foundry (or set False to skip LLM calls)
```

For **production deployment**, set all flags to `False` and provide Azure credentials.

### First-Time User Flow

1. **Open frontend**: http://localhost:5173
2. **Click "Create BOM"** on homepage
3. **Select category**: e.g., "Network & Telecom"
4. **Chat with AI**: Answer 5-10 questions about your requirements
5. **Watch BOM build**: Right panel shows real-time BOM generation
6. **Export**: Download Excel file when complete

## 🎯 Key Features

### 1. AI-Powered BOM Creation
- **10-Phase Guided Workflow**: Intake → Qualify → Scope → Sizing → Generate → Validate → Complete
- **8+ Technology Categories**: Data Center, Network, SD-WAN, Cybersecurity, Cloud, M365, EOL Replacement
- **Conversational Interface**: Natural language chat (no forms)
- **Real-time BOM Preview**: See line items as they're generated
- **Streaming Responses**: SSE-based streaming for immediate feedback
- **Smart Defaults**: Day-1 pre-population for Network categories

### 2. 3-Party Approval Workflow
- **Sequential Sign-off**: Buyer IT → Seller IT → SI (Systems Integrator)
- **Reset on Changes**: Any modification restarts approval from Buyer IT
- **Audit Trail**: Who approved when, with comments
- **Export Lock**: BOM cannot be sent to vendors until all 3 approved

### 3. Analytics Dashboard
- **KPI Tracking**: Total spend, active BOMs, avg cycle time (14 days → 3 days target)
- **Spending Insights**: By category, by vendor, trend analysis
- **Chart.js Visualizations**: Interactive pie, bar, line charts
- **Live Alerts**: BOM status change notifications

### 4. BOM Library & Management
- **Search & Filter**: Full-text search, status filter, category filter
- **Inline Editing**: Click-to-edit cells with validation
- **Version Control**: Track all BOM revisions
- **BOM Comparison**: Side-by-side diff of 2+ BOMs
- **Bulk Export**: CSV/Excel export of multiple BOMs

### 5. Vendor Catalog
- **1200+ SKUs**: Extracted from historical BOMs
- **6 Categories**: Compute, Storage, Network, Security, Cloud, Licenses
- **48+ Services**: Access Points, SD-WAN, Firewalls, Servers, etc.
- **Price History**: Min/max/avg pricing across multiple vendors
- **Add to BOM**: One-click add catalog items to active BOM

### 6. RFQ Builder & Quote Extraction
- **RFQ Cart**: Build vendor-ready quote requests
- **CSV Export**: Generate vendor submission files
- **Quote Upload**: Drag-and-drop vendor quotes (Excel, CSV, PDF)
- **Intelligent Parsing**: AI-based extraction with confidence scoring
- **Map to BOM**: Match extracted items to BOM structure

## 📊 Project Status

### ✅ Completed Features

**Backend (Phase 1 & 2)**:
- [x] FastAPI application with middleware (request logging, timing, CORS)
- [x] Database layer: Cosmos DB + ADLS clients with mock mode
- [x] Complete Pydantic schemas (BOM, ChatSession, User, Template)
- [x] Chat API with streaming (SSE) support
- [x] BOM CRUD operations + validation
- [x] Analytics endpoints (summary, spending, vendors, patterns)
- [x] Catalog search API
- [x] SharePoint integration (Microsoft Graph)
- [x] AI Agents: BOMOrchestrator (7-phase state machine)
- [x] LangGraph BOM creation workflow (fully implemented)
- [x] Azure AI Foundry integration (Anthropic Claude)
- [x] RAG (Retrieval-Augmented Generation) via Azure AI Search
- [x] Specialist skills system (Network/Telecom skill complete)
- [x] Day-1 pre-population for Network categories
- [x] BOM delta detection pipeline
- [x] Excel export (with openpyxl)

**Frontend (Phase 1 & 2)**:
- [x] React 18 + Vite 5 + Material-UI v5 setup
- [x] Redux Toolkit state management (auth, chat, bom, ui, analytics)
- [x] 7 main pages: Chat, Overview, BOM Library, Vendor Selector, RFQ Builder, Quote Extractor, BOM Review
- [x] ChatWindow component with message bubbles, typing indicators
- [x] BOMPreview component with real-time updates
- [x] CategoryCard selection with 8+ categories
- [x] Phase progress indicator (10 phases)
- [x] Analytics dashboard with Chart.js (KPI cards, pie/bar charts)
- [x] BOM Library with search/filter/inline editing
- [x] Vendor Price Selector with catalog browser
- [x] RFQ Builder with cart system
- [x] Quote Extractor with drag-and-drop upload
- [x] BOM Review page with 3-party approval UI
- [x] Domain pre-selection for Network categories

**Extractor (Phase 0)**:
- [x] File format detection (Excel, CSV, PDF)
- [x] Heuristic extraction (pattern-based, no LLM)
- [x] AI validator (LLM-based quality check)
- [x] AI categorizer (6 categories, 48+ services)
- [x] LLM router with failover (Groq → OpenAI → Anthropic)
- [x] Web scraper (optional price enrichment)
- [x] Catalog builder (unified catalog JSON)
- [x] SharePoint connector (Microsoft Graph)
- [x] ~1200 SKUs extracted from historical BOMs

**Infrastructure**:
- [x] Docker containers (frontend + backend)
- [x] Nginx configuration for production
- [x] Azure Container Registry build pipelines
- [x] Azure Container Apps deployment ready

### 🚧 In Progress (Phase 3 - Sprint 3)

- [ ] 3-party approval workflow backend logic (BOMApproval schema, endpoints)
- [ ] Audit logging (AuditEvent schema, log every mutation)
- [ ] EOL/EOS validation (eol_skus.json, check_eol_status service)
- [ ] JWT authentication (Azure AD B2C integration)
- [ ] Wire Redux BOM saves to backend API
- [ ] KPI cycle-time analytics (real queries vs hardcoded)

### 📋 Planned (Phase 4 & 5 - Sprints 4-5)

- [ ] Backend catalog API (replace hardcoded frontend catalog)
- [ ] Dual-quote requirement flag (line items > $50K)
- [ ] Lead-time warnings (Day-1 date vs longest lead time)
- [ ] Spares kit validation (10% rule)
- [ ] Maintenance contract validation (every hardware item)
- [ ] Order sequencing enforcement (Phase 10b)
- [ ] Email notifications (approval reminders)
- [ ] PDF export (in addition to Excel)
- [ ] User role-based access control (RBAC)
- [ ] Audit log viewer UI
- [ ] Advanced analytics (vendor comparison, price trends)

See [ROADMAP.md](ROADMAP.md) for the complete 5-sprint development plan (55 developer-days total).

## 🐳 Deployment

### Docker Deployment

**Build images**:
```bash
# Backend
docker build -t vc-backend:v9 -f Dockerfile.backend .

# Frontend
docker build -t vc-frontend:v9 -f frontend/Dockerfile frontend/
```

**Run containers**:
```bash
# Backend
docker run -p 8000:8000 \
  -e USE_DUMMY_COSMOS=True \
  -e USE_DUMMY_ADLS=True \
  vc-backend:v9

# Frontend
docker run -p 80:80 vc-frontend:v9
```

### Azure Container Apps Deployment

**Prerequisites**:
- Azure Container Registry (ACR)
- Azure Container Apps Environment
- Resource Group

**Build & push to ACR**:
```bash
# Login
az login

# Backend
az acr build \
  --registry <YOUR_ACR_NAME> \
  --image vc-backend:v9 \
  --file Dockerfile.backend \
  .

# Frontend
az acr build \
  --registry <YOUR_ACR_NAME> \
  --image vc-frontend:v9 \
  --file frontend/Dockerfile \
  frontend/
```

**Deploy to Container Apps**:
```bash
# Backend
az containerapp update \
  --name vc-backend \
  --resource-group <YOUR_RG> \
  --image <YOUR_ACR_NAME>.azurecr.io/vc-backend:v9

# Frontend
az containerapp update \
  --name vc-frontend \
  --resource-group <YOUR_RG> \
  --image <YOUR_ACR_NAME>.azurecr.io/vc-frontend:v9
```

See [backend/README.md](backend/README.md#deployment) and [frontend/README.md](frontend/README.md#build--deployment) for detailed deployment instructions.

## 📝 API Endpoints

Full API documentation available at http://localhost:8000/docs (Swagger UI).

### Key Endpoints

**Chat & BOM Creation**:
- `POST /api/chat/start` - Start new chat session
- `POST /api/chat/message` - Send message (sync response)
- `POST /api/chat/stream` - Send message (SSE streaming)
- `GET /api/chat/history` - List all sessions
- `GET /api/chat/history/{id}/transcript` - Download transcript

**BOM Management**:
- `GET /api/bom/{id}` - Get BOM by ID
- `POST /api/bom` - Create new BOM
- `PUT /api/bom/{id}` - Update BOM
- `POST /api/bom/validate` - Validate BOM
- `POST /api/bom/{id}/export/excel` - Export to Excel

**Analytics**:
- `GET /api/analytics/summary` - Dashboard KPIs
- `GET /api/analytics/spending` - Spending by category/vendor
- `GET /api/analytics/vendors` - Vendor performance

**Catalog**:
- `GET /api/catalog` - Search catalog (SKUs, prices)

See [backend/README.md#api-endpoints](backend/README.md#api-endpoints) for complete API reference.

## 📚 Documentation

### Core Documentation
- **[QUICKSTART.md](QUICKSTART.md)** - Single-command quick start guide
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Detailed system architecture, data flow, tech stack
- **[ROADMAP.md](ROADMAP.md)** - 5-sprint development roadmap (55 developer-days)
- **[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)** - Original 10-week detailed plan
- **[ENHANCEMENTS_COMPLETED.md](ENHANCEMENTS_COMPLETED.md)** - Feature completion log

### Component Documentation
- **[backend/README.md](backend/README.md)** - Backend setup, API reference, deployment
- **[frontend/README.md](frontend/README.md)** - Frontend setup, components, pages, build
- **[extractor/README.md](extractor/README.md)** - BOM extraction pipeline, catalog building
- **[app/README.md](app/README.md)** - AI agents, specialist skills, domain logic
- **[framework/README.md](framework/README.md)** - Reusable agentic AI framework

### API Documentation
- **Swagger UI**: http://localhost:8000/docs (when backend is running)
- **OpenAPI Schema**: http://localhost:8000/openapi.json

### Additional Resources
- **System Instructions**: [Vendor_Contracting_Agent_System_Instructions.md](Vendor_Contracting_Agent_System_Instructions%20(1).md)
- **Sample BOMs**: `Colo_BOM_Rev5.xlsx`, `Data Center BoM - Honeywell (1).xlsx`
- **Catalog Data**: `catalog_data.json` (1200+ SKUs)

## 🧪 Testing

### Backend Tests
```bash
cd backend
pytest tests/ -v
pytest --cov=. --cov-report=html
```

### Frontend Tests
```bash
cd frontend
npm test
npm run test:coverage
```

### E2E Testing
```bash
# Start both servers first
start-all.bat

# Run E2E tests
cd frontend
npm run test:e2e
```

### Manual Testing
See [QUICKSTART.md](QUICKSTART.md) for step-by-step testing scenarios.

## 🔍 Troubleshooting

### Common Issues

**Backend won't start**:
```bash
# Check Python version (need 3.11+)
python --version

# Reinstall dependencies
pip install -r backend/requirements.txt --force-reinstall

# Check if port 8000 is already in use
netstat -ano | findstr :8000
```

**Frontend won't start**:
```bash
# Check Node.js version (need 18+)
node --version

# Clear cache and reinstall
rm -rf frontend/node_modules frontend/.vite
cd frontend && npm install
```

**CORS errors**:
- Verify backend is running at http://localhost:8000
- Check `backend/config.py` CORS_ORIGINS includes `http://localhost:5173`
- Check `frontend/vite.config.js` proxy configuration

**LLM API errors**:
- Set `USE_AZURE_OPENAI=False` in `.env` to skip LLM calls during dev
- Verify `AZURE_AI_FOUNDRY_ENDPOINT` and `AZURE_AI_FOUNDRY_KEY` are correct
- Check Azure AI Foundry rate limits

**Cosmos DB connection fails**:
- Use mock mode for local dev: `USE_DUMMY_COSMOS=True`
- Verify credentials if using real Cosmos DB
- Check firewall rules allow your IP

See component-specific READMEs for more troubleshooting:
- [backend/README.md#troubleshooting](backend/README.md#troubleshooting)
- [frontend/README.md#troubleshooting](frontend/README.md#troubleshooting)
- [extractor/README.md#troubleshooting](extractor/README.md#troubleshooting)

## 🤝 Team & Contacts

**Branch**: `abhi--vendor--dashboard`  
**Project Lead**: Abhishek Dore  
**Client**: PwC M&A IT Procurement Team  
**Timeline**: August 2026 - September 2026 (5 sprints)

## 🎯 Success Metrics

| KPI | Current Baseline | Target | Status |
|-----|-----------------|--------|--------|
| **BOM cycle time** | 14 days | 3 days | 🟡 In Progress |
| **BOM first draft time** | 2-3 days | <1 hour | ✅ Achieved |
| **Approval round-trips** | 4-6 emails | 1 workflow click | 🟡 In Progress |
| **SKU error rate** | ~15% | <2% | 🟡 In Progress |
| **Vendor quote revisions** | 2-3 | 0-1 | 🟡 In Progress |
| **User adoption** | 0 users | 20 PwC users | 🔴 Not Started |

## 📄 License

See [LICENSE](LICENSE) for details.

---

**Status**: 🟢 Sprint 2 Complete | 🟡 Sprint 3 In Progress  
**Last Updated**: 2026-08-03  
**Version**: 1.0.0-beta
