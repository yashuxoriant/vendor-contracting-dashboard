"""
Chat and BOM creation API endpoints
Sprint 1: Azure OpenAI wired in with full 10-phase BOM methodology system prompt.
Fallback to Anthropic Claude, then rule-based when no credentials available.
"""
from fastapi import APIRouter, HTTPException, status, BackgroundTasks, File, Form, UploadFile
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import uuid
import json
import re
import asyncio
import hashlib

logger = logging.getLogger(__name__)

from db import get_cosmos_client, get_adls_client, ChatSession, ChatMessage, SessionContext
from config import get_settings

router = APIRouter(prefix="/api/bom", tags=["chat"])
settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
# Per-session asyncio locks — prevent concurrent writes to the same session.
# Key: session_id → asyncio.Lock
# Without this: two concurrent requests load the same session state and the
# second write silently overwrites the first (last-writer-wins race condition).
# ─────────────────────────────────────────────────────────────────────────────
_SESSION_LOCKS: Dict[str, asyncio.Lock] = {}

def _get_session_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _SESSION_LOCKS:
        _SESSION_LOCKS[session_id] = asyncio.Lock()
    return _SESSION_LOCKS[session_id]


def _msg_fingerprint(role: str, content: str) -> str:
    """SHA-256 fingerprint of (role, first 200 chars) for deduplication."""
    key = f"{role}:{content[:200]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _dedup_conversation(conversation: List[ChatMessage]) -> List[ChatMessage]:
    """Remove back-to-back duplicate messages (same role + same content prefix)."""
    seen = set()
    result = []
    for msg in conversation:
        fp = _msg_fingerprint(msg.role, msg.content)
        if fp not in seen:
            seen.add(fp)
            result.append(msg)
    return result


def _append_user_message_if_new(
    conversation: List[ChatMessage],
    content: str,
) -> bool:
    """
    Append a user message ONLY if it is not a duplicate of the last user message.
    Returns True if the message was appended, False if skipped (duplicate).

    Real-world scenario: streaming client disconnects mid-stream; on retry the
    same user message would be appended again, creating a duplicate.
    """
    fp = _msg_fingerprint("user", content)
    # Check last few messages for duplicates (not just the very last)
    for msg in reversed(conversation[-4:]):
        if msg.role == "user" and _msg_fingerprint("user", msg.content) == fp:
            logger.debug("Skipped duplicate user message (fingerprint=%s)", fp)
            return False
    conversation.append(ChatMessage(role="user", content=content))
    return True

