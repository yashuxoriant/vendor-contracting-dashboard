# Agentic AI Framework — Architecture Specification

**Version:** 1.0  
**Status:** Reference Architecture  
**Audience:** Software Architects, Senior Engineers, Platform Teams

---

## 1. Overview

### 1.1 Purpose

This document specifies the reference architecture for a reusable **Agentic AI Framework** derived from a production multi-workstream AI planning application. The framework provides the execution mechanics for building conversational, stateful, multi-phase AI agents that operate over a domain-specific knowledge base, persist state across turns, and guide users through structured workflows.

The framework is intentionally domain-agnostic. It supports any application that requires:

- Multi-agent orchestration across independent domains or departments
- Phase-based workflows where agents hand off context to successor agents
- Per-session memory with long-term state persistence
- Retrieval-Augmented Generation (RAG) grounded in a private document corpus
- Hot-swappable, versioned instruction and skill content
- Structured rich-output protocols rendered by a frontend

### 1.2 Design Goals

| Goal | Description |
|---|---|
| **Domain independence** | No framework file imports from or references any domain-specific concept |
| **Registry-driven extensibility** | Adding a new domain, agent, or skill requires only configuration — no framework modification |
| **Separation of knowledge from mechanics** | Prompts, skills, step definitions, and decision vocabularies live entirely in the application layer |
| **Stateful conversation** | Every turn is grounded in persistent memory: confirmed facts, workflow progress, open blockers |
| **Streaming-first** | All primary response paths are async streaming; batch invocation is a fallback |
| **Prompt-cache aware** | System prompts are structured to maximise LLM-side prompt caching, reducing latency and cost |
| **Security by default** | Prompt injection detection, response sanitisation, and JWT-based auth are built in, not bolted on |
| **Graceful degradation** | Every external dependency (Blob, Cosmos, Search) has a local fallback so the system can run without cloud services during development |

### 1.3 High-Level Architecture

```mermaid
graph TB
    subgraph Client["Client Layer"]
        UI[React SPA]
    end

    subgraph API["API Layer (FastAPI)"]
        Auth[Auth Middleware]
        Security[Security Guards]
        Router[HTTP / SSE Router]
        Registry[Agent Registry]
    end

    subgraph Orchestration["Orchestration Layer (LangGraph)"]
        Supervisor[Supervisor Graph]
        WorkstreamGraph[Workstream Sub-Graph]
        PhaseNode[Phase Agent Node]
    end

    subgraph AgentCore["Agent Core"]
        ContextBuilder[Context Builder]
        SkillSelector[Skill Selector]
        PromptBuilder[Prompt Builder]
        LLMWrapper[LLM Wrapper / Streamer]
        StateExtractor[State Extractor]
    end

    subgraph Storage["Storage Layer"]
        CosmosMemory[(Cosmos DB\nConversation Memory)]
        CosmosWorkflow[(Cosmos DB\nWorkflow State)]
        BlobInstructions[(Blob Storage\nInstruction Versions)]
        AISearch[(Azure AI Search\nRAG Index)]
    end

    subgraph Instructions["Instruction System"]
        InstructionStore[Instruction Store\nBlob + Cosmos + Cache]
        SkillFiles[Skill Files\n.md on disk / Blob]
    end

    UI -->|HTTPS Bearer + SSE| Auth
    Auth --> Security
    Security --> Router
    Router --> Registry
    Registry --> Supervisor
    Supervisor -->|routes on workstream| WorkstreamGraph
    WorkstreamGraph -->|routes on phase| PhaseNode
    PhaseNode --> ContextBuilder
    ContextBuilder -->|embed + search| AISearch
    ContextBuilder --> SkillSelector
    SkillSelector -->|load skill text| SkillFiles
    ContextBuilder --> PromptBuilder
    PromptBuilder -->|system prompt| InstructionStore
    InstructionStore -->|versioned content| BlobInstructions
    PromptBuilder --> LLMWrapper
    LLMWrapper -->|stream tokens| Router
    LLMWrapper -->|full response| StateExtractor
    StateExtractor -->|upsert| CosmosMemory
    StateExtractor -->|upsert| CosmosWorkflow
    PhaseNode -->|load memory| CosmosMemory
```

---

## 2. Request Lifecycle

### 2.1 Complete Execution Flow

```mermaid
sequenceDiagram
    participant U as User (Browser)
    participant API as FastAPI
    participant Auth as Auth Middleware
    participant Sec as Security Guards
    participant Reg as Agent Registry
    participant Mem as Memory Manager
    participant Graph as LangGraph Supervisor
    participant Sub as Workstream Sub-Graph
    participant Agent as Phase Agent Node
    participant Ret as Retriever (RAG)
    participant IS as Instruction Store
    participant SS as Skill Selector
    participant PB as Prompt Builder
    participant LLM as LLM Wrapper
    participant SE as State Extractor
    participant DB as Cosmos DB

    U->>API: GET /chat/stream?query=...&workstream=...&phase=...
    API->>Auth: Validate JWT (Entra JWKS)
    Auth-->>API: User claims + roles
    API->>Sec: _detect_extraction_attempt(query)
    Sec-->>API: safe / blocked

    API->>Reg: resolve(workstream, phase)
    Reg-->>API: AgentConfig (prepare_ctx, get_prompt, valid_steps)

    API->>Mem: load_memory(entity_id, scope, sub_scope, user_key, session_id)
    Mem->>DB: read session doc + state doc + shared doc
    DB-->>Mem: messages, decisions, stage_progress, blockers, inventory
    Mem-->>API: memory dict

    API->>Graph: invoke(AgentState)
    Graph->>Sub: route on state.routing_key
    Sub->>Agent: route on state.sub_routing_key

    Agent->>Ret: retrieve(index_key, filter, query, top_k)
    Ret-->>Agent: chunks[]

    Agent->>IS: get_active_content(system_prompt_scope)
    IS-->>Agent: system_prompt (Blob or fallback)

    Agent->>SS: select_skills(query, stage_progress)
    SS->>IS: get_active_content(skill_scope) x N
    IS-->>SS: skill_texts[]
    SS-->>Agent: skill_texts[]

    Agent->>PB: build_llm_messages(query, chunks, system_prompt, history, state, skills)
    PB-->>Agent: messages[]

    Agent->>LLM: astream(messages)
    loop Token stream
        LLM-->>API: token
        API->>Sec: _sanitise_token(token)
        Sec-->>API: token or None
        API-->>U: data: {token}\n\n (SSE)
    end

    Note over Agent,DB: Background task (post-stream)
    Agent->>SE: extract_state_updates(query, answer, existing_state, config)
    SE->>LLM: invoke extraction prompt
    LLM-->>SE: JSON {decisions, stage_progress, blockers}
    SE-->>Agent: validated state delta

    Agent->>Mem: save_memory(entity_id, scope, sub_scope, user_key, full_state)
    Mem->>DB: upsert session doc + state doc + shared doc
    Agent->>DB: upsert workflow pipeline doc
```

### 2.2 Key Lifecycle Stages

| Stage | Owner | Blocking? | Fallback |
|---|---|---|---|
| JWT validation | Auth middleware | Yes — 401 on failure | Dev bypass mode |
| Injection detection | Security guards | Yes — canned reply returned | None |
| Registry resolution | Agent Registry | Yes — 400 on missing entry | None |
| Memory load | Memory Manager | No — empty state if Cosmos unavailable | Empty dict |
| RAG retrieval | Retriever | No — empty chunks passed to prompt | Empty chunks section |
| Instruction load | Instruction Store | No — falls back to compiled constant | Module-level string |
| Skill load | Skill Selector | No — skills omitted from prompt | No skills injected |
| LLM stream | LLM Wrapper | Yes — 500 on LLM error | None |
| State extraction | State Extractor | No — background task; empty dict on failure | `{}` |
| Memory save | Memory Manager | No — background task; logs on failure | Silent warning |

