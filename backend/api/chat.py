"""
Chat and BOM creation API endpoints — LangGraph architecture.
All AI responses go through BOMCreationAgent (app/agents/bom_creation_agent.py).
Rule-based fallback used only when the LangGraph agent raises unexpectedly.
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio
import uuid
import json
import re
import logging

from db import get_cosmos_client, get_adls_client, ChatSession, ChatMessage, SessionContext
from config import get_settings

import os as _os, sys as _sys
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, _PROJECT_ROOT)
from framework.security.guards import check_user_input, sanitise_llm_output, PromptInjectionError  # noqa: E402

router = APIRouter(prefix="/api/bom", tags=["chat"])
settings = get_settings()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    category: str
    project: Optional[str] = "New Project"
    user_id: Optional[str] = "demo_user"
    existing_bom: Optional[Dict[str, Any]] = None
    domain_preselected: bool = False

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

class SessionStatusResponse(BaseModel):
    session_id: str
    category: str
    status: str
    progress: int
    message_count: int

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
        requirements={"project": request.project, "loaded_bom": request.existing_bom},
        progress_percentage=0.0,
        domain_preselected=request.domain_preselected,
    )
    if request.existing_bom:
        item_count = len(request.existing_bom.get("lineItems", []))
        total = request.existing_bom.get("totalValue", 0)
        welcome_content = (
            f"I have loaded **{request.existing_bom.get('name', request.project)}** "
            f"({item_count} items, ${total:,.0f}).\n\n"
            f"Ask me anything about this BOM — vendor costs, savings opportunities, "
            f"item breakdown, what to change, or how to take it through the approval process."
        )
    else:
        if request.domain_preselected:
            # Domain was pre-selected from the UI picker — skip generic intro,
            # jump straight to M&A phase question (Step 1) with domain context.
            welcome_content = (
                f"I'm ready to build your **{request.category} BOM**.\n\n"
                f"I've loaded the {request.category} skill file and will walk you through "
                f"the required qualification questions.\n\n"
                f"**Step 1 — M&A Phase:** What phase is this engagement in?\n"
                f"- Day-1 Readiness (minimum viable cutover)\n"
                f"- TSA Exit / Cutover (active migration off TSA services)\n"
                f"- Full Integration / Standalone Build (post-TSA steady-state)"
            )
        else:
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
async def send_message(request: ChatMessageRequest):
    """Send a message in an active BOM creation session."""
    # ── Security: block prompt injection before any LLM call ──────────────
    try:
        check_user_input(request.message)
    except PromptInjectionError as exc:
        logger.warning("Injection attempt blocked | session=%s | pattern=%s", request.session_id, exc.matched_pattern)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message blocked by security policy.")
    # ──────────────────────────────────────────────────────────────────────
    cosmos_client = get_cosmos_client()
    session_data = cosmos_client.get_session(request.session_id)
    if not session_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    try:
        session = ChatSession.model_validate(session_data)
    except Exception as exc:
        logger.error("Session hydration failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Session data corrupt")
    session.conversation.append(ChatMessage(role="user", content=request.message))

    response_text, partial_bom, progress, complete = await _process_message(session, request.message)
    response_text = sanitise_llm_output(response_text)

    session.conversation.append(ChatMessage(role="assistant", content=response_text))
    session.context.progress_percentage = float(progress)
    session.updated_at = datetime.utcnow()
    if complete:
        session.status = "completed"
        session.completed_at = datetime.utcnow()

    cosmos_client.update_session(request.session_id, session.model_dump(mode="json"))

    # Archive full conversation to ADLS (best-effort — non-blocking, fails silently)
    _archive_session_to_adls(session, request.user_id or "demo_user")

    try:
        from api.audit import log_action
        log_action(
            user_id=request.user_id,
            action="chat_message",
            resource_type="session",
            resource_id=request.session_id,
            details={"progress": progress, "complete": complete, "has_bom": partial_bom is not None},
        )
    except Exception:
        pass

    return ChatMessageResponse(
        session_id=request.session_id,
        response=response_text,
        partial_bom=partial_bom,
        progress=progress,
        complete=complete,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Streaming SSE endpoint — LangGraph async (primary)
#   POST /api/bom/stream
#   Uses: framework/agents/llm_client.py (astream_llm)
#         app/agents/bom_prompt_config.py (make_prompt_config)
#         framework/instructions/store.py  (load_skill)
#         framework/security/guards.py     (check_user_input, sanitise_llm_output)
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/stream")
async def stream_message(request: ChatMessageRequest):
    """
    SSE streaming chat endpoint — Step 8 implementation.

    Emits newline-delimited Server-Sent Events:
      data: {"token": "...", "done": false}          ← text chunk
      data: {"token": "", "done": true, "complete": bool, "progress": int, "bom": {...}|null}

    Replaces the thread-based /chat/stream endpoint over time.
    Both endpoints coexist; existing callers of /chat/stream are unaffected.
    """
    import json as _j
    import re as _r

    # ── Security guard ──────────────────────────────────────────────────────
    try:
        check_user_input(request.message)
    except PromptInjectionError as exc:
        logger.warning("Injection blocked | session=%s | pattern=%s",
                       request.session_id, exc.matched_pattern)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Message blocked by security policy.")

    # ── Load session ────────────────────────────────────────────────────────
    cosmos_client = get_cosmos_client()
    session_data = cosmos_client.get_session(request.session_id)
    if not session_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Session not found")
    try:
        session = ChatSession.model_validate(session_data)
    except Exception as exc:
        logger.error("Session hydration failed: %s", exc)
        raise HTTPException(status_code=500, detail="Session data corrupt")

    # Append the user message before building the prompt
    session.conversation.append(ChatMessage(role="user", content=request.message))

    # ── Build prompt using framework/app prompt builders ────────────────────
    from app.agents.bom_prompt_config import make_prompt_config    # noqa: PLC0415
    from framework.agents.prompt_builder import build_llm_messages  # noqa: PLC0415
    from framework.agents.llm_client import astream_llm             # noqa: PLC0415
    from framework.instructions.store import load_skill             # noqa: PLC0415

    session_doc = session.model_dump(mode="json")
    category = (session.context.category or "Data Center / COLO")
    skill_text = load_skill(category)   # empty string if no .md file yet

    # Detect Step-7 confirmation: short approval word after >= 4 intake turns.
    # When true, force skill file injection regardless of extraction field count
    # and add a directive overriding the Skill File's "ask Phase 1 first" rule.
    _CONFIRM_RE = _r.compile(
        r"^(confirmed?|yes|ok|looks good|proceed|go ahead|generate|build it|"
        r"sounds good|correct|that.?s (correct|right)|approved?)[\.!]?$",
        _r.IGNORECASE,
    )
    user_turns_so_far = sum(1 for m in session.conversation if m.role == "user")
    force_generation = (
        bool(_CONFIRM_RE.match(request.message.strip()))
        and user_turns_so_far >= 4
    )

    config = make_prompt_config(session_doc, skill_text=skill_text,
                                force_generation=force_generation)
    system_prompt, messages = build_llm_messages(config, session_doc)

    # ── Rule-based fallback helper ───────────────────────────────────────────
    def _fallback_response() -> str:
        from ai.agents.orchestrator import BOMOrchestrator  # noqa: PLC0415
        orch = BOMOrchestrator()
        phase = session.context.current_phase or 1
        user_turns = sum(1 for m in session.conversation if m.role == "user")
        return orch._rule_based(category, phase, request.message, user_turns)

    # ── Async event generator ────────────────────────────────────────────────
    async def event_stream():
        full_text = ""
        had_content = False

        async for chunk in astream_llm(messages, system_prompt):
            if chunk:
                had_content = True
                full_text += chunk
                yield "data: " + _j.dumps({"token": chunk, "done": False}) + "\n\n"

        # If LLM returned nothing, use rule-based fallback
        if not had_content:
            fallback = _fallback_response()
            full_text = fallback
            yield "data: " + _j.dumps({"token": fallback, "done": True,
                                        "fallback": True}) + "\n\n"

        # Sanitise full assembled response before persisting
        full_text = sanitise_llm_output(full_text)

        # Detect BOM completion
        bom_data = None
        complete = False
        match = _r.search(r"```json\s*([\s\S]*?)```", full_text)
        if match:
            try:
                parsed = _j.loads(match.group(1).strip())
                if "line_items" in parsed and parsed["line_items"]:
                    bom_data = parsed
                    complete = True
            except Exception:
                pass

        # ── Extraction fallback ───────────────────────────────────────────
        # When the user confirmed intake (force_generation=True) but the LLM
        # generated prose instead of JSON fences, run a second synchronous
        # call to extract structured JSON from the prose response.
        if force_generation and not bom_data:
            try:
                from ai.client import call_ai  # noqa: PLC0415
                extraction_prompt = (
                    "The assistant just produced a BOM description in plain text.\n"
                    "Convert it into the exact JSON format below and output ONLY "
                    "the JSON object inside ```json...``` fences. "
                    "Do not include any other text.\n\n"
                    "Required format:\n"
                    "{\n"
                    '  "name": "ProjectName - Category BOM Rev 1",\n'
                    '  "project": "string",\n'
                    '  "category": "string",\n'
                    '  "revision": 1,\n'
                    '  "line_items": [\n'
                    '    {"line_number":1,"category":"string","description":"string",'
                    '"sku":"string","qty":1,"unit":"/unit","unit_price":0,'
                    '"extended_price":0,"vendor":"string","term":"one-time",'
                    '"eol_flag":false,"order_sequence":1,"notes":"string"}\n'
                    "  ],\n"
                    '  "totals": {"hardware":0,"software":0,"services":0,'
                    '"total_otc":0,"tco_3year":0},\n'
                    '  "warnings": [],\n'
                    '  "approvals_required": ["Buyer IT","Seller IT","SI Technical Team"]\n'
                    "}\n\n"
                    "Assistant prose to convert:\n" + full_text
                )
                extraction_msgs = [{"role": "user", "content": extraction_prompt}]
                extraction_result = await asyncio.to_thread(
                    call_ai, extraction_msgs,
                    "You are a JSON formatter. Output only valid JSON inside ```json...``` fences.",
                )
                if extraction_result:
                    em = _r.search(r"```json\s*([\s\S]*?)```", extraction_result)
                    if em:
                        ep = _j.loads(em.group(1).strip())
                        if "line_items" in ep and ep["line_items"]:
                            bom_data = ep
                            complete = True
                            logger.info("BOM extracted via fallback call: %d items",
                                        len(ep["line_items"]))
            except Exception as _ext_err:
                logger.warning("BOM extraction fallback failed: %s", _ext_err)

        user_count = sum(1 for m in session.conversation if m.role == "user")
        progress = 100 if complete else min(90, user_count * (
            9 if category == "Data Center / COLO" else 18))

        yield "data: " + _j.dumps({
            "token": "", "done": True,
            "complete": complete, "progress": progress,
            "bom": bom_data,
        }) + "\n\n"

        # Persist assistant response + updated session
        session.conversation.append(ChatMessage(role="assistant", content=full_text))
        session.updated_at = datetime.utcnow()

        # ── Post-stream: run state extraction to update intake fields ────
        # This populates session_doc["context"]["agent_state"] with collected
        # BOM_EXTRACTION_DECISION_KEYS so the next turn knows what's already known.
        try:
            from framework.agents.state_extractor import aextract            # noqa: PLC0415
            from app.agents.bom_extraction_config import BOM_EXTRACTION_SCHEMA  # noqa: PLC0415

            updated_session_doc = session.model_dump(mode="json")
            existing_agent_state = (
                updated_session_doc.get("context", {}).get("agent_state") or {}
            )
            extracted = await aextract(
                conversation=updated_session_doc.get("conversation", []),
                schema=BOM_EXTRACTION_SCHEMA,
                existing_state=existing_agent_state,
                use_llm=False,   # heuristic only in stream path — fast, no extra LLM call
            )
            # Merge extracted fields back into context
            ctx = updated_session_doc.get("context") or {}
            ctx["agent_state"] = extracted
            updated_session_doc["context"] = ctx
            # Validate intake completeness and advance pipeline step marker
            from app.agents.bom_prompt_config import is_intake_complete    # noqa: PLC0415
            from app.memory_config import BOM_VALID_STEPS                  # noqa: PLC0415
            if is_intake_complete(extracted):
                current_step = extracted.get("current_step") or "01_ma_phase"
                if current_step < "09_skill_invoked":
                    extracted["current_step"] = "09_skill_invoked"
            await asyncio.to_thread(
                cosmos_client.update_session,
                request.session_id,
                updated_session_doc,
            )
        except Exception as _exc:
            logger.warning("Post-stream state extraction failed: %s", _exc)
            await asyncio.to_thread(
                cosmos_client.update_session,
                request.session_id,
                session.model_dump(mode="json"),
            )
        # Re-archive to ADLS after every stream turn so the transcript endpoint
        # always has the full conversation, not just the session-creation welcome.
        await asyncio.to_thread(_archive_session_to_adls, session, request.user_id or "demo_user")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        result.append(SessionSummary(
            session_id=s.get("session_id") or s.get("_id") or "",
            user_id=s.get("user_id"),
            status=s.get("status", "active"),
            created_at=s.get("created_at"),
            updated_at=s.get("updated_at"),
            message_count=s.get("message_count", 0),
            category=ctx.get("category"),
            project=ctx.get("project_name"),
            progress=int(ctx.get("progress_percentage", 0)),
        ))
    return result


@router.get("/history/{session_id}/transcript")
async def get_session_transcript(session_id: str, user_id: str = "demo_user"):
    """Return full conversation for a session.

    Cosmos is checked FIRST — it holds every turn appended by the stream
    endpoint. ADLS is the fallback; it is re-written after every stream turn
    but unavailable when in-memory Cosmos (mock) was restarted.
    The previous order (ADLS first) caused welcome-only transcripts to be
    returned because _archive_session_to_adls was historically only called at
    session creation.
    """
    # 1. Cosmos first — full conversation including all stream turns
    cosmos_client = get_cosmos_client()
    session_data = cosmos_client.get_session(session_id)
    if session_data:
        conv = session_data.get("conversation", [])
        ctx  = session_data.get("context", {})
        if conv:
            return {
                "session_id": session_id,
                "category": ctx.get("category"),
                "project": ctx.get("project_name"),
                "messages": [
                    {"role": m.get("role"), "content": m.get("content"), "timestamp": m.get("timestamp")}
                    for m in conv
                ],
                "source": "cosmos",
            }

    # 2. ADLS fallback (re-archived after every stream turn)
    try:
        adls_client = get_adls_client()
        date_prefix = datetime.utcnow().strftime("%Y/%m")
        adls_path = f"{user_id}/{date_prefix}/{session_id}.json"
        raw = adls_client.download_file(settings.adls_container_chat_history, adls_path)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        pass

    raise HTTPException(status_code=404, detail="Session not found")


# ─────────────────────────────────────────────────────────────────────────────
# ADLS Archive helper
# ─────────────────────────────────────────────────────────────────────────────

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
# AI Orchestration
# ─────────────────────────────────────────────────────────────────────────────

async def _process_message(session: ChatSession, message: str) -> tuple:
    """
    Route one conversational turn through the BOM creation LangGraph.
    Falls back to rule-based responses if the agent raises unexpectedly.
    """
    try:
        from app.agents.bom_creation_agent import BOMCreationAgent  # noqa: PLC0415
        agent = BOMCreationAgent()
        session_dict = session.model_dump(mode="json")
        response_text, partial_bom, progress, complete = await agent.run(session_dict, message)
        return response_text, partial_bom, progress, complete
    except Exception as exc:
        logger.warning("BOMCreationAgent error: %s — falling back to rule-based", exc)
        return await _rule_based_fallback(session, message)


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
        f"Based on your inputs, here is a **{category}** BOM draft with "
        f"**{len(bom['line_items'])} line items** totalling "
        f"**${bom['totals']['total_otc']:,.0f}** OTC.\n\n"
        "Note: This is a rule-based template estimate. "
        "Connect Azure OpenAI credentials for AI-powered precision sizing."
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