# ─────────────────────────────────────────────────────────────────────────────
# 10-PHASE BOM SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────
BOM_SYSTEM_PROMPT = """You are an expert IT procurement BOM Specialist embedded in PwC's M&A Contracting Tool.
Your mission: guide users through creating accurate, fully-sized Bills of Materials that compress the typical
2–3 week procurement cycle by surfacing every cost, lead-time risk, and approval requirement upfront.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUSINESS CONTEXT — READ FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This tool is used in M&A ("Day 1") scenarios where IT infrastructure must be operational on a hard cutover
date. Delays in BOM approval directly delay the acquisition close. The full approval lifecycle is:

  CREATION (Phases 1–10) → REVIEW CYCLE (Phase 11) → VENDOR SUBMISSION

APPROVAL LIFECYCLE (Phase 11 — Sequential, With Reset):
  Step 1 → BOM sent to BUYER IT for review
           Reviews: Compute sizing, Storage sizing, Network sizing, Power & Physical sizing
           ✓ Approved → advance to Step 2
           ✗ Changes Requested → BOM MUST BE REBUILT → restart from Step 1
  
  Step 2 → BOM sent to SELLER IT for review
           Reviews: Same four sizing areas + vendor/pricing validation
           ✓ Approved → advance to Step 3
           ✗ Changes Requested → BOM MUST BE REBUILT → restart from Step 1 (not Step 2)
  
  Step 3 → BOM sent to SI / JBR for review
           Reviews: Technical feasibility, installation sequence, spares adequacy
           ✓ Approved → BOM FINALISED → vendor submission
           ✗ Changes Requested → BOM MUST BE REBUILT → restart from Step 1

CRITICAL RULE: ANY changes requested by ANY approver resets the ENTIRE approval cycle back to Step 1.
This is why the process typically takes 2–3 weeks (often 3–5 rebuild cycles).

APPROVAL PHASES (what each approver checks):
  • SIZE THE COMPUTE REQUIREMENTS — server specs, vCPU/RAM, consolidation ratios, HA nodes
  • SIZE THE STORAGE REQUIREMENTS — tiers, IOPS, RAID, backup, SAN/NAS/HCI
  • SIZE THE NETWORK REQUIREMENTS — switching, routing, uplinks, firewall, load balancers
  • SIZE POWER AND PHYSICAL INFRASTRUCTURE — racks, PDUs, UPS, cooling, cabling

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CATEGORIES YOU HANDLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Data Center / COLO | SD-WAN | Cybersecurity | Network Equipment |
M365 & Power Platform | Cloud Infrastructure | EOL Replacement | Laptops

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
11-PHASE BOM METHODOLOGY (Data Center / COLO — full detail)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PHASE 1 — SCOPE & CONSTRAINTS
  • Which workloads land in the DC? What stays cloud/SaaS/co-lo?
  • Specialised hardware: AS400, GPU clusters, bare-metal requirements?
  • Physical site type (new build, existing DC, co-lo cage)?
  • Power/cooling constraints and available capacity?
  • HARD Day 1 cutover date (drives all lead-time calculations)
  • Compliance/regulatory constraints (PCI, HIPAA, SOC 2, GDPR)?

PHASE 2 — SELLER INVENTORY ASSESSMENT
  • App-to-server mapping: which apps run where today?
  • Conveyed vs. non-conveyed assets (what transfers in the deal)?
  • Age, spec, warranty status of existing hardware
  • EOL/EOS hardware → flag immediately for replacement sizing
  • Current rack count, peak power draw (kW), cooling load
  • Existing network topology and uplink capacities

PHASE 3 — COMPUTE SIZING (Approval Phase A)
  • Per-application vCPU, RAM, IOPS, bandwidth, HA requirements
  • Virtualisation consolidation ratio: 8:1–15:1 (VMware/Hyper-V)
  • Minimum 3 nodes for HA (N+1); recommend 4+ for live migration headroom
  • Headroom: +20–30% for growth; +15% for backup workloads
  • GPU compute: separate sizing for AI/ML workloads
  • Output: server count, model, specs, vendor, unit price, extended price

PHASE 4 — STORAGE SIZING (Approval Phase B)
  • Tier 1 (NVMe/SSD): databases, ERP, latency-sensitive apps — target <1ms
  • Tier 2 (SAS/SATA): file shares, archive, VMs — target <5ms
  • RAID overhead: +20–25% raw vs. usable; mirror vs. parity trade-offs
  • Backup sizing: 2–3× primary usable + dedup/compression ratio (2:1–5:1)
  • Architecture choice: SAN, NAS, HCI (Nutanix/vSAN), DAS — document rationale
  • Output: storage array model, raw/usable capacity, IOPS spec, vendor, price

PHASE 5 — NETWORK SIZING (Approval Phase C)
  • Layer 2/3 architecture: core, distribution, access tiers
  • Top-of-Rack (ToR) switches: 1 per rack minimum; uplinks 10G/25G/100G
  • North–south traffic: WAN/DC uplink sizing (MPLS, dark fibre, internet)
  • East–west traffic: inter-rack bandwidth for VM live-migration and storage
  • Out-of-band (OOB) management network: dedicated or VRF-based
  • Firewall: throughput Gbps, CPS, concurrent sessions, VPN tunnels
  • Load balancers: VIPs, SSL offload, throughput
  • Output: switch models, firewall model, qty, rack placement, price

PHASE 6 — POWER & PHYSICAL INFRASTRUCTURE (Approval Phase D)
  • Total IT load calculation: sum all device TDPs + 20% contingency
  • PUE target: 1.4–1.6 (factor into cooling capacity)
  • UPS: N+1 configuration; match kVA to IT load × 1.25
  • PDUs: redundant A+B feeds per rack; horizontal vs. vertical
  • Rack count: 2U servers → 40 per 42U rack; allow 30% space for cables/patch
  • Raised floor vs. overhead cable management
  • CRAC/CRAH cooling: match to heat load; in-row vs. perimeter
  • Generator: size to full DC load + 10% headroom
  • Output: rack units, PDU model/qty, UPS model/qty, cooling unit model/qty

PHASE 7 — BUILD THE BOM (compile all phases)
  Categories in order:
  1. Physical/Racks (order_sequence=1): racks, PDUs, cables
  2. Networking (order_sequence=2): switches, firewalls, load balancers
  3. Compute/Storage (order_sequence=3): servers, storage arrays
  4. Cabling (order_sequence=4): fibre, copper, patch panels
  5. Software Licenses (order_sequence=5): hypervisor, monitoring, backup SW
  + Maintenance Contracts (3–5yr on EVERY hardware line — mandatory)
  + Spares Kit: 10% of drives, NICs, PSUs (critical failure parts only)

PHASE 8 — EOL & RISK VALIDATION
  • Flag any SKU with EOS date < Day 1 + 3 years as WARNING
  • Flag any SKU with EOS already past as CRITICAL — must replace
  • Dual-quote requirement: any line item > $50K needs two vendor quotes
  • Lead times: networking 8–14 weeks, compute 10–18 weeks, storage 12–20 weeks
  • Warn if (Day 1 date) minus (longest lead time) < today + 2 weeks buffer

PHASE 9 — PRICING & VENDOR STRATEGY
  • Preferred vendors hierarchy: CDW → PC Connection → SHI → Dell Direct → Cisco Direct
  • Bundled discounts: note when pricing assumes volume/deal-reg discount
  • List vs. net pricing: always use net/street pricing; never list price
  • PO entity: which legal entity in the deal structure issues the PO?
  • MSA/NDA status: flag if vendor agreements not yet in place

PHASE 10 — ORDER SEQUENCING & APPROVAL READINESS
  • Verify order_sequence 1–5 assigned to every line item
  • Confirm 3-party approval sign-off list: Buyer IT, Seller IT, SI / JBR
  • Identify long-lead items that need PO issued before final approval (de-risk)
  • Legal review flag: software licenses > $100K need legal review
  • Budget confirmation: total vs. approved capex envelope

PHASE 11 — APPROVAL WORKFLOW (3-PARTY SEQUENTIAL WITH RESET)
  BUYER IT → SELLER IT → SI / JBR
  
  Each party reviews the four sizing sections:
    A. Compute Requirements sizing
    B. Storage Requirements sizing
    C. Network Requirements sizing
    D. Power & Physical Infrastructure sizing
  
  If ANY approver requests changes at ANY step:
    → BOM is marked REVISION REQUIRED
    → Revision counter increments (Rev 1 → Rev 2 → Rev 3...)
    → Approval cycle counter increments
    → ALL three parties must re-approve from the beginning
    → Typical timeline: 3–5 rebuild cycles = 2–3 weeks total
  
  BOM is FINAL only when all three parties approve with no changes.
  Final BOM → status = "approved" → vendor submission.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
5-QUESTION FLOW (for non-DC categories)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SD-WAN:          site count, bandwidth/redundancy per site, HA config, existing carrier contracts, preferred vendor
Cybersecurity:   endpoint count, compliance requirements (PCI/HIPAA/SOC2), SIEM log volume, current tools, cloud vs. on-prem
Network Equip:   total port count, PoE requirements, rack space available, uplink speeds, support tier (NBD/4hr)
M365:            user count, E3 vs E5, Power BI Premium, migration scope (Exchange/Teams/SPO), go-live date
Cloud Infra:     Azure regions needed, workload types (IaaS/PaaS/SaaS), ExpressRoute vs VPN, compliance, monthly budget target
EOL Replacement: current hardware model/age, EOS/EOL date, urgency driver, budget envelope, vendor preference
Laptops:         user count, role profiles (exec/dev/standard), OS (Windows/Mac), MDM platform, procurement timeline

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY BUSINESS RULES (enforce every time)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. EOL/EOS hardware → always flag with WARNING + recommend replacement SKU
2. Maintenance contract line for EVERY hardware item (3–5yr minimum)
3. Spares Kit line: 10% of drives, NICs, PSUs
4. Lead-time warning if Day 1 minus longest lead time < today + 2 weeks
5. Dual-quote flag for any single line item > $50K
6. 3-party sequential approval (Buyer IT → Seller IT → SI) is non-negotiable
7. Any change request restarts the entire approval cycle from Buyer IT
8. Never use list price — always net/street pricing
9. Always include order_sequence 1–5 on every line item
10. Minimum 3 compute nodes for HA; document consolidation ratio used

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXT-AWARE RESPONSE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- If asked about an existing BOM's status, explain which approval step it is on and what is needed next.
- If a BOM is in "revision_required" status, explain that it must be rebuilt before re-submission and list the changes requested.
- If asked "why is this taking so long?" explain the sequential approval with reset mechanism.
- If a BOM is on Revision 3+, proactively suggest scheduling a joint review call to align all three parties before rebuilding.
- If asked about approval phases, map them to the four sizing sections: Compute, Storage, Network, Power/Physical.
- Never fabricate SKU numbers, prices, or lead times — say "verify with vendor" if uncertain.
- Always tie recommendations back to the Day 1 cutover date.
- When referencing approval history, cite the revision number and approval cycle.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOM JSON OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When ready to output, emit valid JSON inside ```json...``` fences:
{
  "name": "ProjectName - Category BOM Rev 1",
  "project": "string",
  "category": "string",
  "revision": 1,
  "line_items": [
    {
      "line_number": 1,
      "category": "Compute",
      "description": "Dell PowerEdge R750 2x Xeon Gold 6330 512GB RAM",
      "sku": "DELL-PE-R750",
      "qty": 3,
      "unit": "/unit",
      "unit_price": 28500,
      "extended_price": 85500,
      "vendor": "Dell/CDW",
      "term": "one-time",
      "eol_flag": false,
      "order_sequence": 3,
      "notes": "HA compute cluster — 3-node N+1"
    }
  ],
  "totals": {"hardware": 0, "software": 0, "services": 0, "total_otc": 0, "tco_3year": 0},
  "warnings": ["List any EOL, dual-quote, or lead-time warnings here"],
  "approval_phases": {
    "compute_sizing": "summary of compute decisions",
    "storage_sizing": "summary of storage decisions",
    "network_sizing": "summary of network decisions",
    "power_physical": "summary of power/physical decisions"
  },
  "approvals_required": ["Buyer IT", "Seller IT", "SI Technical Team"],
  "approval_sequence": "Buyer IT → Seller IT → SI (sequential; any change request restarts from Buyer IT)"
}
After the JSON block, write a 4–6 sentence plain-English summary covering:
1. What was sized and why
2. Key risks or warnings
3. Next approval step
4. What would trigger a cycle restart
"""

# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    category: str
    project: Optional[str] = "New Project"
    user_id: Optional[str] = "demo_user"
    bom_id: Optional[str] = None  # Optional: scope chat to a specific indexed BOM

class StartSessionResponse(BaseModel):
    session_id: str
    category: str
    message: str

class ChatMessageRequest(BaseModel):
    session_id: str
    message: str
    user_id: Optional[str] = "demo_user"

class ChatMessageResponse(BaseModel):
    session_id: str
    response: str
    partial_bom: Optional[Dict[str, Any]] = None
    progress: int
    complete: bool
    suggestions: List[str] = []          # 3 contextual follow-up questions
    session_title: Optional[str] = None  # Auto-generated title from first exchange

class SessionStatusResponse(BaseModel):
    session_id: str
    category: str
    status: str
    progress: int
    message_count: int

# ─────────────────────────────────────────────────────────────────────────────
# AI Client Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_azure_openai_client():
    if settings.azure_openai_endpoint == "https://dummy.openai.azure.com/":
        return None
    try:
        from openai import AzureOpenAI
        return AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
    except Exception:
        return None

def _get_azure_foundry_anthropic_client():
    """Create Anthropic client pointing at Azure AI Foundry Anthropic proxy endpoint.
    Endpoint format: https://<resource>.services.ai.azure.com/anthropic
    Authentication: Azure API key passed as both api_key and x-ms-useragent header.
    """
    endpoint = settings.azure_openai_chat_endpoint
    api_key = settings.azure_openai_api_key
    if not endpoint or "dummy" in endpoint or "services.ai.azure.com" not in endpoint:
        return None
    if not api_key or "dummy" in api_key:
        return None
    try:
        import anthropic
        # Azure AI Foundry Anthropic proxy accepts Anthropic SDK requests;
        # base_url must end without trailing slash so the SDK appends /v1/messages correctly.
        client = anthropic.Anthropic(
            base_url=endpoint.rstrip("/"),
            api_key=api_key,
            default_headers={"x-ms-useragent": "anthropic-azure/1.0"},
        )
        return client
    except Exception:
        return None

def _get_anthropic_client():
    if settings.anthropic_api_key == "dummy-api-key":
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=settings.anthropic_api_key)
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/start", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest):
    """Start a new BOM creation session."""
    cosmos_client = get_cosmos_client()
    session_id = f"session_{uuid.uuid4().hex[:12]}"
    context = SessionContext(
        category=request.category,
        requirements={"project": request.project},
        progress_percentage=0.0,
        bom_id=request.bom_id,  # scope vector search to this BOM (if provided)
    )
    welcome_content = (
        f"Hello! I am your AI BOM specialist. Let us build a **{request.category}** BOM "
        f"for **{request.project}**.\n\n"
        f"I will guide you step by step and generate a complete, vendor-ready Bill of Materials.\n\n"
        f"To start: {_opening_question(request.category)}"
    )
    welcome = ChatMessage(role="assistant", content=welcome_content)
    session = ChatSession(
        session_id=session_id,
        user_id=request.user_id,
        conversation=[welcome],
        context=context,
    )
    session_dict = session.model_dump(mode="json")
    session_dict["_id"] = session_id  # ensure mock stores under the correct key
    session_dict["id"] = session_id
    cosmos_client.create_session(session_dict)
    # Seed ADLS archive with initial session (welcome message)
    _archive_session_to_adls(session, request.user_id or "demo_user")
    return StartSessionResponse(session_id=session_id, category=request.category, message=welcome_content)


@router.post("/chat", response_model=ChatMessageResponse)
async def send_message(request: ChatMessageRequest, background_tasks: BackgroundTasks):
    """Send a message in an active BOM creation session."""
    cosmos_client = get_cosmos_client()

    async with _get_session_lock(request.session_id):
        session_data = cosmos_client.get_session(request.session_id)
        if not session_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        try:
            session = ChatSession.model_validate(session_data)
        except Exception as exc:
            logger.error("Session hydration failed: %s", exc)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Session data corrupt")

        appended = _append_user_message_if_new(session.conversation, request.message)
        if not appended:
            logger.info("Duplicate user message detected for session %s — skipped", request.session_id)

        response_text, partial_bom, progress, complete = await _process_message(session, request.message)

        session.conversation.append(ChatMessage(role="assistant", content=response_text))
        session.conversation = _dedup_conversation(session.conversation)
        session.context.progress_percentage = float(progress)
        session.updated_at = datetime.utcnow()
        if complete:
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            if partial_bom:
                _save_bom_to_cosmos(cosmos_client, partial_bom, session, request.user_id or "demo_user")

        cosmos_client.update_session(request.session_id, session.model_dump(mode="json"))

    # Archive to ADLS outside the lock (non-blocking)
    background_tasks.add_task(_archive_session_to_adls, session, request.user_id or "demo_user")

    _emit_audit_event(
        user_id=request.user_id or "demo_user",
        action="chat_message",
        session_id=request.session_id,
        details={"progress": progress, "complete": complete, "has_bom": partial_bom is not None},
    )

    suggestions = _generate_suggestions(
        response_text, session.context.category, partial_bom, complete
    )
    session_title = _session_title(session)

    return ChatMessageResponse(
        session_id=request.session_id,
        response=response_text,
        partial_bom=partial_bom,
        progress=progress,
        complete=complete,
        suggestions=suggestions,
        session_title=session_title,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Chat with Attachment
# ─────────────────────────────────────────────────────────────────────────────

_ATTACH_ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/csv",
    "text/plain",
    "application/octet-stream",
}
_ATTACH_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