---

## 3. Folder Structure

### 3.1 Top-Level Layout

```
{project-root}/
├── framework/                  # Reusable framework package (zero domain imports)
│   ├── api/                    # FastAPI app factory and core route handlers
│   ├── graph/                  # LangGraph supervisor and workstream graph builders
│   ├── agents/                 # Base agent mechanics: retrieval, prompt building, streaming
│   ├── memory/                 # Conversation and state persistence (Cosmos)
│   ├── workflow/               # Pipeline state machine and notifications
│   ├── auth/                   # Entra ID JWT middleware and RBAC
│   ├── infra/                  # Lazy Azure client singletons
│   ├── instructions/           # Versioned instruction store (Blob + Cosmos + cache)
│   ├── security/               # Injection detection and response sanitisation
│   ├── web/                    # Domain-allowlisted web fetcher
│   └── settings.py             # BaseAgentSettings dataclass
│
├── app/                        # Domain application package (imports from framework)
│   ├── agents/                 # Domain agent modules (system prompts, skill routing)
│   ├── instructions/           # Domain skill .md files and system prompt files
│   ├── routers/                # Domain-specific API routes
│   ├── graph_registry.py       # WORKSTREAM_GRAPHS dict
│   ├── stream_registry.py      # _STREAM_REGISTRY dict
│   ├── workflow_config.py      # PipelineConfig, stage names, node labels
│   ├── memory_config.py        # MemoryConfig, step maps, phase prerequisites
│   ├── settings.py             # AppSettings extends BaseAgentSettings
│   └── main.py                 # FastAPI app wiring and startup
│
├── ingest/                     # Document ingestion pipeline (Azure Function)
│   ├── function_app.py         # HTTP trigger entry point
│   ├── ingest.py               # Chunk, embed, index to AI Search
│   ├── extractors.py           # File-type text extractors
│   └── requirements.txt
│
├── frontend/                   # React SPA
│   ├── src/
│   │   ├── components/         # Chat renderer, workflow panel, form renderer
│   │   ├── auth/               # MSAL config and current user hook
│   │   └── store/              # Global state management
│   └── package.json
│
└── docs/
    └── ARCHITECTURE.md         # This document
```

### 3.2 Framework Folder Details

| Folder | Purpose | Key Files | Dependencies |
|---|---|---|---|
| `framework/api/` | FastAPI app factory; mounts routers, middleware, SSE streaming endpoint | `app_factory.py`, `chat_stream.py` | `framework/auth`, `framework/security`, `framework/graph` |
| `framework/graph/` | LangGraph supervisor and generic workstream sub-graph builder | `supervisor.py`, `workstream.py`, `state.py` | `langgraph`, `framework/settings` |
| `framework/agents/` | RAG retrieval, prompt assembly, async LLM streaming, state extraction | `retriever.py`, `prompt_builder.py`, `llm_client.py`, `state_extractor.py` | `langchain_anthropic`, `langchain_openai`, `azure.search` |
| `framework/memory/` | Cosmos conversation persistence; multi-scope session/state/shared docs | `store.py`, `session.py`, `shared.py` | `azure.cosmos`, `framework/infra` |
| `framework/workflow/` | Pipeline state machine, stage transitions, notification events | `pipeline.py`, `notifications.py` | `azure.cosmos`, `framework/infra` |
| `framework/auth/` | Entra JWKS fetch, JWT decode, RBAC middleware, `current_user()` | `entra.py`, `middleware.py` | `PyJWT`, `fastapi` |
| `framework/infra/` | Lazy Azure client singleton registry | `singletons.py`, `cosmos.py` | `azure.cosmos`, `azure.storage.blob`, `azure.search` |
| `framework/instructions/` | Three-tier versioned instruction store (Blob + Cosmos + TTL cache) | `store.py` | `azure.storage.blob`, `azure.cosmos`, `azure.identity` |
| `framework/security/` | Prompt injection detection, response token sanitisation | `guards.py` | `re` |
| `framework/web/` | Domain-allowlisted URL fetcher and vendor doc injector | `fetcher.py` | `urllib`, `html.parser` |

### 3.3 Application Layer Folder Details

| Folder | Purpose | Should Import From |
|---|---|---|
| `app/agents/` | Per-phase agent modules: system prompts, skill routing, `prepare_context` functions | `framework/agents/`, `framework/instructions/` |
| `app/instructions/` | `.md` files for system prompts and skills (disk or Blob) | N/A (content only) |
| `app/routers/` | Domain REST endpoints (entities, export, knowledge base) | `framework/auth/`, `framework/infra/` |
| `app/graph_registry.py` | Maps workstream name → `build_*_graph()` factory | `framework/graph/`, `app/agents/` |
| `app/stream_registry.py` | Maps (workstream, phase) → `AgentConfig` | `framework/agents/`, `app/agents/` |
| `app/workflow_config.py` | `PipelineConfig` with stage names, node labels, cost template | `framework/workflow/` |
| `app/memory_config.py` | `MemoryConfig` with step maps, phase prerequisites, doc ID scheme | `framework/memory/` |

---

## 4. Core Components

### 4.1 Agent

**Purpose:** Represents a single phase within a domain workflow. Responsible for gathering context, building the prompt, invoking the LLM, and returning an updated state.

**Responsibilities:**
- Declare a system prompt (static or live-loaded from Instruction Store)
- Declare valid step keys for its phase
- Implement `prepare_context(state, settings) -> AgentContext`
- Implement the LangGraph node function `agent_node(state, settings) -> dict`

**Inputs:** `AgentState`, `AgentSettings`  
**Outputs:** Updated `AgentState` fields (messages, decisions, stage_progress, blockers)  
**Dependencies:** `Retriever`, `InstructionStore`, `SkillSelector`, `PromptBuilder`, `LLMWrapper`, `StateExtractor`

**Extension points:**
- Override `prepare_context` to add domain-specific pre-processing (URL enrichment, inventory loading, cross-agent context injection)
- Provide a `get_system_prompt()` callable that supports live hot-reload from Blob Storage
- Provide a `SkillSelector` implementation with domain-specific keyword routing

---

### 4.2 Planner (Supervisor Graph)

**Purpose:** Routes incoming requests to the correct domain sub-graph, then to the correct phase agent, without any domain knowledge.

**Responsibilities:**
- Compile a `StateGraph` from the `WORKSTREAM_GRAPHS` registry
- Apply a conditional edge from `START` that reads `state.routing_key`
- Provide a stub `orchestrator` node for cross-domain queries
- Delegate all domain routing to workstream sub-graphs

**Inputs:** `WORKSTREAM_GRAPHS: dict[str, Callable]`, `AgentSettings`  
**Outputs:** Compiled `CompiledGraph`  
**Dependencies:** `langgraph`, `AgentState`, `AgentSettings`

**Extension points:**
- Add entries to `WORKSTREAM_GRAPHS` — no framework code changes required
- Replace the orchestrator stub with a full cross-domain reasoning agent

---

### 4.3 Skill Registry

**Purpose:** Maps domain concept triggers (step positions, keyword patterns) to skill file content. Determines which skill files are injected into the system prompt for a given turn.

**Responsibilities:**
- Maintain a keyword routing table (`list[tuple[str, list[str]]]`)
- Maintain a step-to-skill map (`dict[str, str]`)
- Select up to `max_skills` skill file stems per turn based on current step and query
- Load selected skill content from disk or Instruction Store (with fallback)

**Inputs:** `query: str`, `stage_progress: dict`, `max_skills: int`  
**Outputs:** `list[tuple[str, str]]` — (skill_name, skill_content) pairs  
**Dependencies:** `InstructionStore` (for live versions), local `Instructions/` directory (for fallback)

**Extension points:**
- The routing table and step map are application-owned; the loading mechanism is framework-owned
- Additional selection strategies (semantic similarity, user role-based) can be plugged in by implementing the `SkillSelector` protocol

---

