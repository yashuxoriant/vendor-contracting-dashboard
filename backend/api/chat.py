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
# Request / Response Models

# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    category: str
    project: Optional[str] = "New Project"
    user_id: Optional[str] = "demo_user"
    bom_id: Optional[str] = None  # Optional: scope chat to a specific indexed BOM
    domain_preselected: bool = False  # True when user chose the category from the UI picker
    existing_bom: Optional[Dict[str, Any]] = None  # Full BOM object when loading an existing BOM for editing
    existing_bom: Optional[Dict[str, Any]] = None  # Full BOM object when loading an existing BOM

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
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/start", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest):
    """Start a new BOM creation session."""
    cosmos_client = get_cosmos_client()
    session_id = f"session_{uuid.uuid4().hex[:12]}"

    # When the user selected a category from the UI picker before starting the session,
    # BOMAgent Steps 1-3 are already satisfied:
    #   Step 1 (M&A phase) — Day-1 is the business assumption for this application
    #   Step 2 (category)  — confirmed by the user's picker selection
    #   Step 3 (vendor engagement) — confirmed true (user is explicitly creating a BOM)
    # Seed agent_state with these known fields so the LLM never re-asks them, and
    # set current_step to 08_category_resolved to trigger Skill injection from turn 1.
    initial_agent_state: dict = {}
    if request.domain_preselected:
        initial_agent_state = {
            "ma_phase": "Day-1 Readiness",
            "workstream_category": request.category,
            "vendor_engagement_required": True,
            "current_step": "08_category_resolved",
        }

    # When an existing BOM is loaded, skip intake (Steps 1-9 already done) and
    # seed the agent with the BOM context so it can answer questions about it.
    if request.existing_bom:
        bom = request.existing_bom
        line_items = bom.get("lineItems") or bom.get("line_items") or []
        bom_name   = bom.get("name") or bom.get("project_name") or request.project
        initial_agent_state.update({
            "ma_phase": initial_agent_state.get("ma_phase", "Day-1 Readiness"),
            "workstream_category": request.category,
            "vendor_engagement_required": True,
            "current_step": "10_skill_output_received",
            "existing_bom_loaded": True,
            "bom_name": bom_name,
            "bom_line_count": len(line_items),
            "bom_total_value": bom.get("totalValue") or bom.get("total_value", 0),
            "bom_status": bom.get("status", "draft"),
        })

    context = SessionContext(
        category=request.category,
        requirements={"project": request.project},
        progress_percentage=0.0,
        bom_id=request.bom_id,
        domain_preselected=request.domain_preselected,
        agent_state=initial_agent_state,
    )

    if request.existing_bom:
        bom      = request.existing_bom
        line_items = bom.get("lineItems") or bom.get("line_items") or []
        bom_name = bom.get("name") or bom.get("project_name") or request.project
        total    = bom.get("totalValue") or bom.get("total_value", 0)
        welcome_content = (
            f"I've loaded **\"{bom_name}\"** \u2014 {len(line_items)} line items"
            + (f", total **${total:,.0f}**" if total else "") + ".\n\n"
            "What would you like to do?\n"
            "- Add, remove, or update line items\n"
            "- Explain any line item, SKU, or pricing\n"
            "- Rebuild or revise the BOM for a different scope\n"
            "- Export to Excel or prepare an RFQ"
        )
    else:
        welcome_content = (
            f"Hello! I'm your AI Procurement Assistant for **{request.category}**.\n\n"
            f"I'll help determine what equipment or services need to be procured "
            f"for **{request.project}** and prepare a draft procurement BOM for vendor review.\n\n"
            f"To get started, tell me a bit about the environment you're working with, "
            f"or simply reply and I'll guide you through the qualification."
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
    - Delegates to BOMCreationAgent (LangGraph)

    SSE frame format:
        data: {"token": "<text>", "done": false}   (per chunk)
        data: {"token": "", "done": true, "complete": bool, "progress": int, "bom": <obj|null>}
    """
    cosmos_client = get_cosmos_client()
    from fastapi.responses import StreamingResponse  # noqa: PLC0415
    from app.agents.bom_creation_agent import BOMCreationAgent  # noqa: PLC0415

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

        appended = _append_user_message_if_new(session.conversation, request.message)
        if appended:
            session.updated_at = datetime.utcnow()
            cosmos_client.update_session(request.session_id, session.model_dump(mode="json"))
            logger.debug("User message committed to Cosmos before stream (session=%s)", request.session_id)

    async def event_stream():
        from ai.agents.orchestrator import BOMOrchestrator  # noqa: PLC0415
        session_doc = cosmos_client.get_session(request.session_id) or {}
        orch = BOMOrchestrator()
        response_text, bom_data, progress, complete = await asyncio.to_thread(
            orch.process, session_doc, request.message
        )

        display_text = response_text
        if bom_data:
            import re as _re  # noqa: PLC0415
            display_text = _re.sub(r"```json[\s\S]*?```", "", response_text).strip()
            if not display_text:
                n = len(bom_data.get("line_items", []))
                display_text = f"BOM generated: **{n} line items** — see the panel on the right."

        yield "data: " + json.dumps({"token": display_text, "done": False}) + "\n\n"

        category = session_doc.get("context", {}).get("category", "")
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

        async with _get_session_lock(request.session_id):
            latest_data = cosmos_client.get_session(request.session_id)
            try:
                latest_session = ChatSession.model_validate(latest_data) if latest_data else session
            except Exception:
                latest_session = session

            latest_session.conversation.append(ChatMessage(role="assistant", content=display_text))
            latest_session.conversation = _dedup_conversation(latest_session.conversation)
            latest_session.context.progress_percentage = float(progress)
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
            details={"progress": progress, "complete": complete},
        )
        logger.info("Stream complete: session=%s progress=%d complete=%s", request.session_id, progress, complete)

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

        # ── 1. Upload to SharePoint (nested inside drive_path/category) ─────────
        try:
            from db.sharepoint_client import get_sharepoint_client
            sp = get_sharepoint_client()
            # Use the category from the form; fall back to the session's stored category
            effective_category = category.strip() or session.context.category or "BOMs"
            drive_root = sp.drive_path if sp is not None else "PWC_Vendor_Contracting_Hub"
            # Always nest inside drive root: Shared Documents/<drive_root>/<category>/file
            folder_path = f"{drive_root}/{effective_category}"
            if sp is not None:
                sp_result = sp.upload_file(content, filename, folder_path=folder_path)
                attachment_info["web_url"] = sp_result.get("web_url", "")
                attachment_info["sharepoint_folder"] = folder_path
                # Capture the SP Graph item ID for stable bom_id tracking
                sp_file_id = sp_result.get("id") or ""
                if sp_file_id:
                    attachment_info["sp_file_id"] = sp_file_id
                logger.info("Chat attachment uploaded to SharePoint folder='%s' file='%s'", folder_path, filename)
            else:
                logger.info("SharePoint mock — attachment '%s' not actually uploaded", filename)
                attachment_info["web_url"] = ""
                attachment_info["sharepoint_folder"] = folder_path
                sp_file_id = ""
        except Exception as exc:
            logger.warning("SharePoint upload for chat attachment failed (non-fatal): %s", exc)
            attachment_info["web_url"] = ""
            attachment_info["sharepoint_folder"] = category
            sp_file_id = ""

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
                category=effective_category,
                sp_file_id=sp_file_id,
                folder_path=folder_path,
                sharepoint_path=f"{folder_path}/{filename}",
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

    from app.agents.bom_creation_agent import BOMCreationAgent  # noqa: PLC0415
    _agent = BOMCreationAgent()
    _session_doc = cosmos_client.get_session(session_id) or {}
    response_text, partial_bom, progress, complete = await _agent.run(_session_doc, enriched_message)

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
        # Fallback title: first user message, or real project+category (skip placeholder)
        _real_project = project if (project and project != "New Project") else None
        if not title:
            if _real_project and category_label:
                title = f"{_real_project} \u2014 {category_label}"
            elif _real_project:
                title = _real_project
            elif category_label:
                title = category_label
        result.append(SessionSummary(
            session_id=s.get("session_id") or s.get("_id") or "",
            user_id=s.get("user_id"),
            status=s.get("status", "active"),
            created_at=s.get("created_at"),
            updated_at=s.get("updated_at"),
            message_count=s.get("message_count") or len(conversation),
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


def _opening_question(category: str) -> str:
    """Return a short, category-aware opening question for the /start welcome message."""
    _MAP = {
        "Network & Telecom":        "What M&A phase are you in, and which sites or entities are in scope?",
        "Network Equipment":        "What M&A phase are you in, and which sites or entities are in scope?",
        "SD-WAN":                   "What M&A phase are you in, and which sites or entities are in scope?",
        "Data Center / COLO":       "What M&A phase are you in, and is this a new build, existing DC, or co-lo?",
        "Data Center":              "What M&A phase are you in, and is this a new build, existing DC, or co-lo?",
        "End User Computing":       "What M&A phase are you in, and how many end users are in scope?",
        "EUC":                      "What M&A phase are you in, and how many end users are in scope?",
        "Identity & Security":      "What M&A phase are you in, and what identity platform is currently in use?",
        "Cybersecurity":            "What M&A phase are you in, and what security tooling is currently in place?",
        "M365 & Power Platform":    "What M&A phase are you in, and are existing M365 licenses conveying?",
        "Cloud Infrastructure":     "What M&A phase are you in, and which cloud provider(s) are in scope?",
    }
    return _MAP.get(category, "What M&A phase are you in, and what is driving this request?")


def _session_title(session: "ChatSession") -> Optional[str]:
    """Derive a human-readable title: prefer project name from requirements, else first user message."""
    # 1. Use requirements project if meaningful
    req_project = (session.context.requirements or {}).get("project", "")
    if req_project and req_project not in ("", "New Project"):
        category = session.context.category or ""
        if category:
            return f"{req_project} — {category}"
        return req_project

    # 2. Fall back to first user message
    for msg in session.conversation:
        if msg.role == "user":
            raw = msg.content.strip()
            title = raw[:60].rstrip(",. ")
            if len(raw) > 60:
                title += "…"
            return title
    return None


# ─────────────────────────────────────────────────────────────────────────────