# ─────────────────────────────────────────────────────────────────────────────
# SSE Streaming Chat  POST /api/bom/stream
# ─────────────────────────────────────────────────────────────────────────────

import re as _r
from fastapi.responses import StreamingResponse


@router.post("/stream")
async def stream_message(request: ChatMessageRequest, background_tasks: BackgroundTasks):
    """
    Server-Sent Events streaming chat endpoint.

    Fix history:
    - Session lock prevents concurrent writes (race condition fix)
    - User message written to Cosmos ATOMICALLY before streaming begins
      → on client disconnect, session is still consistent
    - Deduplication prevents duplicate user messages on retry
    - Fallback to rule-based uses the new orchestrator state machine

    SSE frame format:
        data: {"token": "<text>", "done": false}   (per chunk)
        data: {"token": "", "done": true, "complete": bool, "progress": int, "bom": <obj|null>}
    """
    cosmos_client = get_cosmos_client()

    # ── PHASE 1: Atomic user-message write (inside lock) ──────────────────
    # This runs BEFORE the stream generator starts. If the client disconnects
    # mid-stream, the user message is already persisted correctly.
    session: ChatSession
    session_dict_for_ai: dict
    messages_for_ai: list
    system_prompt: str

    lock = _get_session_lock(request.session_id)
    async with lock:
        session_data = cosmos_client.get_session(request.session_id)
        if not session_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        try:
            session = ChatSession.model_validate(session_data)
        except Exception as exc:
            logger.error("Session hydration failed in stream: %s", exc)
            raise HTTPException(status_code=500, detail="Session data corrupt")

        # Dedup: skip if this exact user message was already appended (retry case)
        appended = _append_user_message_if_new(session.conversation, request.message)
        if appended:
            # Save user message immediately — consistent even if stream is interrupted
            session.updated_at = datetime.utcnow()
            cosmos_client.update_session(request.session_id, session.model_dump(mode="json"))
            logger.debug("User message committed to Cosmos before stream (session=%s)", request.session_id)

    # ── PHASE 2: Build AI context (outside lock — read-only) ──────────────
    from ai.agents.orchestrator import BOMOrchestrator, _retrieve_bom_context, _phase_addendum, BOMPhase, _PHASE_ORDER, _PHASE_PROGRESS, _extract_fields_from_message, _detect_phase_transition
    from ai.prompts.system_base import get_system_prompt

    orch = BOMOrchestrator()
    session_dict_for_ai = session.model_dump(mode="json")
    context = session_dict_for_ai.get("context", {})
    category = context.get("category") or "Data Center / COLO"
    agent_state = context.get("agent_state", {})
    phase_str = context.get("current_phase_name", BOMPhase.INTAKE.value)
    try:
        current_phase = BOMPhase(phase_str)
    except ValueError:
        current_phase = BOMPhase.INTAKE

    requirements = context.get("requirements", {})
    project = requirements.get("project", "New Project")

    # Extract fields deterministically from user message
    agent_state = _extract_fields_from_message(request.message, agent_state)
    if category and not agent_state.get("workstream_category"):
        agent_state["workstream_category"] = category

    base_prompt = get_system_prompt(category)
    bom_id = context.get("bom_id")
    bom_rag = _retrieve_bom_context(request.message, bom_id=bom_id)

    system_prompt = (
        base_prompt
        + "\n\n" + "=" * 60 + "\nACTIVE SESSION\n" + "=" * 60
        + f"\nProject: {project}"
        + f"\nCategory: {category}"
        + f"\nPhase: {current_phase.value.upper()}"
        + f"\nAgent State: {json.dumps(agent_state, default=str)}"
        + _phase_addendum(current_phase, agent_state)
        + bom_rag
    )

    # Build conversation history — strict user/assistant alternation, deduped
    raw_conv = session.conversation[-16:]
    messages_for_ai = []
    for m in raw_conv:
        role = m.role if m.role not in ("ai", "AI") else "assistant"
        if role not in ("user", "assistant"):
            continue
        content = (m.content or "").strip()
        if not content:
            continue
        if messages_for_ai and messages_for_ai[-1]["role"] == role:
            if role == "assistant":
                messages_for_ai[-1]["content"] += "\n" + content
            continue  # skip duplicate user messages
        messages_for_ai.append({"role": role, "content": content})
    while messages_for_ai and messages_for_ai[0]["role"] == "assistant":
        messages_for_ai.pop(0)

    # ── PHASE 3: Stream generator (stateless from here) ───────────────────
    async def event_stream():
        from ai.client import stream_ai, call_ai
        import asyncio
        full_text = ""
        had_content = False
        gen = stream_ai(messages_for_ai, system_prompt)

        if gen is not None:
            # Run synchronous Anthropic streaming in a thread pool so the
            # asyncio event loop is not blocked between chunks.
            loop = asyncio.get_event_loop()
            sentinel = object()
            while True:
                try:
                    chunk = await loop.run_in_executor(None, next, gen, sentinel)
                except StopIteration:
                    break
                if chunk is sentinel:
                    break
                if chunk == "__STREAM_ERROR__":
                    logger.warning("Stream error signal for session %s", request.session_id)
                    break
                had_content = True
                full_text += chunk
                yield "data: " + json.dumps({"token": chunk, "done": False}) + "\n\n"

        # Fallback: non-streaming call
        if not had_content:
            result = call_ai(messages_for_ai, system_prompt)
            if result:
                full_text = result
                had_content = True
                yield "data: " + json.dumps({"token": result, "done": False}) + "\n\n"

        # Rule-based fallback
        if not had_content:
            user_turns = sum(1 for m in session.conversation if m.role == "user")
            full_text = orch._rule_based(category, current_phase, request.message, agent_state, user_turns)
            yield "data: " + json.dumps({"token": full_text, "done": False}) + "\n\n"

        # ── Post-stream: extract BOM, advance phase ────────────────────────
        bom_data, bom_found = orch._extract_bom(full_text)

        display_text = full_text
        if bom_data:
            display_text = _r.sub(r"```json[\s\S]*?```", "", full_text).strip()
            if not display_text:
                n = len(bom_data.get("line_items", []))
                display_text = f"BOM generated: **{n} line items** — see the panel on the right."

        # Phase transition
        new_phase = _detect_phase_transition(full_text, current_phase, agent_state, bom_found)
        new_phase_num = _PHASE_ORDER.index(new_phase) + 1
        progress = _PHASE_PROGRESS.get(new_phase, 10)
        complete = bom_found and new_phase.value in ("validate", "complete")

        suggestions = _generate_suggestions(display_text, category, bom_data, complete)
        session_title = _session_title(session)

        yield "data: " + json.dumps({
            "token": "", "done": True,
            "complete": complete,
            "progress": progress,
            "bom": bom_data,
            "suggestions": suggestions,
            "session_title": session_title,
        }) + "\n\n"

        # ── PHASE 4: Persist assistant message + state (inside lock) ──────
        async with _get_session_lock(request.session_id):
            # Re-load to get latest state (user message was already persisted in Phase 1)
            latest_data = cosmos_client.get_session(request.session_id)
            if latest_data:
                try:
                    latest_session = ChatSession.model_validate(latest_data)
                except Exception:
                    latest_session = session
            else:
                latest_session = session

            latest_session.conversation.append(ChatMessage(role="assistant", content=display_text))
            latest_session.conversation = _dedup_conversation(latest_session.conversation)
            latest_session.context.progress_percentage = float(progress)
            latest_session.context.current_phase = new_phase_num
            latest_session.context.current_phase_name = new_phase.value  # type: ignore[attr-defined]
            latest_session.context.agent_state = agent_state  # type: ignore[attr-defined]
            latest_session.updated_at = datetime.utcnow()

            if complete:
                latest_session.status = "completed"
                latest_session.completed_at = datetime.utcnow()
                if bom_data:
                    _save_bom_to_cosmos(cosmos_client, bom_data, latest_session, request.user_id or "demo_user")

            cosmos_client.update_session(request.session_id, latest_session.model_dump(mode="json"))

        background_tasks.add_task(_archive_session_to_adls, latest_session, request.user_id or "demo_user")
        _emit_audit_event(
            user_id=request.user_id or "demo_user",
            action="stream_message",
            session_id=request.session_id,
            details={"phase": new_phase.value, "progress": progress, "complete": complete, "bom_items": len(bom_data.get("line_items", []) if bom_data else [])},
        )
        logger.info("Stream complete: session=%s phase=%s progress=%d complete=%s", request.session_id, new_phase.value, progress, complete)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat-with-attachment", response_model=ChatMessageResponse)