### 4.4 Skill Interface

A skill is not a class — it is a **Markdown text file** that encodes procedural knowledge for a specific sub-topic. The LLM interprets the skill content as instructions when handling queries in that sub-domain.

**Skill contract:**
- File path: `app/instructions/{Phase}/{SkillName}.md`
- File stem must match the key used in the `SkillRegistry` routing table
- Content: prose instructions, decision trees, output templates, constraint lists
- No executable code
- Optionally mirrored to Blob Storage under a named scope for hot-reload

**Skill injection:** Selected skill texts are concatenated under the `=== AGENT SKILLS ===` section appended to the system prompt before LLM invocation.

---

### 4.5 Instruction Loader

**Purpose:** Retrieves the current active version of any named instruction scope from a three-tier storage hierarchy.

**Responsibilities:**
- Query Cosmos DB for active version metadata (version number, blob path, status)
- Fetch content from Azure Blob Storage using the version metadata
- Cache content in-process with a configurable TTL (default: 300 seconds)
- Return empty string on any failure, enabling graceful fallback to compiled constants

**Inputs:** `settings: BaseAgentSettings`, `scope: str`  
**Outputs:** `str` — instruction content, or `""` on failure  
**Dependencies:** `azure.storage.blob`, `azure.cosmos`, `azure.identity`, `threading`, `time`

**Storage layout:**
```
Blob Container: {instructions_container}/
  {scope}/
    v1.md
    v2.md
    v3.md   <- active version

Cosmos Container: {instruction_version_container}/
  {scope_id}: { scope, version: 3, status: "active", blobPath: "prompt-strategy/v3.md", ... }
```

**Extension points:**
- Scope names are entirely application-defined
- TTL is configurable per deployment via environment variable
- The three-tier pattern (global → domain → sub-domain) is implemented by calling `get_active_content` for each tier and concatenating results

---

### 4.6 Prompt Builder

**Purpose:** Assembles the complete multi-part message list in the format required by the LLM provider. Enforces a consistent section ordering and injects all framework-standard context.

**Responsibilities:**
- Construct the system message with Anthropic prompt-caching headers
- Inject conversation history, stripping framework-internal metadata blocks (e.g., `<!--SUMMARY-->` markers)
- Assemble the user turn as an ordered sequence of named sections
- Append the output protocol and behavioural instruction blocks
- Return a `list[dict]` in provider message format

**Inputs:**
- `query: str`
- `chunks: list[dict]` — RAG results
- `system_prompt: str` — resolved by agent
- `history: list[dict]` — from memory
- `state_sections: list[PromptSection]` — domain-injected context sections
- `config: PromptConfig` — formatting rules, behavioural guidelines, output protocol

**Outputs:** `list[dict]` — Anthropic-compatible message list  
**Dependencies:** `re` (summary block stripping), `json`

**Section ordering (invariant):**
1. System message (with cache header)
2. History turns (filtered)
3. Current state section (decisions + progress + blockers)
4. Cross-agent shared context section (optional)
5. Pre-computed data section (optional, domain-provided)
6. RAG knowledge base section
7. User query + formatting rules + output protocol + behavioural guidelines

---

### 4.7 Context Builder

**Purpose:** Orchestrates all pre-LLM data gathering for a single turn: retrieval, inventory/pre-computed context loading, skill selection, and system prompt resolution.

**Responsibilities:**
- Call `Retriever.retrieve()` to get RAG chunks
- Call the application-provided pre-computed context loader (optional)
- Call `SkillSelector.select()` to get skill texts
- Call the application-provided `get_system_prompt()` to resolve the active prompt
- Assemble and return an `AgentContext` dataclass

**Inputs:** `AgentState`, `AgentSettings`, application-provided callables  
**Outputs:** `AgentContext`  
**Dependencies:** `Retriever`, `InstructionStore`, `SkillSelector`

---

### 4.8 Memory Manager

**Purpose:** Provides durable, multi-scope conversation persistence backed by Cosmos DB. Manages three document types per user+entity+scope combination.

**Document scopes:**

| Document Type | Key | Contains | Lifecycle |
|---|---|---|---|
| Session doc | `{user_key}:{scope}-{sub_scope}:{session_id}` | Serialised message history | Deleted when session is cleared |
| State doc | `{user_key}:{scope}-{sub_scope}:state` | `decisions`, `stage_progress`, `blockers`, `inventory` | Never deleted; survives session resets |
| Shared doc | `{user_key}:{scope}-shared` | Cross-phase `decisions`, `blockers`, `source_map` | Never deleted; readable by all phase agents |

**Responsibilities:**
- `load_memory()` — reads all three doc types; returns merged state dict
- `save_memory()` — upserts session doc and state doc
- `load_shared_memory()` / `save_shared_memory()` — cross-agent shared context
- Serialise/deserialise LangChain message objects
- Handle Cosmos 404 gracefully (return empty state)

**Inputs:** `entity_id`, `scope`, `sub_scope`, `user_key`, `session_id`, `MemoryConfig`  
**Outputs:** `dict` containing `messages`, `decisions`, `stage_progress`, `blockers`, `inventory`  
**Dependencies:** `azure.cosmos`, `framework/infra`

**Extension points:**
- `MemoryConfig.doc_id_scheme` — callable that constructs Cosmos document IDs; application-defined
- `MemoryConfig.default_step_map` — initial `stage_progress` dict; application-defined

---

### 4.9 Tool Registry

**Purpose:** Manages the registration and resolution of external tools (web fetchers, calculators, API connectors) available to agents.

> In the current implementation the only tool is the domain-allowlisted web fetcher. The registry pattern exists implicitly in the `FETCH_PAGE_TOOL` Anthropic schema dict. For multi-tool applications, this should become an explicit registry.

**Interface:**
```
ToolRegistry:
  register(tool_name: str, schema: dict, executor: Callable) -> None
  resolve(tool_name: str) -> (schema, executor)
  all_schemas() -> list[dict]   # passed to LLM tool_use parameter
```

**Dependencies:** Application-provided tool executors; `langchain_anthropic` for tool-use loop (if applicable)

---

### 4.10 Tool Executor

**Purpose:** Executes a resolved tool call, validates inputs against the tool schema, handles errors, and returns a result string.

**Responsibilities:**
- Validate the URL or input against a domain-specific allowlist before execution
- Fetch and parse content (HTML extraction, JSON parsing, etc.)
- Handle connection errors, timeouts, and encoding errors
- Return empty string on failure rather than raising (to keep the agent turn alive)

**Inputs:** Tool name, tool input dict  
**Outputs:** `str` — tool result text  
**Dependencies:** `urllib.request`, `html.parser`; application provides the allowlist and vendor registry

---

### 4.11 LLM Wrapper

**Purpose:** Wraps the underlying LLM client to provide a consistent streaming interface, token usage extraction, and prompt-caching configuration.

**Responsibilities:**
- Instantiate `ChatAnthropic` (or any `langchain` chat model) from settings
- Provide `astream_llm(settings, messages) -> AsyncGenerator[str, None]`
- Apply provider-specific beta headers (e.g., Anthropic prompt-caching)
- Extract token usage from response metadata for logging
- Yield string tokens; skip empty chunks

**Inputs:** `BaseAgentSettings`, `list[dict]` message list  
**Outputs:** `AsyncGenerator[str, None]`  
**Dependencies:** `langchain_anthropic.ChatAnthropic`, `BaseAgentSettings`

**Extension points:** Swap the underlying provider by replacing `ChatAnthropic` with any LangChain-compatible chat model. The `astream_llm` signature does not change.

---

### 4.12 Configuration

**Purpose:** Provides a single, typed, immutable configuration object populated from environment variables.

**Structure:**

