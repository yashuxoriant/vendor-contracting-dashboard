# Backend - IT BOM Creation System

FastAPI-based backend service providing REST APIs for BOM creation, chat orchestration, and analytics.

## 📋 Table of Contents
- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)

## 🏗️ Architecture

The backend follows a layered architecture:

```
┌─────────────────────────────────────────┐
│         FastAPI REST API Layer          │
│   (chat.py, bom.py, analytics.py)      │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│        Services Layer                   │
│  (bom_delta_pipeline, search, ingest)  │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│       AI Agents Layer                   │
│  (Orchestrator, Gatherer, Validator)   │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│      Data Access Layer                  │
│   (Cosmos DB, ADLS, SharePoint)        │
└─────────────────────────────────────────┘
```

### Tech Stack
- **Framework**: FastAPI 0.109
- **ASGI Server**: Uvicorn
- **AI/LLM**: LangGraph 0.0.20 + Anthropic Claude (via Azure AI Foundry)
- **Database**: Azure Cosmos DB (NoSQL) with mock for dev
- **Storage**: Azure Data Lake Storage Gen2 with mock for dev
- **Search**: Azure AI Search (vector embeddings)
- **Authentication**: JWT (planned)

## 📂 Directory Structure

```
backend/
├── ai/                          # AI agents and LLM integration
│   ├── agents/
│   │   ├── orchestrator.py      # BOMOrchestrator - 7-phase state machine
│   │   └── analytics_agent.py   # Analytics query agent
│   ├── client.py                # Azure AI Foundry client wrapper
│   ├── prompts/
│   │   └── system_base.py       # Master system prompt + category addenda
│   └── skills/
│       └── Skill_Network_Telecom.md  # Network/Telecom specialist skill
├── api/                         # REST API endpoints
│   ├── __init__.py
│   ├── analytics.py             # GET /api/analytics/* endpoints
│   ├── audit.py                 # Audit logging (TODO)
│   ├── bom.py                   # BOM CRUD + export endpoints
│   ├── catalog.py               # Catalog search endpoints
│   ├── chat.py                  # Chat + streaming endpoints
│   ├── ingest.py                # BOM ingestion pipeline
│   ├── notify.py                # Notifications (TODO)
│   ├── sharepoint.py            # SharePoint integration
│   └── templates.py             # BOM templates
├── db/                          # Database clients
│   ├── __init__.py
│   ├── cosmos_client.py         # Real Azure Cosmos DB client
│   ├── mock_cosmos_client.py    # In-memory mock for dev
│   ├── adls_client.py           # Real Azure ADLS Gen2 client
│   ├── mock_adls_client.py      # Local filesystem mock
│   ├── sharepoint_client.py     # Microsoft Graph SharePoint client
│   └── schemas.py               # Pydantic data models
├── services/                    # Business logic services
│   ├── __init__.py
│   ├── bom_delta_pipeline.py    # BOM delta detection
│   ├── bom_ingest.py            # BOM file ingestion
│   ├── search_service.py        # Azure AI Search integration
│   └── ...                      # (other services)
├── data/                        # Static data files
│   └── eol_skus.json            # End-of-life SKU database
├── config.py                    # Configuration + feature flags
├── main.py                      # FastAPI application entry point
├── healthcheck.py               # Health check logic
├── requirements.txt             # Python dependencies
├── requirements-api.txt         # Minimal API dependencies
├── Dockerfile                   # Docker container definition
└── .env.example                 # Environment variables template
```

## 🚀 Setup & Installation

### Prerequisites
- Python 3.11+
- pip or conda
- Azure subscription (optional - mock mode available)

### Installation

1. **Create virtual environment**:
   ```bash
   cd backend
   python -m venv venv
   venv\Scripts\activate  # Windows
   # source venv/bin/activate  # Linux/Mac
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your settings (see Configuration section)
   ```

4. **Run the server**:
   ```bash
   # Development mode with auto-reload
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   
   # Or use the startup script
   ..\start-backend.bat
   ```

5. **Verify installation**:
   - API: http://localhost:8000
   - Health check: http://localhost:8000/health
   - API docs: http://localhost:8000/docs
   - OpenAPI schema: http://localhost:8000/openapi.json

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the `backend/` directory:

```env
# Feature Flags (Development Mode)
USE_DUMMY_COSMOS=True           # Use in-memory mock instead of Cosmos DB
USE_DUMMY_ADLS=True             # Use local filesystem instead of ADLS
USE_AZURE_OPENAI=True           # Use Azure AI Foundry for LLM calls

# Azure AI Foundry (Anthropic via Azure)
AZURE_AI_FOUNDRY_ENDPOINT=https://ma-workstream-planner-p-resource.services.ai.azure.com
AZURE_AI_FOUNDRY_KEY=your-key-here
ANTHROPIC_MODEL=claude-opus-4-6

# Azure Cosmos DB (when USE_DUMMY_COSMOS=False)
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE=bom-db

# Azure Data Lake Storage Gen2 (when USE_DUMMY_ADLS=False)
ADLS_ACCOUNT_NAME=your-storage-account
ADLS_ACCOUNT_KEY=your-storage-key
ADLS_CONTAINER=bom-files

# Azure AI Search (for RAG)
AZURE_SEARCH_ENDPOINT=https://your-search.search.windows.net
AZURE_SEARCH_KEY=your-search-key
AZURE_SEARCH_INDEX=bom-embeddings

# SharePoint (Microsoft Graph)
SHAREPOINT_SITE_URL=https://yourorg.sharepoint.com/sites/BOMs
SHAREPOINT_CLIENT_ID=your-client-id
SHAREPOINT_CLIENT_SECRET=your-client-secret
SHAREPOINT_TENANT_ID=your-tenant-id

# Server Configuration
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO

# CORS (Frontend URLs)
CORS_ORIGINS=["http://localhost:5173", "http://localhost:3000"]
```