async def send_message_with_attachment(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    message: str = Form(default=""),
    user_id: str = Form(default="demo_user"),
    category: str = Form(default="BOMs"),
    file: UploadFile = File(default=None),
):
    """
    Send a chat message optionally with a file attachment.

    The file (if present) is:
      1. Uploaded to SharePoint under  <category>/<filename>
      2. Run through the BOM embedding pipeline (background)
      3. Its extracted text is injected into the AI context for this turn

    Returns the normal ChatMessageResponse plus an `attachment` field.
    """
    attachment_info: dict = {}

    if file and file.filename:
        ct = file.content_type or "application/octet-stream"
        if ct not in _ATTACH_ALLOWED_TYPES:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"File type '{ct}' not supported. Use PDF, Excel, Word, CSV or TXT.",
            )

        content = await file.read()
        if len(content) > _ATTACH_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds 20 MB limit.",
            )

        import uuid as _uuid
        bom_id = str(_uuid.uuid4())
        filename = file.filename or "attachment"

        # ── 1. Upload to SharePoint (category as folder name) ──────────────
        try:
            from db.sharepoint_client import get_sharepoint_client
            sp = get_sharepoint_client()
            folder_path = category.strip() or "BOMs"
            if sp is not None:
                sp_result = sp.upload_file(content, filename, folder_path=folder_path)
                attachment_info["web_url"] = sp_result.get("web_url", "")
                attachment_info["sharepoint_folder"] = folder_path
                logger.info("Chat attachment uploaded to SharePoint folder='%s' file='%s'", folder_path, filename)
            else:
                logger.info("SharePoint mock — attachment '%s' not actually uploaded", filename)
                attachment_info["web_url"] = ""
                attachment_info["sharepoint_folder"] = folder_path
        except Exception as exc:
            logger.warning("SharePoint upload for chat attachment failed (non-fatal): %s", exc)
            attachment_info["web_url"] = ""
            attachment_info["sharepoint_folder"] = category

        attachment_info.update({
            "bom_id": bom_id,
            "filename": filename,
            "size_bytes": len(content),
            "ingest_status_url": f"/api/ingest/status/{bom_id}",
        })

        # ── 2. BOM embedding pipeline (background) ─────────────────────────
        try:
            from services.bom_ingest import ingest_bom_background
            background_tasks.add_task(
                ingest_bom_background,
                bom_id=bom_id,
                filename=filename,
                data=content,
                vendor="",
                category=category,
                metadata={"source": "chat_attachment", "session_id": session_id},
            )
        except Exception as exc:
            logger.warning("Could not queue ingest for chat attachment: %s", exc)

        # ── 3. Extract text snippet for immediate AI context ───────────────
        file_context_prefix = ""
        try:
            from services.bom_extractor import extract_chunks
            chunks = extract_chunks(content, filename)
            if chunks:
                snippet = "\n".join(c for c, _ in chunks[:3])[:2000]
                file_context_prefix = (
                    f"\n\n[Attached file: {filename} — category: {category}]\n"
                    f"Extracted content (first section):\n{snippet}\n\n"
                    f"Please analyse this file content as part of your response.\n"
                )
        except Exception as exc:
            logger.warning("Could not extract text from attachment for AI context: %s", exc)
            file_context_prefix = f"\n\n[Attached file: {filename} — category: {category}]\n"

        # Prepend file context to the message so the AI sees it
        enriched_message = (file_context_prefix + (message or f"Please review the attached {category} document: {filename}")).strip()
    else:
        enriched_message = message

    # ── 4. Normal chat processing ──────────────────────────────────────────
    cosmos_client = get_cosmos_client()
    session_data = cosmos_client.get_session(session_id)
    if not session_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    try:
        session = ChatSession.model_validate(session_data)
    except Exception as exc:
        logger.error("Session hydration failed: %s", exc)
        raise HTTPException(status_code=500, detail="Session data corrupt")

    # ── Scope future vector searches to this uploaded BOM ─────────────────
    if attachment_info.get("bom_id"):
        session.context.bom_id = attachment_info["bom_id"]

    # Store original user message (not the enriched one) in conversation history
    display_message = message or f"📎 Uploaded: {file.filename if file else 'file'}"
    session.conversation.append(ChatMessage(role="user", content=display_message))

    response_text, partial_bom, progress, complete = await _process_message(session, enriched_message)

    session.conversation.append(ChatMessage(role="assistant", content=response_text))
    session.context.progress_percentage = float(progress)
    session.updated_at = datetime.utcnow()
    if complete:
        session.status = "completed"
        session.completed_at = datetime.utcnow()
        if partial_bom:
            _save_bom_to_cosmos(cosmos_client, partial_bom, session, user_id)

    cosmos_client.update_session(session_id, session.model_dump(mode="json"))
    background_tasks.add_task(_archive_session_to_adls, session, user_id)

    suggestions = _generate_suggestions(response_text, session.context.category, partial_bom, complete)
    session_title = _session_title(session)

    resp = ChatMessageResponse(
        session_id=session_id,
        response=response_text,
        partial_bom=partial_bom,
        progress=progress,
        complete=complete,
        suggestions=suggestions,
        session_title=session_title,
    )
    # Attach the upload metadata as an extra field (Pydantic ignores it on the
    # response model but FastAPI returns it in the JSON)
    result = resp.model_dump()
    if attachment_info:
        result["attachment"] = attachment_info
    return result