```
BaseAgentSettings (frozen dataclass)
├── LLMSettings
│   ├── chat_endpoint, chat_model, api_key
│   └── temperature, max_tokens
├── EmbeddingSettings
│   ├── endpoint, api_key, api_version, deployment
├── SearchSettings
│   ├── endpoint, admin_key, index_prefix, top_k
├── StorageSettings
│   ├── cosmos_endpoint, cosmos_key, cosmos_db
│   ├── blob_account_url, instructions_container
│   └── container names (application-provided)
└── AuthSettings
    ├── entra_tenant_id, entra_api_audience
    ├── allowed_audiences, allowed_roles
    └── bypass_mode (dev only)
```

**Application extends** `BaseAgentSettings` by subclassing and adding domain-specific fields.

---

### 4.13 Logging and Observability

**Responsibilities:**
- Standard Python `logging` at module level via `logger = logging.getLogger(__name__)`
- Structured usage event logging to Cosmos DB `usage-events` container: token counts, user OID, phase, entity ID, action type
- Security audit logging: instruction leak detections, injection attempts (WARNING level, no content)
- LangChain run naming via `config={"run_name": "..."}` for traceability in LangSmith

**What is never logged:**
- Instruction or skill content
- JWT tokens or credentials
- User query content at WARNING/ERROR level

---

### 4.14 Utilities

| Utility | Location | Description |
|---|---|---|
| `_normalise_index_name()` | `framework/agents/retriever.py` | Sanitises arbitrary strings to valid Azure Search index names |
| `_serialise_messages()` | `framework/memory/store.py` | Converts LangChain message objects to plain dicts for Cosmos storage |
| `_slim_inventory_for_storage()` | `framework/memory/store.py` | Truncates large pre-computed context items before Cosmos upsert |
| `_blocker_is_resolved()` | Application layer | Fuzzy-match blocker text against resolved list (difflib, threshold 0.82) |
| `_prune_state_for_session()` | `framework/memory/store.py` | Removes framework-internal fields from state before persisting |

---

## 5. Skill Architecture

### 5.1 Skill Lifecycle

```mermaid
flowchart LR
    A[Author writes\nSkill .md file] --> B[File placed in\napp/instructions/Phase/]
    B --> C{Production\ndeployment?}
    C -->|Yes| D[Upload to Blob Storage\nvia /instructions POST]
    C -->|No| E[Loaded from disk\nat runtime]
    D --> F[Cosmos version metadata\nstored with status=active]
    E --> G[Skill available\nfor selection]
    F --> G
    G --> H[Turn arrives with\nmatching query or step]
    H --> I[SkillSelector.select\nreturns skill text]
    I --> J[Text appended to\nsystem prompt]
    J --> K[LLM uses skill\nknowledge in response]
    K --> L{Update needed?}
    L -->|Yes| D
    L -->|No| G
```

### 5.2 Skill Interface

A skill is a **text contract** between the author and the LLM, not a code interface. It must:

- Be self-contained — assume no other skill is injected alongside it
- Use clear headings and numbered steps
- State explicit output expectations ("Output: ...")
- Include decision criteria and constraint thresholds
- Avoid references to other skill files by name

### 5.3 Skill Registration

Skills are registered in two places in the application layer:

**Keyword routing table** (for query-triggered selection):
```
_SKILL_ROUTING = [
    ("SkillFileName", ["keyword1", "keyword2", "phrase match"]),
    ...
]
```

**Step-to-skill map** (for workflow-position-based selection):
```
_STEP_SKILL_MAP = {
    "step_key_in_stage_progress": "SkillFileName",
    ...
}
```

The framework `SkillSelector` reads both; the application populates both.

### 5.4 Skill Execution

The framework does not "execute" skills. Skill text is injected into the system prompt under `=== AGENT SKILLS ===`. The LLM interprets and applies the skill content during response generation. This means:

- Skills cannot have side effects
- Skills cannot call APIs or tools directly
- Skills influence LLM output quality, not execution flow

### 5.5 How to Create a New Skill

1. Create `app/instructions/{Phase}/Skill_{TopicName}.md`
2. Write the skill as structured Markdown: purpose, inputs required, decision logic, output format
3. Add a keyword trigger list to `_SKILL_ROUTING` in the relevant agent module
4. Optionally add a step mapping to `_STEP_SKILL_MAP`
5. Optionally upload to Blob Storage via the admin API for production hot-reload capability

### 5.6 Best Practices

| Practice | Rationale |
|---|---|
| One skill per sub-topic | Prevents skill bloat and ensures precise routing |
| State outputs explicitly | "Output: [artifact name]" gives the LLM a clear deliverable target |
| Include constraint thresholds | Hard limits (e.g., volume thresholds that change tool recommendations) must be explicit |
| Keep skills under 2,000 tokens | Token budget; `max_skills = 3` is the default ceiling |
| Version skills in Blob | Allows content updates without code deployments |
| Name files with `Skill_` prefix | Distinguishes skill files from system prompt files in the `Instructions/` directory |

---

## 6. Instruction System

### 6.1 Instruction File Organisation

```
app/instructions/
├── Shared.md                   # Global rules, tone, formatting — injected into all agents
├── {Phase}/
│   ├── {Phase}AgentSkills.md   # Master skills overview for this phase agent
│   ├── Skill_{TopicA}.md
│   ├── Skill_{TopicB}.md
│   └── Skill_{TopicC}.md
└── pptx_structure_prompt.py    # Export-specific prompt fragment (domain-specific)
```

### 6.2 Loading Mechanism

The framework resolves instructions in this priority order for each scope:

```mermaid
flowchart TD
    A[Request for scope content] --> B{In-memory cache?\nTTL not expired?}
    B -->|Yes| C[Return cached content]
    B -->|No| D[Query Cosmos for\nactive version metadata]
    D --> E{Active version\nexists?}
    E -->|No| F[Return empty string\nAgent falls back to compiled constant]
    E -->|Yes| G[Fetch blob:\ncontainer/{scope}/v{N}.md]
    G --> H{Fetch succeeded?}
    H -->|No| F
    H -->|Yes| I[Store in cache\nwith TTL]
    I --> C
```

### 6.3 Composition Strategy

Each agent's system prompt is composed at call time from up to four layers:

| Layer | Source | Purpose |
|---|---|---|
| **L1 — Agent prompt** | `get_active_content("prompt-{phase}")` or compiled constant | Core agent identity, workflow steps, output format |
| **L2 — Shared rules** | `get_active_content("skill-global-shared")` or `Shared.md` | Universal tone, formatting, progressive disclosure rules |
| **L3 — Agent skills** | Selected skill files (≤ `max_skills`) | Sub-topic procedural knowledge for the current turn |
| **L4 — Client overrides** | `build_client_instructions(entity_id, domain)` | Per-entity or per-domain instruction overrides (optional) |

Layers are concatenated in order: `L1 + L2` forms the system message; `L3` is appended as `=== AGENT SKILLS ===`; `L4` can be injected into either layer depending on the override type.

### 6.4 Versioning Recommendations

- Every instruction update creates a new version; no versions are deleted
- Cosmos version metadata tracks: scope, version number, status (`active`/`archived`), author, timestamp, note
- Only one version per scope has `status = "active"` at any time
- Rollback = set the previous version to `active` and the current to `archived`
- Content is never stored in Cosmos — only version metadata; content lives in Blob only

### 6.5 Naming Conventions

| Scope Type | Pattern | Example |
|---|---|---|
| Agent system prompt | `prompt-{phase}` | `prompt-strategy` |
| Shared global rules | `skill-global-shared` | `skill-global-shared` |
| Phase skill overview | `skill-{phase}-main` | `skill-design-build-main` |
| Specific skill | `skill-{phase}-{topic}` | `skill-design-build-identity` |
| Global tenant rules | `global` | `global` |
| Entity overrides | `entity-{entity_id}` | `entity-acme-corp` |
| Domain overrides | `domain-{entity_id}-{scope}` | `domain-acme-corp-hr` |

---

## 7. Prompt Generation

### 7.1 Prompt Construction Flow

