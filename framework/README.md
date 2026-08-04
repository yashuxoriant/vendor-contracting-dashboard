# Framework - Reusable Agentic AI Framework

A reusable, domain-agnostic framework for building conversational, stateful, multi-phase AI agents that operate over a knowledge base and guide users through structured workflows.

## 📋 Table of Contents
- [Overview](#overview)
- [Directory Structure](#directory-structure)
- [Core Concepts](#core-concepts)
- [Components](#components)
- [Usage](#usage)

## 🎯 Overview

The `framework/` directory provides the **execution mechanics** for building agentic AI applications. It is **domain-agnostic** and can be reused for any multi-step workflow requiring:

- **Conversational state management** across multiple turns
- **Multi-phase workflows** with gating logic
- **Knowledge base integration** (RAG, vector search)
- **LLM orchestration** with multiple models
- **Persistent storage** (Cosmos DB, ADLS)
- **Authentication and authorization**

This framework was extracted from the IT BOM Creation System but is designed to be **reusable** for other domains (HR onboarding, financial planning, regulatory compliance workflows, etc.).

## 📂 Directory Structure

```
framework/
├── __init__.py
├── settings.py                  # Framework-level settings
├── agents/                      # Agent execution framework
│   ├── __init__.py
│   ├── base_agent.py            # Abstract base agent class
│   ├── supervisor.py            # Multi-agent orchestration
│   └── state.py                 # State management primitives
├── api/                         # API utilities
│   ├── __init__.py
│   ├── middleware.py            # Request logging, timing, errors
│   └── dependencies.py          # FastAPI dependency injection
├── auth/                        # Authentication & authorization
│   ├── __init__.py
│   ├── jwt.py                   # JWT token handling
│   └── azure_ad.py              # Azure AD B2C integration
├── graph/                       # LangGraph utilities
│   ├── __init__.py
│   ├── builder.py               # Graph construction helpers
│   └── nodes.py                 # Reusable graph nodes
├── infra/                       # Infrastructure clients
│   ├── __init__.py
│   ├── cosmos.py                # Cosmos DB client
│   ├── adls.py                  # Azure Data Lake Storage client
│   ├── search.py                # Azure AI Search client
│   └── singletons.py            # Lazy singleton pattern for clients
├── instructions/                # Instruction loading system
│   ├── __init__.py
│   └── store.py                 # Load .md skill files from app/
├── memory/                      # Session memory management
│   ├── __init__.py
│   ├── session_store.py         # In-memory or Redis session store
│   └── checkpoint.py            # LangGraph checkpoint persistence
├── security/                    # Security utilities
│   ├── __init__.py
│   ├── encryption.py            # Data encryption helpers
│   └── secrets.py               # Azure Key Vault integration
├── web/                         # Web utilities
│   ├── __init__.py
│   ├── cors.py                  # CORS configuration
│   └── sse.py                   # Server-Sent Events (SSE) streaming
└── workflow/                    # Workflow primitives
    ├── __init__.py
    ├── phase.py                 # Phase state machine
    ├── gate.py                  # Phase gate logic (field completeness)
    └── transition.py            # Phase transition rules
```

## 🧠 Core Concepts

### 1. Agents (`agents/`)

**Base Agent** (`base_agent.py`):
Abstract class defining the agent interface:

```python
class BaseAgent(ABC):
    @abstractmethod
    async def run(self, session: dict, message: str) -> tuple:
        """Execute agent logic. Returns (response, data, progress, complete)."""
        pass
    
    @abstractmethod
    def build_context(self, session: dict, message: str) -> dict:
        """Build context for LLM call (system prompt, history, RAG)."""
        pass
    
    @abstractmethod
    def extract_data(self, response: str) -> Optional[dict]:
        """Extract structured data from LLM response."""
        pass
```

**Supervisor** (`supervisor.py`):
Multi-agent orchestration - route user requests to specialist agents:

```python
class AgentSupervisor:
    def route(self, session: dict, message: str) -> BaseAgent:
        """Route to specialist agent based on session context."""
        category = session.get("category")
        return self.agent_registry.get(category, self.default_agent)
```

### 2. Workflow (`workflow/`)

**Phase State Machine** (`phase.py`):
```python
class Phase(Enum):
    INTAKE = 1
    QUALIFY = 2
    SCOPE = 3
    # ... etc

class PhaseStateMachine:
    def advance(self, current: Phase, state: dict) -> Phase:
        """Advance to next phase if gates are satisfied."""
        if self.gate_satisfied(current, state):
            return self.next_phase(current)
        return current
```

**Gate Logic** (`gate.py`):
```python
class PhaseGate:
    def check(self, phase: Phase, state: dict) -> bool:
        """Check if all required fields for this phase are present."""
        required_fields = self.gates[phase]
        return all(state.get(field) for field in required_fields)
```

### 3. Infrastructure (`infra/`)

**Lazy Singletons** (`singletons.py`):
```python
class LazyCosmosClient:
    _instance = None
    
    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = CosmosClient(endpoint, key)
        return cls._instance
```

**Usage**:
```python
from framework.infra.singletons import get_cosmos, get_adls, get_search

cosmos = get_cosmos()  # Lazy init on first call
adls = get_adls()
search = get_search()
```

### 4. Memory (`memory/`)

**Session Store** (`session_store.py`):
```python
class SessionStore:
    def save(self, session_id: str, state: dict):
        """Persist session state."""
    
    def load(self, session_id: str) -> dict:
        """Load session state."""
    
    def checkpoint(self, session_id: str, graph_state: dict):
        """Save LangGraph checkpoint."""
```

### 5. Instructions (`instructions/`)

**Skill Loader** (`store.py`):
```python
class InstructionStore:
    def load_skill(self, category: str) -> str:
        """Load specialist skill .md file from app/instructions/BOM/"""
        path = self.skills_dir / f"Skill_{category}.md"
        return path.read_text()
    
    def list_skills(self) -> List[str]:
        """List all available skill files."""
        return [f.stem for f in self.skills_dir.glob("Skill_*.md")]
```

## 🔧 Components

### API Middleware (`api/middleware.py`)

**Request Logging**:
```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {duration:.3f}s")
    return response
```

**Error Handling**:
```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": str(exc)})
```

### SSE Streaming (`web/sse.py`)

**Server-Sent Events** for streaming LLM responses:

```python
async def stream_llm_response(prompt: str):
    async for chunk in llm_client.stream(prompt):
        yield f"data: {json.dumps({'text': chunk})}\n\n"
    yield "data: [DONE]\n\n"

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    return StreamingResponse(
        stream_llm_response(request.message),
        media_type="text/event-stream"
    )
```

### Auth (`auth/jwt.py`)

**JWT Token Generation**:
```python
def create_access_token(user_id: str, expires_delta: timedelta = None):
    payload = {"sub": user_id, "exp": datetime.utcnow() + (expires_delta or timedelta(hours=24))}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

**JWT Verification**:
```python
def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
```

### LangGraph Utilities (`graph/builder.py`)

**Graph Construction**:
```python
def build_workflow_graph(nodes: List[Callable]) -> StateGraph:
    graph = StateGraph(WorkflowState)
    
    for node in nodes:
        graph.add_node(node.__name__, node)
    
    graph.set_entry_point(nodes[0].__name__)
    
    for i in range(len(nodes) - 1):
        graph.add_edge(nodes[i].__name__, nodes[i+1].__name__)
    
    graph.set_finish_point(nodes[-1].__name__)
    
    return graph.compile()
```

## 🛠️ Usage

### Creating a New Domain Application

1. **Define your domain** in `app/`:
   ```
   app/
   ├── agents/
   │   └── my_domain_agent.py
   └── instructions/
       └── MyDomain/
           └── Skill_MyCategory.md
   ```

2. **Implement agent** extending `BaseAgent`:
   ```python
   from framework.agents.base_agent import BaseAgent
   
   class MyDomainAgent(BaseAgent):
       async def run(self, session: dict, message: str) -> tuple:
           # Your logic here
           pass
   ```

3. **Use framework infrastructure**:
   ```python
   from framework.infra.singletons import get_cosmos, get_adls
   from framework.memory.session_store import SessionStore
   from framework.web.sse import stream_response
   
   cosmos = get_cosmos()
   session_store = SessionStore(cosmos)
   ```

4. **Register agent** in API routes:
   ```python
   from app.agents.my_domain_agent import MyDomainAgent
   
   @app.post("/api/my-domain/chat")
   async def chat(request: ChatRequest):
       agent = MyDomainAgent()
       return await agent.run(session, request.message)
   ```

### Extending the Framework

**Add new infrastructure client**:
```python
# framework/infra/my_service.py
class MyServiceClient:
    def __init__(self, endpoint: str, key: str):
        self.endpoint = endpoint
        self.key = key
    
    def query(self, q: str):
        # Implementation
        pass

# framework/infra/singletons.py
_my_service_client = None

def get_my_service():
    global _my_service_client
    if _my_service_client is None:
        _my_service_client = MyServiceClient(...)
    return _my_service_client
```

**Add new middleware**:
```python
# framework/api/middleware.py
@app.middleware("http")
async def custom_middleware(request: Request, call_next):
    # Your middleware logic
    response = await call_next(request)
    return response
```

## 📚 Additional Resources

- [Backend README](../backend/README.md) - API implementation
- [App README](../app/README.md) - Domain agents
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [Main README](../README.md) - Project overview

## 📄 License

See [LICENSE](../LICENSE) for details.