@router.get("/session/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str):
    """Get session status and metadata."""
    cosmos_client = get_cosmos_client()
    session_data = cosmos_client.get_session(session_id)
    if not session_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session = ChatSession(**session_data)
    return SessionStatusResponse(
        session_id=session.session_id,
        category=session.context.category or "Unknown",
        status=session.status,
        progress=int(session.context.progress_percentage),
        message_count=len(session.conversation),
    )


@router.get("/session/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Return full conversation messages for Claude-like history loading.

    Tries ADLS transcript first (full fidelity), falls back to Cosmos.
    Returns list of {role, content, ts} objects.
    """
    cosmos_client = get_cosmos_client()
    session_data = cosmos_client.get_session(session_id)
    if not session_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session = ChatSession(**session_data)
    ctx = session.context
    messages = []
    for msg in session.conversation:
        messages.append({
            "role": msg.role,
            "content": msg.content,
        })
    project = (
        ctx.requirements.get("project")
        or (ctx.phase_data or {}).get("project_name")
        or (ctx.phase_data or {}).get("project")
    )
    return {
        "session_id": session_id,
        "category": ctx.category,
        "project": project,
        "status": session.status,
        "progress": int(ctx.progress_percentage),
        "messages": messages,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Chat History  (Cosmos index + ADLS full-transcript archive)
# ─────────────────────────────────────────────────────────────────────────────

class SessionSummary(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    status: str = "active"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int = 0
    category: Optional[str] = None
    project: Optional[str] = None
    progress: int = 0
    title: Optional[str] = None        # Auto-generated from first user message
    last_message: Optional[str] = None  # Preview of last assistant message


@router.get("/history", response_model=List[SessionSummary])
async def list_chat_history(user_id: str = "demo_user", limit: int = 30):
    """Return recent chat sessions for the sidebar — indexed from Cosmos DB."""
    cosmos_client = get_cosmos_client()
    try:
        sessions = cosmos_client.list_sessions(user_id=user_id, limit=limit)
    except Exception as exc:
        logger.warning("list_sessions failed: %s", exc)
        sessions = []
    result = []
    for s in sessions:
        ctx = s.get("context") or {}
        # Derive title + last_message preview from conversation if stored
        conversation = s.get("conversation") or []
        title: Optional[str] = None
        last_message: Optional[str] = None
        for msg in conversation:
            if not title and msg.get("role") == "user":
                raw = (msg.get("content") or "").strip()
                title = raw[:60].rstrip(",. ") + ("\u2026" if len(raw) > 60 else "")
        for msg in reversed(conversation):
            if msg.get("role") == "assistant":
                raw = (msg.get("content") or "").strip()
                last_message = raw[:80].rstrip(",. ") + ("\u2026" if len(raw) > 80 else "")
                break
        project = ctx.get("requirements", {}).get("project") or ctx.get("project_name")
        category_label = ctx.get("category")
        # Fallback title: first user message or project+category
        if not title:
            if project and category_label:
                title = f"{project} — {category_label}"
            elif project:
                title = project
            elif category_label:
                title = category_label
        result.append(SessionSummary(
            session_id=s.get("session_id") or s.get("_id") or "",
            user_id=s.get("user_id"),
            status=s.get("status", "active"),
            created_at=s.get("created_at"),
            updated_at=s.get("updated_at"),
            message_count=s.get("message_count", 0),
            category=category_label,
            project=project,
            progress=int(ctx.get("progress_percentage", 0)),
            title=title,
            last_message=last_message,
        ))
    return result


@router.get("/history/{session_id}/transcript")
async def get_session_transcript(session_id: str, user_id: str = "demo_user"):
    """Return full conversation for a session — from ADLS archive or Cosmos fallback."""
    # 1. Try ADLS first (cheapest, long-term store)
    try:
        adls_client = get_adls_client()
        date_prefix = datetime.utcnow().strftime("%Y/%m")
        adls_path = f"{user_id}/{date_prefix}/{session_id}.json"
        raw = adls_client.download_file(settings.adls_container_chat_history, adls_path)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        pass  # fall through to Cosmos

    # 2. Fall back to Cosmos (full session still has conversation array)
    cosmos_client = get_cosmos_client()
    session_data = cosmos_client.get_session(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    conv = session_data.get("conversation", [])
    ctx  = session_data.get("context", {})
    return {
        "session_id": session_id,
        "category": ctx.get("category"),
        "project": ctx.get("project_name"),
        "messages": [{"role": m.get("role"), "content": m.get("content"), "timestamp": m.get("timestamp")} for m in conv],
        "source": "cosmos",
    }


# ─────────────────────────────────────────────────────────────────────────────
# ADLS Archive helper
# ─────────────────────────────────────────────────────────────────────────────

def _save_bom_to_cosmos(cosmos_client, bom_data: dict, session: ChatSession, user_id: str):
    """Persist a completed BOM as a standalone document in the boms container."""
    try:
        bom_id = session.context.bom_id or f"bom_{uuid.uuid4().hex[:12]}"
        project = (
            session.context.requirements.get("project")
            or session.context.phase_data.get("project_name")
            or "New Project"
        )
        doc = {
            "_id": bom_id,
            "id": bom_id,
            "user_id": user_id,
            "session_id": session.session_id,
            "category": session.context.category,
            "project": project,
            "status": "draft",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "line_items": bom_data.get("line_items", []),
            "totals": bom_data.get("totals", {}),
            "metadata": bom_data,
        }
        cosmos_client.create_bom(doc)
        logger.info("Saved BOM %s to Cosmos (session=%s)", bom_id, session.session_id)
    except Exception as exc:
        logger.warning("_save_bom_to_cosmos failed (non-fatal): %s", exc)


def _emit_audit_event(user_id: str, action: str, session_id: str, details: dict = None):
    """Write a structured audit log entry.  Best-effort — never raises."""
    try:
        from api.audit import log_action
        log_action(
            user_id=user_id,
            action=action,
            resource_type="session",
            resource_id=session_id,
            details=details or {},
        )
    except Exception as exc:
        logger.debug("Audit log skipped (non-fatal): %s", exc)


def _archive_session_to_adls(session: ChatSession, user_id: str):
    """Write full conversation JSON to ADLS chat-history container (best-effort)."""
    try:
        adls_client = get_adls_client()
        date_prefix = datetime.utcnow().strftime("%Y/%m")
        path = f"{user_id}/{date_prefix}/{session.session_id}.json"
        # SessionContext has category but not project_name — pull from phase_data
        project = (session.context.phase_data or {}).get("project_name") or \
                  (session.context.phase_data or {}).get("project") or None
        payload = {
            "session_id": session.session_id,
            "user_id": user_id,
            "category": session.context.category,
            "project": project,
            "status": session.status,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat() if getattr(m, "timestamp", None) else None,
                }
                for m in session.conversation
            ],
        }
        adls_client.upload_file(
            settings.adls_container_chat_history,
            path,
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            overwrite=True,
        )
        logger.info("Archived session %s to ADLS at %s", session.session_id, path)
    except Exception as exc:
        logger.warning("ADLS archive failed (non-fatal): %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Follow-up Suggestions & Session Title Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _generate_suggestions(
    response_text: str,
    category: str,
    partial_bom: Optional[Dict[str, Any]],
    complete: bool,
) -> List[str]:
    """Return 3 contextual follow-up question strings for the user.

    We use deterministic logic keyed on category/completion state — no extra AI
    call needed, keeping latency and token cost low.
    """
    cat = (category or "").lower()

    if complete and partial_bom:
        items = partial_bom.get("line_items", [])
        count = len(items)
        return [
            f"Analyze cost-saving opportunities across these {count} items",
            "Export this BOM as CSV and generate an RFQ",
            "What are the EOL risks in this BOM?",
        ]

    if "data center" in cat or "colo" in cat:
        return [
            "What power and cooling capacity do I need?",
            "Add redundant networking components",
            "Show me the rack unit (U) breakdown",
        ]
    if "sd-wan" in cat:
        return [
            "How many sites require dual WAN?",
            "Compare Cisco vs Fortinet pricing for this deployment",
            "Add LTE failover for remote sites",
        ]
    if "cybersecurity" in cat or "security" in cat:
        return [
            "What compliance frameworks does this cover (PCI, HIPAA, SOC 2)?",
            "Add endpoint detection and response (EDR) tooling",
            "Estimate the annual licensing cost",
        ]
    if "eol" in cat:
        return [
            "Show me the EOL timeline for each flagged SKU",
            "Suggest modern replacements from the catalog",
            "Generate a refresh plan with cost impact",
        ]
    # Generic BOM follow-ups
    return [
        "Add more items to this BOM",
        "Analyze cost breakdown by category",
        "Export as RFQ and send for approval",
    ]


def _session_title(session: "ChatSession") -> Optional[str]:
    """Derive a human-readable title from the first user message."""
    for msg in session.conversation:
        if msg.role == "user":
            raw = msg.content.strip()
            title = raw[:60].rstrip(",. ")
            if len(raw) > 60:
                title += "…"
            return title
    return None


# ─────────────────────────────────────────────────────────────────────────────
# AI Orchestration
# ─────────────────────────────────────────────────────────────────────────────

async def _process_message(session: ChatSession, message: str) -> tuple:
    """Route: BOMOrchestrator (Azure AI Foundry / Anthropic) → rule-based fallback."""
    try:
        from ai.agents.orchestrator import BOMOrchestrator
        orch = BOMOrchestrator()
        session_dict = session.model_dump(mode="json")
        response_text, partial_bom, progress, complete = orch.process(session_dict, message)
        # Sync phase back to session context
        session.context.current_phase = session_dict.get("context", {}).get("current_phase", 1)
        return response_text, partial_bom, progress, complete
    except Exception as e:
        logger.warning("Orchestrator error: %s — falling back", e)
        return await _rule_based_fallback(session, message)


async def _call_azure_openai(client, session: ChatSession, message: str) -> tuple:
    """Call Azure OpenAI GPT-4 with 10-phase system prompt."""
    category = session.context.category or "Data Center / COLO"
    project = session.context.requirements.get("project", "New Project")
    system = (
        BOM_SYSTEM_PROMPT
        + f"\n\nCURRENT SESSION:\nCategory: {category}\nProject: {project}\n"
        f"Progress: {int(session.context.progress_percentage)}%\n"
        f"Requirements gathered: {json.dumps(session.context.requirements)}"
    )
    history = [{"role": "system", "content": system}]
    for m in session.conversation[-12:]:
        history.append({"role": m.role, "content": m.content})
    try:
        completion = client.chat.completions.create(
            model=settings.azure_openai_chat_deployment,
            messages=history,
            max_tokens=settings.azure_openai_max_tokens,
            temperature=settings.azure_openai_temperature,
        )
        response_text = completion.choices[0].message.content or ""
    except Exception:
        return await _rule_based_fallback(session, message)
    return _parse_ai_response(response_text, session)


async def _call_azure_foundry_anthropic(client, session: ChatSession, message: str) -> tuple:
    """Call Claude via Azure AI Foundry Anthropic proxy endpoint.
    Uses the deployment name (e.g. claude-opus-4-6) as the model identifier.
    """
    category = session.context.category or "Data Center / COLO"
    project = session.context.requirements.get("project", "New Project")
    system = (
        BOM_SYSTEM_PROMPT
        + f"\n\nCURRENT SESSION:\nCategory: {category}\nProject: {project}\n"
        f"Progress: {int(session.context.progress_percentage)}%"
    )
    history = [{"role": m.role, "content": m.content} for m in session.conversation[-12:]]
    try:
        response = client.messages.create(
            model=settings.azure_openai_chat_deployment,  # e.g. "claude-opus-4-6"
            max_tokens=settings.claude_max_tokens,
            system=system,
            messages=history,
        )
        response_text = response.content[0].text
    except Exception:
        return await _rule_based_fallback(session, message)
    return _parse_ai_response(response_text, session)


async def _call_anthropic(client, session: ChatSession, message: str) -> tuple:
    """Call direct Anthropic API with 10-phase system prompt."""
    category = session.context.category or "Data Center / COLO"
    project = session.context.requirements.get("project", "New Project")
    system = (
        BOM_SYSTEM_PROMPT
        + f"\n\nCURRENT SESSION:\nCategory: {category}\nProject: {project}\n"
        f"Progress: {int(session.context.progress_percentage)}%"
    )
    history = [{"role": m.role, "content": m.content} for m in session.conversation[-12:]]
    try:
        response = client.messages.create(
            model=settings.claude_model_default,
            max_tokens=settings.claude_max_tokens,
            system=system,
            messages=history,
        )
        response_text = response.content[0].text
    except Exception:
        return await _rule_based_fallback(session, message)
    return _parse_ai_response(response_text, session)


def _parse_ai_response(response_text: str, session: ChatSession) -> tuple:
    """Extract BOM JSON from AI response if present, compute progress."""
    partial_bom = None
    complete = False
    json_match = re.search(r"```json\s*([\s\S]*?)```", response_text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1).strip())
            if "line_items" in parsed and len(parsed["line_items"]) > 0:
                partial_bom = parsed
                complete = True
        except (json.JSONDecodeError, KeyError):
            pass
    user_count = sum(1 for m in session.conversation if m.role == "user")
    if complete:
        progress = 100
    elif session.context.category == "Data Center / COLO":
        progress = min(90, user_count * 9)
    else:
        progress = min(90, user_count * 18)
    return response_text, partial_bom, progress, complete


async def _rule_based_fallback(session: ChatSession, message: str) -> tuple:
    """Rule-based fallback when no AI credentials configured."""
    category = session.context.category or "Data Center / COLO"
    user_turns = sum(1 for m in session.conversation if m.role == "user")
    questions = _get_fallback_questions(category)
    if user_turns <= len(questions):
        q = questions[min(user_turns, len(questions) - 1)]
        progress = int((user_turns / (len(questions) + 1)) * 90)
        session.context.requirements[f"answer_{user_turns}"] = message
        return q, None, progress, False
    bom = _generate_fallback_bom(category, session.context.requirements)
    summary = (
        f"Based on your inputs, here is a **{category}** BOM for "
        f"**{bom.get('project', 'your project')}**.\n\n"
        f"**{len(bom['line_items'])} line items** — estimated total: "
        f"**${bom['totals']['total_otc']:,.0f}** OTC."
    )
    return summary, bom, 100, True


def _opening_question(category: str) -> str:
    qs = {
        "Data Center / COLO": "What is your target Day 1 cutover date, and which workloads are moving into the data center vs. staying in cloud/SaaS?",
        "SD-WAN": "How many branch sites need SD-WAN, and what is the primary bandwidth requirement per site?",
        "Cybersecurity": "How many endpoints (servers + workstations) need protection, and are there compliance requirements (PCI, HIPAA, SOC 2)?",
        "Network Equipment": "How many network ports are needed at the access layer, and do any locations require PoE for phones or access points?",
        "M365 & Power Platform": "How many users need licenses, and are you targeting M365 E3 or E5?",
        "Cloud Infrastructure": "Which Azure regions are required, and what types of workloads are you running?",
        "EOL Replacement": "What hardware is reaching end-of-life, and what is the support contract expiration date driving this?",
        "Laptops": "How many laptops are needed, and what are the primary user roles?",
    }
    return qs.get(category, "Can you describe the scope and scale of your IT infrastructure requirement?")


def _get_fallback_questions(category: str) -> List[str]:
    return [
        f"Question 1: What is the project name and target go-live date for this {category} deployment?",
        "Question 2: What is the approximate scale? (number of sites, users, servers, or racks as applicable)",
        "Question 3: Do you need high availability or redundancy (N+1 or active-active)?",
        "Question 4: What is the preferred vendor or any existing vendor contracts we should consider?",
        "Question 5: What is the estimated budget range for this project?",
    ]


def _generate_fallback_bom(category: str, requirements: dict) -> dict:
    """Generate a basic template BOM when AI is unavailable."""
    line_items = [
        {"line_number": 1, "category": "Compute", "description": "Dell PowerEdge R750 2x Xeon Gold 6330 512GB RAM", "sku": "DELL-PE-R750", "qty": 3, "unit": "/unit", "unit_price": 28500, "extended_price": 85500, "vendor": "Dell/CDW", "term": "one-time", "eol_flag": False, "order_sequence": 3, "notes": "HA compute cluster"},
        {"line_number": 2, "category": "Storage", "description": "Dell PowerStore 1000T NVMe 50TB usable", "sku": "DELL-PS1000T", "qty": 1, "unit": "/unit", "unit_price": 65000, "extended_price": 65000, "vendor": "Dell/CDW", "term": "one-time", "eol_flag": False, "order_sequence": 3, "notes": "Shared storage array"},
        {"line_number": 3, "category": "Networking", "description": "Cisco Nexus 9300 48p 25G ToR Switch", "sku": "N9K-C9300-48UX", "qty": 4, "unit": "/unit", "unit_price": 18500, "extended_price": 74000, "vendor": "Cisco/CDW", "term": "one-time", "eol_flag": False, "order_sequence": 2, "notes": "Top-of-rack switching"},
        {"line_number": 4, "category": "Physical", "description": "42U Server Rack Cabinet with PDU", "sku": "RACK-42U-PDU", "qty": 4, "unit": "/unit", "unit_price": 2200, "extended_price": 8800, "vendor": "PC Connection", "term": "one-time", "eol_flag": False, "order_sequence": 1, "notes": ""},
        {"line_number": 5, "category": "Power", "description": "APC Smart-UPS 10kVA N+1 config", "sku": "APC-UPS-10K", "qty": 2, "unit": "/unit", "unit_price": 12000, "extended_price": 24000, "vendor": "PC Connection", "term": "one-time", "eol_flag": False, "order_sequence": 1, "notes": "N+1 UPS configuration"},
        {"line_number": 6, "category": "Software Licenses", "description": "VMware vSphere Enterprise Plus per-core 3-node", "sku": "VMWARE-VS-ENT-PLUS", "qty": 1, "unit": "/bundle", "unit_price": 42000, "extended_price": 42000, "vendor": "VMware/CDW", "term": "one-time", "eol_flag": False, "order_sequence": 5, "notes": ""},
        {"line_number": 7, "category": "Maintenance", "description": "Dell ProSupport Plus 5Y on all compute and storage", "sku": "DELL-PROSUPPORT-5Y", "qty": 1, "unit": "/bundle", "unit_price": 28000, "extended_price": 28000, "vendor": "Dell", "term": "5yr", "eol_flag": False, "order_sequence": 3, "notes": "Required: hardware support"},
        {"line_number": 8, "category": "Spares", "description": "Critical Spares Kit drives NICs PSUs 10 percent", "sku": "SPARES-KIT-10PCT", "qty": 1, "unit": "/kit", "unit_price": 15000, "extended_price": 15000, "vendor": "Dell/CDW", "term": "one-time", "eol_flag": False, "order_sequence": 4, "notes": "10% of critical components"},
    ]
    total_otc = sum(i["extended_price"] for i in line_items)
    hw = sum(i["extended_price"] for i in line_items if i["category"] in ("Compute", "Storage", "Networking", "Physical", "Power", "Spares"))
    sw = sum(i["extended_price"] for i in line_items if i["category"] == "Software Licenses")
    svc = sum(i["extended_price"] for i in line_items if i["category"] == "Maintenance")
    return {
        "name": f"{requirements.get('project', 'Project')} - {category} BOM",
        "project": requirements.get("project", "New Project"),
        "category": category,
        "line_items": line_items,
        "totals": {"hardware": hw, "software": sw, "services": svc, "total_otc": total_otc, "tco_3year": total_otc + (svc * 2)},
        "warnings": ["Rule-based estimate - connect Azure OpenAI for AI-powered precision", "Verify all specs with SI before ordering"],
        "approvals_required": ["Buyer IT", "Seller IT", "SI Technical Team"],
    }