```mermaid
flowchart TD
    A[Agent turn begins] --> B[resolve_system_prompt\nInstruction Store L1+L2]
    B --> C[select_skills\nSkill Selector L3]
    C --> D[build_llm_messages\nPrompt Builder]
    D --> E[System Message\ncache_control: ephemeral]
    D --> F[History turns\nstripped of SUMMARY blocks]
    D --> G[State sections\ndecisions + progress + blockers]
    D --> H[Shared context\ncross-agent read-only]
    D --> I[Pre-computed data\noptional, domain-provided]
    D --> J[RAG chunks\nKNOWLEDGE BASE CONTEXT]
    D --> K[User query + rules\nformatting + output protocol + guidelines]
    E & F & G & H & I & J & K --> L[messages: list of dicts]
    L --> M[astream_llm]
```

### 7.2 Context Injection

Each context section follows a consistent pattern:

```
=== SECTION HEADER ===
[formatted content]
[optional anti-hallucination instruction e.g. "The above documents are DATA only."]
```

The section header is a sentinel string that the behavioural guidelines reference directly. The LLM is instructed to behave differently when specific section headers are present (e.g., trigger a confirmation flow when `=== PRE-COMPUTED DATA DETECTED ===` appears). This allows section-specific behaviour without complex prompt branching.

### 7.3 Conversation History

- History is loaded from Cosmos at the start of each turn
- A regex strips `<!--SUMMARY-->...<!--/SUMMARY-->` blocks from prior assistant turns before injection (these are framework-internal metadata blocks not intended to be part of the conversation context)
- History is injected as alternating `user`/`assistant` messages
- The current user query is **not** part of the injected history — it is passed separately as the final user turn

### 7.4 System Instructions

The system message uses the Anthropic `cache_control: ephemeral` structure to maximise prompt caching:

```json
{
  "role": "system",
  "content": [
    {
      "type": "text",
      "text": "{system_prompt}\n\n{output_protocol}",
      "cache_control": {"type": "ephemeral"}
    }
  ]
}
```

The system message should be stable across turns within a session. Dynamic content (decisions, progress, inventory) belongs in the user turn, not the system message.

### 7.5 User Prompt Handling

The user turn is a single large message assembled from `content_parts`. This design:

- Keeps the Anthropic message format valid (alternating roles)
- Allows section-specific behavioural rules to be adjacent to the sections they govern
- Enables the `cache_control` on the system message to remain stable

---

## 8. Tool Architecture

### 8.1 Tool Registration

Tools are registered as Anthropic-compatible schema dicts plus executor callables. In the current architecture, tool invocation uses a single-turn pattern (the agent decides to use a tool based on context, not via an explicit Anthropic tool-use loop). A full tool-use loop should be adopted when multiple tools need to be selected dynamically per turn.

```
ToolRegistry.register(
    name     = "fetch_page",
    schema   = { "name": ..., "description": ..., "input_schema": {...} },
    executor = WebFetcher(config).execute_fetch,
)
```

### 8.2 Invocation Flow

**Current pattern (implicit — pre-fetch before LLM):**
```
1. Agent identifies URL-bearing chunks in RAG results
2. Calls enrich_url_chunks(chunks) — fetches URLs, replaces chunk content
3. Calls route_vendor_docs(query) — LLM selects relevant vendor URLs
4. Injects fetched content as synthetic RAG chunks
5. Proceeds to prompt assembly with enriched chunks
```

**Recommended pattern for multi-tool (explicit tool-use loop):**
```
1. Build initial messages with all_tool_schemas in tool_choice parameter
2. Invoke LLM — may return tool_use block
3. If tool_use block: execute tool, append result as tool_result message
4. Re-invoke LLM with updated messages
5. Repeat until no tool_use block (or max_iterations reached)
6. Return final text response
```

### 8.3 Error Handling

- Tool executors catch all exceptions and return empty string
- Empty tool results are passed as-is (the LLM is told no content was found)
- Timeout is configurable per tool
- Domain allowlist validation happens before any network call; violations return empty string and log a warning

### 8.4 Retry Strategy

The current implementation has no LLM-level retry. For production hardening:

- Wrap `astream_llm` with `tenacity` exponential backoff for transient 429/503 errors
- Retry limit: 3 attempts, base delay 1s, max delay 10s
- Do not retry 400 (bad request) or 401 (auth) errors

The `ingest` pipeline already uses `tenacity` for embedding and index upsert operations as a reference pattern.

### 8.5 Tool Abstraction

```
Protocol: ToolExecutor
  execute(input: dict) -> str
  # Raises: ToolValidationError (input fails schema check)
  # Returns: "" on network/parsing failure (never raises in production path)
```

---

## 9. Configuration

### 9.1 Environment Variables

All configuration is environment-variable-driven. The `BaseAgentSettings` frozen dataclass reads values at instantiation time. The singleton `_get_settings()` ensures it is built once.

**Core variables required for framework operation:**

| Variable | Used By | Required |
|---|---|---|
| `AZURE_OPENAI_CHAT_ENDPOINT` | LLM Wrapper | Yes |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | LLM Wrapper | Yes |
| `AZURE_OPENAI_API_KEY` | LLM Wrapper, Embeddings | Yes |
| `AZURE_OPENAI_ENDPOINT` | Embeddings | Yes |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embeddings / Retriever | Yes |
| `AZURE_OPENAI_API_VERSION` | Embeddings | Yes |
| `AZURE_SEARCH_ENDPOINT` | Retriever | Yes |
| `AZURE_SEARCH_ADMIN_KEY` | Retriever | Yes |
| `AZURE_COSMOS_ENDPOINT` | Memory, Workflow, Instructions | No (fallback mode) |
| `AZURE_COSMOS_KEY` | Memory, Workflow, Instructions | No (fallback mode) |
| `COSMOS_DB_NAME` | Memory, Workflow, Instructions | No |
| `AZURE_INSTRUCTIONS_ACCOUNT_URL` | Instruction Store | No (file fallback) |
| `ENTRA_TENANT_ID` | Auth | If `ENTRA_AUTH_ENABLED=true` |
| `ENTRA_API_AUDIENCE` | Auth | If `ENTRA_AUTH_ENABLED=true` |
| `AUTH_BYPASS_MODE` | Auth | Dev only |

### 9.2 Model Configuration

| Parameter | Default | Notes |
|---|---|---|
| `temperature` | `0` | Hardcoded — deterministic outputs required for professional workflows |
| `max_tokens` (generation) | `8000` | Configurable via `AppSettings` |
| `max_tokens` (extraction) | `2048` | Smaller model call for post-generation parsing |
| `top_k` (retrieval) | `5` | Configurable via `RETRIEVAL_TOP_K` env var |
| `instruction_cache_ttl` | `300` seconds | Configurable via `INSTRUCTION_CACHE_TTL` |

### 9.3 Runtime Configuration

The following items are injected at app startup rather than hardcoded:

- `WORKSTREAM_GRAPHS` — registered in `app/graph_registry.py`, mounted in `app/main.py`
- `STREAM_REGISTRY` — registered in `app/stream_registry.py`, mounted in `app/main.py`
- `PipelineConfig` — passed to `workflow.pipeline.seed_workflow()` and `advance_state()`
- `MemoryConfig` — passed to all `memory.store.*` functions
- `AuthConfig` — passed to `auth.build_auth_middleware()`
- `ExtractionConfig` — passed to `state_extractor.extract_state_updates()`
- Scope catalog for the instructions admin router — passed to `create_instructions_router()`

---

## 10. Design Patterns

### 10.1 Registry Pattern

**Where used:** `WORKSTREAM_GRAPHS`, `M365_PHASE_AGENTS`, `_STREAM_REGISTRY`, `ToolRegistry`  
**Why:** Adding a new domain, phase agent, or tool requires only adding a dict entry. No existing framework code changes. The registry is the single extension point for all new capabilities.

### 10.2 Factory Method Pattern