### Feature Flags Explained

| Flag | Purpose | Default |
|------|---------|---------|
| `USE_DUMMY_COSMOS` | Use in-memory dict instead of Cosmos DB | `True` (dev) |
| `USE_DUMMY_ADLS` | Use local filesystem instead of Azure Storage | `True` (dev) |
| `USE_AZURE_OPENAI` | Use Azure AI Foundry for LLM (vs direct Anthropic) | `True` |

**Development Mode** (no Azure credentials needed):
```env
USE_DUMMY_COSMOS=True
USE_DUMMY_ADLS=True
```

**Production Mode** (requires Azure credentials):
```env
USE_DUMMY_COSMOS=False
USE_DUMMY_ADLS=False
```

## 🔌 API Endpoints

### Health & Status
```http
GET  /health              # Basic health check (uptime, version)
GET  /health/ready        # Readiness check (DB, LLM, storage)
```

### Chat & BOM Creation
```http
POST /api/chat/start                     # Start new chat session
POST /api/chat/message                   # Send message (sync)
POST /api/chat/stream                    # Send message (SSE stream)
GET  /api/chat/history                   # List all sessions
GET  /api/chat/history/{id}              # Get session details
GET  /api/chat/history/{id}/transcript   # Download transcript
```

### BOM Management
```http
GET    /api/bom/{id}                # Get BOM by ID
POST   /api/bom                     # Create new BOM
PUT    /api/bom/{id}                # Update BOM
DELETE /api/bom/{id}                # Delete BOM
POST   /api/bom/validate            # Validate BOM structure
POST   /api/bom/{id}/export/excel   # Export to Excel
POST   /api/bom/{id}/export/pdf     # Export to PDF
```

### Analytics
```http
GET /api/analytics/summary          # Dashboard summary stats
GET /api/analytics/spending         # Spending by category/vendor
GET /api/analytics/vendors          # Vendor performance metrics
GET /api/analytics/patterns         # Pattern insights
```

### Catalog & Search
```http
GET  /api/catalog                   # Search catalog (SKUs, prices)
POST /api/catalog/search            # Advanced search with filters
GET  /api/catalog/similar/{sku}     # Find similar SKUs
```

### Templates
```http
GET  /api/templates                 # List BOM templates
POST /api/templates                 # Create template from BOM
GET  /api/templates/{id}            # Get template details
```

### SharePoint Integration
```http
POST /api/sharepoint/sync           # Sync BOMs from SharePoint
GET  /api/sharepoint/files          # List SharePoint BOM files
```

## 🧪 Development

### Running Tests
```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_bom_api.py
```

### Code Quality
```bash
# Linting
pylint backend/

# Type checking
mypy backend/

# Format code
black backend/
isort backend/
```

### Development Server with Auto-Reload
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000 --log-level debug
```

### Testing with cURL

**Start a chat session**:
```bash
curl -X POST http://localhost:8000/api/chat/start \
  -H "Content-Type: application/json" \
  -d '{
    "category": "Network & Telecom",
    "project": "Panasonic Day-1 Network"
  }'
```

**Send a message**:
```bash
curl -X POST http://localhost:8000/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_abc123",
    "message": "10 sites, 200 users per site, Cisco standard"
  }'
```

**Stream a message** (SSE):
```bash
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_abc123",
    "message": "Generate the BOM now"
  }'
```

## 🐳 Deployment

### Docker Build & Run

**Build image**:
```bash
docker build -t vc-backend:v9 -f Dockerfile.backend .
```

**Run container**:
```bash
docker run -p 8000:8000 \
  -e USE_DUMMY_COSMOS=True \
  -e USE_DUMMY_ADLS=True \
  vc-backend:v9
```

### Azure Container Apps Deployment

**Prerequisites**:
- Azure Container Registry (ACR)
- Azure Container Apps Environment

**Build & push to ACR**:
```bash
# Login to Azure
az login

# Build and push to ACR
az acr build \
  --registry <YOUR_ACR_NAME> \
  --image vc-backend:v9 \
  --file Dockerfile.backend \
  .
```

**Deploy to Container Apps**:
```bash
az containerapp update \
  --name vc-backend \
  --resource-group <YOUR_RG> \
  --image <YOUR_ACR_NAME>.azurecr.io/vc-backend:v9 \
  --set-env-vars \
    USE_DUMMY_COSMOS=False \
    USE_DUMMY_ADLS=False \
    COSMOS_ENDPOINT=secretref:cosmos-endpoint \
    COSMOS_KEY=secretref:cosmos-key
```

## 🔍 Troubleshooting

### Common Issues

**1. Import errors after installing dependencies**
```bash
# Clear Python cache and reinstall
find . -type d -name __pycache__ -exec rm -rf {} +
pip install -r requirements.txt --force-reinstall
```

**2. Cosmos DB connection errors**
```bash
# Verify credentials in .env
# Or switch to mock mode
USE_DUMMY_COSMOS=True
```

**3. LLM API timeouts**
```bash
# Increase timeout in config.py
LLM_TIMEOUT = 120  # seconds
```

**4. Port already in use**
```bash
# Kill process using port 8000
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac
lsof -ti:8000 | xargs kill -9
```

## 📚 Additional Resources

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture documentation
- [ROADMAP.md](../ROADMAP.md) - Development roadmap
- [API Documentation](http://localhost:8000/docs) - Interactive Swagger UI
- [Main README](../README.md) - Project overview

## 🤝 Contributing

See the main [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

## 📄 License

See [LICENSE](../LICENSE) for details.
