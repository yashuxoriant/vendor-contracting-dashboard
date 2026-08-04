# App - AI Agents & Domain Logic

Domain-specific AI agents, prompts, and business logic for BOM creation across multiple technology categories.

## 📋 Table of Contents
- [Overview](#overview)
- [Directory Structure](#directory-structure)
- [Components](#components)
- [Agent System](#agent-system)
- [Usage](#usage)

## 🎯 Overview

The `app/` directory contains the **business domain logic** for the IT BOM Creation System, including:

- **AI Agents**: LangGraph-based agents for BOM creation workflow
- **Specialist Skills**: Category-specific domain knowledge (Network, Data Center, etc.)
- **Prompt Configuration**: Dynamic prompt building based on session state
- **BOM Extraction Logic**: Parsing and extracting structured BOM data from LLM responses

This is the "brain" of the system - it knows **what** questions to ask, **how** to interpret answers, and **when** to generate a BOM.

## 📂 Directory Structure

```
app/
├── __init__.py
├── memory_config.py             # Memory configuration (placeholder)
├── settings.py                  # App-level settings
├── agents/                      # AI agent implementations
│   ├── __init__.py
│   ├── bom_creation_agent.py    # LangGraph BOM creation workflow
│   ├── bom_extraction_config.py # BOM extraction rules + schemas
│   └── bom_prompt_config.py     # Dynamic prompt builder
├── instructions/                # Specialist skill files
│   ├── __init__.py
│   ├── Shared.md                # Shared instructions across all categories
│   └── BOM/
│       ├── Skill_Network_Telecom.md  # Network & Telecom specialist
│       └── (other category skills...)
└── routers/                     # API route definitions (minimal)
    └── __init__.py
```

## 🧩 Components

### 1. BOM Creation Agent (`agents/bom_creation_agent.py`)

**Purpose**: LangGraph-based state machine for the full BOM creation workflow.

**Architecture**:
```
START
  ↓
build_context ──→ Gather session state, RAG context, requirements
  ↓
call_llm ──────→ Generate AI response with Anthropic Claude
  ↓
extract_bom ───→ Parse JSON BOM from response (if present)
  ↓
rule_fallback ─→ Fallback if extraction fails
  ↓
compute_progress → Calculate % complete based on collected fields
  ↓
state_extraction → Update agent_state with new info from response
  ↓
END
```

**Key Method**:
```python
async def run(session_doc: dict, message: str) -> tuple:
    """
    Run the BOM creation agent.
    
    Args:
        session_doc: Session document from Cosmos DB
        message: User's message
    
    Returns:
        (response_text, bom_data, progress_pct, complete_flag)
    """
```

**Usage** (from `backend/api/chat.py`):
```python
from app.agents.bom_creation_agent import BOMCreationAgent

agent = BOMCreationAgent()
response, bom, progress, complete = await agent.run(session, message)
```

### 2. BOM Prompt Configuration (`agents/bom_prompt_config.py`)

**Purpose**: Build dynamic prompts based on session state and category.

**Key Functions**:
```python
def make_session_block(agent_state: dict, category: str) -> str:
    """
    Build the "ACTIVE SESSION" block showing collected/missing fields.
    Implements Day-1 pre-population for Network categories.
    """

def make_prompt_config(
    session: dict,
    message: str,
    system_base: str,
    bom_rag: str = "",
) -> PromptConfig:
    """
    Assemble full PromptConfig for LLM call.
    Returns: PromptConfig(system=..., messages=[...])
    """
```

**Day-1 Pre-population Logic**:
For Network categories, if M&A phase is not set, automatically assume "Day-1 Readiness":

```python
_DAY1_ASSUMED_CATEGORIES = {
    "Network & Telecom", "Network Equipment", "SD-WAN",
    "Access Points", "WAN/SD-WAN", "LAN", "Wireless/WLAN",
    "Firewall", "Voice/UCaaS",
}

if category in _DAY1_ASSUMED_CATEGORIES and not agent_state.get("ma_phase"):
    agent_state["ma_phase"] = "Day-1 Readiness"
```

### 3. BOM Extraction Configuration (`agents/bom_extraction_config.py`)

**Purpose**: Define BOM extraction rules and schemas.

**Key Components**:
- **Field Mapping**: Map LLM output keys to canonical BOM schema
- **Validation Rules**: Ensure required fields are present
- **Extraction Patterns**: Regex patterns for extracting BOM JSON from markdown

**Example**:
```python
BOM_SCHEMA = {
    "name": str,
    "project": str,
    "category": str,
    "line_items": list,  # Each item has: description, sku, qty, unit_price, vendor
    "totals": dict,      # hardware, software, services, total_otc
    "warnings": list,
}
```

### 4. Specialist Skills (`instructions/BOM/`)

**Purpose**: Category-specific domain knowledge files in Markdown format.

**Example**: `Skill_Network_Telecom.md`

```markdown
# Network & Telecom BOM Specialist Skill

## Domain Rules
- Assume Day-1 Readiness. Do not ask about M&A phase.
- Always include HA pairs for firewalls and WAN routers.
- PoE budget: 7.5W per phone, 15.4W per AP, 30W per WAP.

## Qualification Sequence
### Stage 1: Site Subcategory
Ask: Office/Branch/Manufacturing Site | Colo/DC Network Hub | Cloud Network Hub

### Stage 2: Sizing Inputs
Ask: Site count, users per site, Day-1 date, vendor standard

### Stage 3: HA Requirements
If critical site → HA mandatory on all layers

## Bundle Expansion Rules
Router → 8 lines (chassis, IOS, DNA sub, SmartNet, NIM, SFP, cables, rack)
Firewall → 10 lines (appliance, IPS, URL, SSL, AMP, support, SFPs, PS, rack)
Switch → 5 lines (chassis, license, stacking, SmartNet, uplink SFPs)
AP → 4 lines (unit, PoE injector, cloud license, mounting)

## BOM Generation Trigger
Generate BOM when ALL of Stage 1 + Stage 2 are complete.
```

**How Skills Are Loaded**:
Skills are loaded by `backend/ai/prompts/system_base.py`:

```python
def _load_skill(category: str) -> str:
    """Load skill file for this category from app/instructions/BOM/"""
    fname = _SKILL_MAP.get(category, "")
    if not fname:
        return ""
    path = _SKILLS_DIR / fname
    return path.read_text(encoding="utf-8")
```

## 🤖 Agent System

### How Agents Work

1. **User sends message** → `POST /api/chat/message`
2. **Backend loads session** from Cosmos DB
3. **Backend calls agent** → `BOMCreationAgent().run(session, message)`
4. **Agent builds context**:
   - Session state (project, category, agent_state)
   - RAG context (similar BOMs from Azure AI Search)
   - Specialist skill (if category matches)
5. **Agent calls LLM** (Anthropic Claude via Azure AI Foundry)
6. **Agent extracts BOM** (if JSON present in response)
7. **Agent computes progress** (% of required fields collected)
8. **Agent returns** → `(response_text, bom_data, progress, complete)`
9. **Backend saves** session + BOM to Cosmos DB
10. **Frontend displays** response + BOM preview

### State Machine (7 Phases)

The `BOMOrchestrator` (in `backend/ai/agents/orchestrator.py`) uses a 7-phase state machine:

| Phase | Purpose | Exit Criteria |
|-------|---------|---------------|
| **INTAKE** | Gather M&A phase, category, project name | All 3 fields present |
| **QUALIFY** | Conveyance/shared/dedicated decision | Conveyance status known |
| **SCOPE** | Site count, users, Day-1 date, vendor | Site count + date present |
| **SIZING** | Compute quantities, multipliers | Quantities calculated |
| **GENERATE** | Build full BOM with SKU bundles | BOM JSON generated |
| **VALIDATE** | EOL checks, PoE budget, lead-time warnings | Validation complete |
| **COMPLETE** | BOM finalized, ready for export | All validations passed |

**Phase Progression**:
```python
_PHASE_ORDER = [
    BOMPhase.INTAKE,
    BOMPhase.QUALIFY,
    BOMPhase.SCOPE,
    BOMPhase.SIZING,
    BOMPhase.GENERATE,
    BOMPhase.VALIDATE,
    BOMPhase.COMPLETE,
]
```

## 🛠️ Usage

### Creating a New Specialist Skill

1. **Create skill file** in `app/instructions/BOM/`:
   ```bash
   touch app/instructions/BOM/Skill_Cybersecurity.md
   ```

2. **Write the skill** (see `Skill_Network_Telecom.md` as template):
   ```markdown
   # Cybersecurity BOM Specialist Skill
   
   ## Domain Rules
   - Prioritize compliance requirements (SOC2, ISO, HIPAA, PCI)
   - Always include: SIEM, EDR, PAM, email security
   
   ## Qualification Sequence
   ### Stage 1: Compliance Requirements
   Ask: Which compliance standards? (SOC2, ISO 27001, HIPAA, PCI-DSS)
   
   ## Bundle Expansion Rules
   EDR → 3 lines (per-endpoint license, management console, support)
   SIEM → 5 lines (log ingestion, UEBA, threat intel, support, storage)
   ```

3. **Register in skill map** (`backend/ai/prompts/system_base.py`):
   ```python
   _SKILL_MAP = {
       "Cybersecurity": "Skill_Cybersecurity.md",
       # ... other mappings
   }
   ```

4. **Test**:
   ```bash
   curl -X POST http://localhost:8000/api/chat/start \
     -d '{"category": "Cybersecurity", "project": "Test"}'
   ```

### Adding New Agent State Fields

1. **Define field** in `agents/bom_prompt_config.py`:
   ```python
   _INTAKE_FIELDS = [
       "ma_phase",
       "workstream_category",
       "project_name",
       "new_field_here",  # Add your field
   ]
   ```

2. **Add extraction logic** in `backend/ai/agents/orchestrator.py`:
   ```python
   def _extract_fields_from_message(message: str, agent_state: Dict) -> Dict:
       # ... existing logic ...
       
       # Add your extraction pattern
       if not agent_state.get("new_field"):
           match = re.search(r"pattern-for-new-field", message.lower())
           if match:
               agent_state["new_field"] = match.group(1)
       
       return agent_state
   ```

3. **Use in prompts** (`agents/bom_prompt_config.py`):
   ```python
   def make_session_block(agent_state: dict, category: str) -> str:
       block += f"\nNew Field: {agent_state.get('new_field', 'NOT SET')}"
       return block
   ```

## 📚 Additional Resources

- [Backend README](../backend/README.md) - API integration
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [ROADMAP.md](../ROADMAP.md) - Development roadmap

## 📄 License

See [LICENSE](../LICENSE) for details.