**Where used:** `build_supervisor_graph()`, `build_workstream_graph()`, `create_instructions_router()`  
**Why:** Each factory encapsulates the construction complexity of a LangGraph `StateGraph` or FastAPI `APIRouter`. Callers receive a configured product without knowing how it was built. Multiple workstream graphs can be produced from the same factory using different phase agent registries.

### 10.3 Strategy Pattern

**Where used:** `SkillSelector` (keyword vs. step-based routing), `MemoryConfig.doc_id_scheme` (application-defined ID generation), `ExtractionConfig.normaliser`  
**Why:** The selection algorithm varies by domain and agent type, but the interface is uniform. The framework calls the strategy through an abstract interface; the application provides the concrete implementation.

### 10.4 Singleton (Lazy Initialisation) Pattern

**Where used:** `_get_settings()`, `_get_graph()`, `_get_cosmos_container()` in `framework/infra/singletons.py`  
**Why:** Azure SDK clients are expensive to initialise. Module-level `None` sentinels with a guard initialise on first call and reuse on all subsequent calls. Python's GIL provides sufficient thread safety for the attribute assignment.

### 10.5 Template Method Pattern

**Where used:** `build_llm_messages()` — the prompt assembly skeleton  
**Why:** The order of sections in the prompt (system → history → state → data → chunks → query) is invariant. The content of each section varies per domain. The template method defines the skeleton; domain-provided `PromptSection` objects fill the variable parts.

### 10.6 Builder Pattern

**Where used:** `AgentContext` construction in `ContextBuilder`, prompt `content_parts` list assembly  
**Why:** The final LLM message list is constructed incrementally from many optional components. A builder accumulates parts and produces the final object in one step, avoiding a constructor with 10+ optional parameters.

### 10.7 Chain of Responsibility Pattern

**Where used:** Instruction loading fallback chain: Blob Storage → local file → compiled constant  
**Why:** Each handler in the chain attempts to satisfy the request. If it cannot (missing config, network failure), it passes to the next handler. The caller never needs to know which handler succeeded.

### 10.8 Adapter Pattern

**Where used:** LLM history normalisation in `build_llm_messages()` — handles both `dict` format and LangChain `HumanMessage`/`AIMessage` objects  
**Why:** The memory layer stores messages as plain dicts; LangChain may return typed objects. The adapter normalises both shapes into the Anthropic message format.

### 10.9 Observer Pattern (Lightweight)

**Where used:** `_add_notification()` in `workflow/notifications.py` — called whenever workflow state advances; consumed by the `/notifications` endpoint  
**Why:** Workflow state transitions need to notify multiple consumers (UI notification bell, audit log) without the workflow module knowing about them. Writing to Cosmos and letting consumers poll is the async-safe equivalent of event emission.

### 10.10 Barrel Export Pattern

**Where used:** `core/deps.py` re-exports everything from sub-modules  
**Why:** Provides a stable single import surface. Consumers do not depend on the internal module structure. Refactoring internals does not break import paths.

---

## 11. Reusable Framework Components

| Component | Responsibility | Generic | Reusable | Key Dependencies |
|---|---|---|---|---|
| `BaseAgentSettings` | Typed env-var configuration | ✅ | ✅ | `os`, `dataclasses` |
| `BaseAgentState` | Minimal LangGraph state TypedDict | ✅ | ✅ | `langgraph` |
| `build_supervisor_graph()` | Top-level workstream router | ✅ | ✅ | `langgraph` |
| `build_workstream_graph()` | Per-workstream phase router | ✅ | ✅ | `langgraph` |
| `astream_llm()` | Async token streaming from LLM | ✅ | ✅ | `langchain_anthropic` |
| `retrieve()` | Hybrid RAG (vector + keyword) | ✅ | ✅ | `azure.search`, `langchain_openai` |
| `build_llm_messages()` skeleton | Prompt assembly template | ✅ | ✅ | `re`, `json` |
| `extract_state_updates()` mechanism | JSON parsing + key validation | ✅ | ✅ | `langchain_anthropic` |
| `instruction_store.py` | Three-tier versioned content store | ✅ | ✅ | `azure.storage.blob`, `azure.cosmos` |
| `framework/memory/store.py` | Cosmos conversation persistence | ✅ | ✅ | `azure.cosmos` |
| `framework/workflow/pipeline.py` | State machine mechanics | ✅ | ✅ | `azure.cosmos` |
| `framework/auth/entra.py` | JWT validation + RBAC middleware | ✅ | ✅ | `PyJWT`, `fastapi` |
| `framework/infra/singletons.py` | Lazy Azure client factory | ✅ | ✅ | Azure SDKs |
| `framework/security/guards.py` | Injection detection + sanitisation | ✅ | ✅ | `re` |
| `framework/web/fetcher.py` mechanics | URL fetch + HTML extraction | ✅ | ✅ | `urllib`, `html.parser` |
| `_INTERACTIVE_OUTPUT_PROTOCOL` block schemas | Rich UI output specification | ✅ | ✅ | None |
| `routers/instructions.py` mechanics | Instruction version admin API | ✅ | ✅ | `fastapi`, `instruction_store` |
| `ExtractionConfig` extraction prompt | Domain decision vocabulary | ❌ | ❌ | Domain-specific |
| `PromptConfig.response_guidelines` | Domain behavioural rules | ❌ | ❌ | Domain-specific |
| `app/agents/*.py` system prompts | Domain agent identity + workflow | ❌ | ❌ | Domain-specific |
| `app/instructions/**/*.md` | Domain skill and prompt content | ❌ | ❌ | Domain-specific |
| `MemoryConfig` step maps | Domain step key → status maps | ❌ | ❌ | Domain-specific |
| `PipelineConfig` stage names | Domain workflow stage topology | ❌ | ❌ | Domain-specific |
| `_SKILL_ROUTING`, `_STEP_SKILL_MAP` | Domain skill routing tables | ❌ | ❌ | Domain-specific |
| `FETCH_ALLOWED_DOMAINS`, `VENDOR_DOC_REGISTRY` | Domain-specific external resources | ❌ | ❌ | Domain-specific |
| `allowed_roles` set | Organisation-specific RBAC roles | ❌ | ❌ | Domain-specific |

---

## 12. Business Layer

The following components are specific to a particular domain and must **not** be included in the framework package.

| Component | Domain | Why It Must Stay in the Application Layer |
|---|---|---|
| `SYSTEM_PROMPT` strings in each agent module | Any | Encodes domain persona, workflow steps, priority framework, scope boundaries |
| All `Instructions/**/*.md` skill files | Any | Encodes domain-specific procedural knowledge |
| `_VALID_STEPS` lists | Any | Domain lifecycle step sequences (e.g., M&A Strategy Steps 00–08) |
| `_M365_*_STEPS`, `_ENDPOINT_*_STEPS` etc. | M&A/M365 | Domain step-key-to-status initialisation maps |
| `_SKILL_ROUTING`, `_STEP_SKILL_MAP` | Any | Domain keyword-to-skill and step-to-skill mappings |
| `extract_memory_updates()` extraction prompt | Any | Contains domain decision keys, step criteria, blocker patterns |
| `_build_llm_messages()` response guidelines | Any | Domain behavioural rules for INVENTORY, DEAL STATE, seller alignment, etc. |
| `_STREAM_REGISTRY` content | Any | Maps domain-specific (workstream, phase) pairs to agent configs |
| `WORKSTREAM_GRAPHS` entries | Any | Domain workstream name → sub-graph factory mapping |
| `_WORKFLOW_STAGES` content | Any | Domain pipeline stage names |
| `_seed_workflow()` hardcoded node labels | Any | Domain agent display names, task descriptions, cost breakdown categories |
| `_CANONICAL_NODE_LABELS`, `_CANONICAL_NODE_AGENTS` | M&A | Domain-specific node schema |
| `_PHASE_PREREQUISITES`, `_PHASE_GATE_CRITERIA` | Any | Domain phase ordering rules |
| `_AGENT_DISPLAY_NAMES` | Any | Domain agent names displayed in UI |
| `routers/deals.py` | M&A | Deal entity CRUD, SharePoint deal folder structure |
| `routers/export.py` | M&A | PDF/PPTX templates for M&A strategy deliverables |
| `project_plan_generator.py` | M&A | Golden project plan Excel template generation |
| `core/deals.py` | M&A | SharePoint/ADLS deal catalog, deal metadata schema |
| Inventory section in `_build_llm_messages()` | M&A | M365 CSV/XLSX confirmation workflow tied to `00_deal_context` step key |
| `_INTERACTIVE_OUTPUT_PROTOCOL` STRATEGY WIDGET TEMPLATE | M&A | M&A-specific dense report layout description |
| `_INTERACTIVE_OUTPUT_PROTOCOL` M365 chat usage rules | M&A/M365 | M365-specific block suppression rules |
| `FETCH_ALLOWED_DOMAINS` | M&A | Migration tooling vendor domains |
| `VENDOR_DOC_REGISTRY` | M&A | Migration tool documentation URLs |

---

## 13. Dependency Graph

```mermaid
graph TD
    subgraph App["Application Layer"]
        AppSettings[AppSettings]
        AppState[AppAgentState]
        AgentModules[Agent Modules]
        StreamRegistry[Stream Registry]
        GraphRegistry[Graph Registry]
        WorkflowCfg[PipelineConfig]
        MemoryCfg[MemoryConfig]
        ExtrCfg[ExtractionConfig]
        InstructionFiles[Instruction .md Files]
        AppRouters[Domain Routers]
    end

    subgraph Framework["Framework Layer"]
        subgraph API["framework/api/"]
            AppFactory[app_factory.py]
            ChatStream[chat_stream.py]
        end
        subgraph Graph["framework/graph/"]
            Supervisor[supervisor.py]
            WorkstreamG[workstream.py]
            BaseState[state.py]
        end
        subgraph Agents["framework/agents/"]
            Retriever[retriever.py]
            PromptBuilder[prompt_builder.py]
            LLMClient[llm_client.py]
            StateExtractor[state_extractor.py]
        end
        subgraph Memory["framework/memory/"]
            MemStore[store.py]
            SharedMem[shared.py]
        end
        subgraph Workflow["framework/workflow/"]
            Pipeline[pipeline.py]
            Notifications[notifications.py]
        end
        subgraph Auth["framework/auth/"]
            Entra[entra.py]
            Middleware[middleware.py]
        end
        subgraph Infra["framework/infra/"]
            Singletons[singletons.py]
        end
        InstructionStore[instruction_store.py]
        Security[security/guards.py]
        WebFetcher[web/fetcher.py]
        BaseSettings[settings.py]
    end

    subgraph Azure["Azure Services"]
        CosmosDB[(Cosmos DB)]
        BlobStorage[(Blob Storage)]
        AISearch[(Azure AI Search)]
        EntraID[(Entra ID JWKS)]
    end

    subgraph LLM["LLM / Embedding"]
        Anthropic[(Claude\nChatAnthropic)]
        AOAI[(Azure OpenAI\nEmbeddings)]
    end

    AppSettings --> BaseSettings
    AppState --> BaseState
    AgentModules --> Retriever
    AgentModules --> PromptBuilder
    AgentModules --> LLMClient
    AgentModules --> StateExtractor
    AgentModules --> InstructionStore
    StreamRegistry --> AgentModules
    StreamRegistry --> ChatStream
    GraphRegistry --> Supervisor
    WorkflowCfg --> Pipeline
    MemoryCfg --> MemStore
    ExtrCfg --> StateExtractor
    InstructionFiles --> InstructionStore
    AppRouters --> MemStore

    AppFactory --> Middleware
    AppFactory --> Security
    AppFactory --> ChatStream
    Supervisor --> WorkstreamG
    WorkstreamG --> AgentModules
    ChatStream --> MemStore
    ChatStream --> SharedMem
    ChatStream --> Pipeline
    PromptBuilder --> InstructionStore
    Singletons --> CosmosDB
    Singletons --> BlobStorage
    MemStore --> Singletons
    SharedMem --> Singletons
    Pipeline --> Singletons
    InstructionStore --> Singletons
    Entra --> EntraID
    Middleware --> Entra

    Retriever --> AISearch
    Retriever --> AOAI
    InstructionStore --> BlobStorage
    InstructionStore --> CosmosDB

    LLMClient --> Anthropic
    StateExtractor --> Anthropic
```

---

## 14. Extension Guide

### 14.1 Adding a New Skill

1. Create `app/instructions/{Phase}/Skill_{Name}.md` with structured content
2. In the relevant agent module, add to `_SKILL_ROUTING`:
   ```python
   ("Skill_Name", ["keyword1", "keyword2"])
   ```
3. Optionally add to `_STEP_SKILL_MAP` for step-position routing:
   ```python
   "step_key": "Skill_Name"
   ```
4. For production hot-reload: upload via `POST /instructions/skill-{phase}-{name}` with `status=active`
5. No framework code changes required

### 14.2 Adding a New Tool

1. Implement the `ToolExecutor` protocol:
   ```python
   class MyTool:
       def execute(self, input: dict) -> str: ...
   ```
2. Define the Anthropic tool schema dict
3. Register with `ToolRegistry.register(name, schema, executor_instance.execute)`
4. Pass `registry.all_schemas()` to the LLM wrapper tool_choice parameter
5. Handle `tool_use` blocks in the agent node's invocation loop
6. No framework code changes required

### 14.3 Adding a New Instruction Set

1. Create `.md` files under `app/instructions/{Domain}/`
2. Upload to Blob Storage under a new scope name via the admin API
3. Reference the scope string in the application's `_kv_get()` calls
4. Add the scope to the application's scope catalog injected into the instructions router
5. No framework code changes required

### 14.4 Adding a New LLM Provider

1. The framework's `astream_llm()` uses `langchain_anthropic.ChatAnthropic`
2. Any LangChain-compatible chat model can be substituted
3. In `framework/agents/llm_client.py`, parameterise the model class:
   ```python
   def build_llm(settings: BaseAgentSettings):
       provider = settings.llm_provider  # "anthropic" | "openai" | "azure_openai"
       if provider == "anthropic":
           return ChatAnthropic(...)
       elif provider == "openai":
           return ChatOpenAI(...)
   ```
4. Add `llm_provider` to `BaseAgentSettings`
5. The `astream_llm()` and `extract_state_updates()` functions use `llm.astream()` and `llm.invoke()` — both are part of the LangChain `BaseChatModel` interface and require no changes

### 14.5 Adding a New Domain (Workstream)

1. Create `app/agents/{domain}_{phase}_agent.py` for each phase, implementing:
   - `SYSTEM_PROMPT: str`
   - `_VALID_STEPS: list[str]`
   - `_get_system_prompt() -> str`
   - `prepare_{domain}_{phase}_context(state, settings) -> AgentContext`
   - `{domain}_{phase}_agent_node(state, settings) -> dict`

2. Create `app/instructions/{Domain}/` with skill files

3. Create `app/graph/{domain}_graph.py`:
   ```python
   DOMAIN_PHASE_AGENTS = {
       "strategy": domain_strategy_agent_node,
       "execution": domain_execution_agent_node,
   }
   def build_{domain}_graph(settings):
       return build_workstream_graph(DOMAIN_PHASE_AGENTS, "strategy", settings)
   ```

4. Register in `app/graph_registry.py`:
   ```python
   WORKSTREAM_GRAPHS["{domain}"] = build_{domain}_graph
   ```

5. Register in `app/stream_registry.py`:
   ```python
   _STREAM_REGISTRY["{domain}"] = {
       "strategy": AgentConfig(prepare_ctx=..., get_prompt=..., valid_steps=..., active_agent="..."),
   }
   ```

6. Provide `MemoryConfig` with domain step maps
7. No framework code changes required

### 14.6 Adding a New API Route

1. Create `app/routers/{domain}_{feature}.py` as a FastAPI `APIRouter`
2. Import framework helpers:
   ```python
   from framework.auth.entra import _current_user
   from framework.infra.singletons import get_cosmos_container
   ```
3. Mount in `app/main.py`:
   ```python
   app.include_router(my_router, prefix="/api/v1")
   ```
4. No framework code changes required

---

## 15. Migration Guidelines

### 15.1 Migration Strategy

Migrate an existing chatbot incrementally using the **Strangler Fig** pattern: the existing application continues to serve traffic while framework components are introduced one at a time, replacing equivalent existing functionality.

### 15.2 Recommended Migration Order

```mermaid
graph LR
    P1[Phase 1\nSettings + Auth] --> P2[Phase 2\nMemory Manager]
    P2 --> P3[Phase 3\nRetriever + LLM Wrapper]
    P3 --> P4[Phase 4\nPrompt Builder]
    P4 --> P5[Phase 5\nInstruction Store]
    P5 --> P6[Phase 6\nGraph + Registry]
    P6 --> P7[Phase 7\nSkill Selector]
    P7 --> P8[Phase 8\nWorkflow Pipeline]
```

### 15.3 Phase-by-Phase Guidance

**Phase 1 — Settings + Auth**  
Replace ad-hoc config dicts with `BaseAgentSettings`. Replace custom JWT logic with `framework/auth/entra.py`. This change is non-breaking; the existing app can import from the new module immediately.

**Phase 2 — Memory Manager**  
Replace any existing session storage (in-memory dict, Redis, simple Cosmos writes) with `framework/memory/store.py`. Define `MemoryConfig` with the existing doc ID scheme to preserve backward compatibility with existing Cosmos documents.

**Phase 3 — Retriever + LLM Wrapper**  
Replace existing OpenAI/Anthropic calls with `retrieve()` and `astream_llm()`. The streaming interface is a drop-in for any generator-based response path.

**Phase 4 — Prompt Builder**  
Replace existing string concatenation prompt assembly with `build_llm_messages()`. Extract all domain-specific content into `PromptConfig`. This is the highest-risk phase — test prompt output equivalence carefully.

**Phase 5 — Instruction Store**  
Replace hardcoded system prompt strings with `InstructionStore`-backed resolution with file fallback. The existing compiled strings become the fallback; no prompt content changes until first Blob upload.

**Phase 6 — Graph + Registry**  
Wrap existing agent call logic in LangGraph node functions. Register in `WORKSTREAM_GRAPHS` and `_STREAM_REGISTRY`. The `/chat` and `/chat/stream` endpoints can be re-pointed to the LangGraph path while the old path remains active.

**Phase 7 — Skill Selector**  
Extract skill content from system prompts into `.md` files. Define `_SKILL_ROUTING` and `_STEP_SKILL_MAP`. Initially all skills can have wildcard triggers so they always load (reproducing existing behaviour) before narrowing to precise routing.

**Phase 8 — Workflow Pipeline**  
Introduce `PipelineConfig` and the workflow state machine. This adds new capability (pipeline tracking UI) without breaking the existing chat flow.

### 15.4 Backward Compatibility Preservation

- Keep existing `_canonical_phase_agent()` alias map intact during migration so old frontend phase strings continue to route correctly
- Keep existing Cosmos document ID scheme in `MemoryConfig.doc_id_scheme` during migration — do not re-key existing documents
- The `generate_guided()` and `generate_guided_stream()` functions can remain as deprecated fallbacks while the primary path migrates to `_build_llm_messages()` + `astream_llm()`
- Introduce the `_STREAM_REGISTRY` path alongside the existing LangGraph path; switch by feature flag

---

## 16. Best Practices

### 16.1 Architectural Principles

| Principle | Description |
|---|---|
| **Framework owns mechanics, application owns knowledge** | No framework file should contain a domain concept. No system prompt string, step name, or decision key belongs in the framework package. |
| **Registration over modification** | Every new capability is added by registering an entry in a dict or passing a config object. The framework is never edited to add features. |
| **Fail gracefully, not loudly** | Every external call is wrapped in try/except. Missing config produces degraded-but-functional behaviour, not crashes. |
| **Security at the boundary** | Auth, injection detection, and response sanitisation happen at the API layer, before any domain code runs. They are not optional middleware. |
| **State is explicit, not ambient** | All conversation state (decisions, progress, blockers) is passed as an explicit `AgentState` object, never stored in module globals. |
| **Prompts are versioned assets** | System prompts and skill files are treated like code: versioned, reviewed, and deployed via a controlled pipeline. |

### 16.2 Coding Guidelines

- Agent node functions must be **pure with respect to side effects** — all Cosmos writes happen after the node returns, not inside it
- LLM instantiation should always use settings values, never hardcoded strings or env vars accessed directly inside the function
- New prompt sections should use unique, exact-match sentinel headers (`=== SECTION NAME ===`) so behavioural rules can reference them precisely
- `extract_state_updates()` should always be called as a background task — never in the critical path of a streaming response
- History injection must always strip metadata blocks (e.g., `<!--SUMMARY-->`) before sending to the LLM to prevent context pollution
- Never log instruction content, user query content at WARNING/ERROR level, or JWT tokens

### 16.3 Naming Conventions

| Item | Convention | Example |
|---|---|---|
| Agent node functions | `{domain}_{phase}_agent_node` | `m365_strategy_agent_node` |
| Graph builders | `build_{domain}_graph` | `build_m365_graph` |
| Prepare context functions | `prepare_{domain}_{phase}_context` | `prepare_m365_strategy_context` |
| Instruction scopes | `{type}-{domain}-{topic}` | `skill-design-build-identity` |
| Skill files | `Skill_{TopicName}.md` | `Skill_IdentityAuthProvisioning.md` |
| Step keys in stage_progress | `{NN}_{snake_case_description}` | `03_seller_alignment` |
| Cosmos containers | kebab-case nouns | `conversation-sessions`, `workflow-runs` |
| Environment variables | `SCREAMING_SNAKE_CASE` with service prefix | `AZURE_COSMOS_ENDPOINT` |

### 16.4 Prompt Engineering Guidelines

- **Layer prompts from stable to dynamic**: identity → workflow → skills (stable in system message) → state → data → query (dynamic in user turn)
- **Use sentinel headers as conditional triggers**: the LLM can be instructed to apply specific rules "ONLY when section `=== X ===` is present", enabling reliable conditional behaviour without complex branching
- **Progressive disclosure is a framework contract**: every step-completion deliverable should follow the summary-then-offer pattern; this is enforced in `_INTERACTIVE_OUTPUT_PROTOCOL` and must not be overridden by domain skills
- **Keep extraction prompts separate from generation prompts**: the state extraction LLM call uses a different, shorter prompt focused solely on JSON output; never combine generation and extraction in one call
- **Stabilise the system message**: dynamic content (decisions, inventory, chunks) belongs in the user turn, not the system message, to maximise prompt-cache hit rate

### 16.5 Testing Recommendations

| Test Type | Target | Approach |
|---|---|---|
| Unit | `build_llm_messages()` | Assert section ordering, header presence, history filtering |
| Unit | `extract_state_updates()` parsing | Mock LLM response; assert key whitelist validation, status validation, blocker sanitisation |
| Unit | `InstructionStore` cache logic | Mock Blob client; assert TTL expiry and cache hit/miss |
| Integration | `retrieve()` | Use a seeded test index; assert chunks returned match filter |
| Integration | `MemoryStore` | Use Cosmos emulator; assert save/load round-trip |
| Contract | Agent node functions | Assert `AgentState` output contains required keys; mock LLM |
| End-to-end | `/chat/stream` SSE | Assert token stream received; assert background state persisted |
