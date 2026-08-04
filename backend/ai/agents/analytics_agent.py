"""
Analytics Agent — natural language spend analysis over BOM data.

Usage:
    agent = AnalyticsAgent()
    result = agent.ask("Which vendor has the highest spend this month?")
    # returns {"answer": "...", "suggested_questions": [...]}
"""
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ai.client import call_ai

logger = logging.getLogger(__name__)

# ── Seed questions shown before the user types anything ─────────────────────
DEFAULT_SUGGESTIONS = [
    "Which vendor has the highest total spend?",
    "What is the average BOM cycle time vs. target?",
    "Which category has the most EOL risks?",
    "How many BOMs are pending approval?",
    "What are the top 5 most common SKUs across all BOMs?",
    "Show me spend trends over the last 6 months.",
]

ANALYTICS_SYSTEM = """You are a procurement and spend analytics expert assistant for an IT vendor-contracting platform.

You have access to a structured snapshot of BOM (Bill of Materials) data extracted from Cosmos DB.
Answer the user's question clearly, concisely, and numerically where data supports it.

Guidelines:
- Lead with the direct answer, then supporting numbers.
- Use bullet points for multi-part answers.
- Format currency as $X,XXX or $X.XM.
- If data is limited or empty, say so honestly and explain what would help.
- Never hallucinate numbers. Only reference what is in the DATA SNAPSHOT.
- At the end, suggest 2-3 follow-up questions the user might want to ask.
- Keep your total response under 250 words.

Respond in this JSON format (no markdown fences):
{
  "answer": "<your analysis text with \\n for line breaks>",
  "suggested_questions": ["<q1>", "<q2>", "<q3>"]
}
"""


def _build_data_snapshot() -> Dict[str, Any]:
    """Pull KPIs, spend, vendor, trend data from Cosmos and return as a compact dict."""
    try:
        from db import get_cosmos_client
        client = get_cosmos_client()
        boms: List[Dict] = client.list_boms({}, limit=500)
    except Exception as exc:
        logger.warning("Analytics agent: Cosmos unavailable — %s", exc)
        boms = []

    # KPIs
    total_boms = len(boms)
    cycle_times, pending_approval, eol_count = [], 0, 0
    by_status: Dict[str, int] = defaultdict(int)

    for b in boms:
        by_status[b.get("status", "draft")] += 1
        if b.get("status") == "approved" and b.get("created_at") and b.get("updated_at"):
            try:
                created = datetime.fromisoformat(b["created_at"].replace("Z", ""))
                updated = datetime.fromisoformat(b["updated_at"].replace("Z", ""))
                days = (updated - created).days
                if 0 <= days <= 365:
                    cycle_times.append(days)
            except Exception:
                pass
        approvals = b.get("approvals", [])
        if b.get("status") not in ("draft", "archived"):
            if not all(a.get("status") == "approved" for a in approvals):
                pending_approval += 1
        for item in b.get("line_items", []):
            if item.get("eol_flag"):
                eol_count += 1

    avg_cycle = round(sum(cycle_times) / len(cycle_times), 1) if cycle_times else 0.0

    # Spend by category and vendor
    cat_spend: Dict[str, float] = defaultdict(float)
    vendor_spend: Dict[str, float] = defaultdict(float)
    vendor_bom_count: Dict[str, int] = defaultdict(int)
    sku_count: Dict[str, int] = defaultdict(int)
    total_value = 0.0

    for b in boms:
        total_value += b.get("totals", {}).get("total_otc", 0)
        for item in b.get("line_items", []):
            cat = item.get("category") or "Other"
            vendor = item.get("vendor") or "Unknown"
            price = item.get("extended_price", 0)
            sku = item.get("sku") or item.get("description", "")[:40]
            cat_spend[cat] += price
            vendor_spend[vendor] += price
        for item in b.get("line_items", []):
            vendor = item.get("vendor") or "Unknown"
            vendor_bom_count[vendor] += 1
            sku = item.get("sku") or item.get("description", "")[:40]
            if sku:
                sku_count[sku] += 1

    # Monthly trends
    monthly: Dict[str, float] = defaultdict(float)
    for b in boms:
        try:
            created = datetime.fromisoformat(b.get("created_at", "").replace("Z", ""))
            key = created.strftime("%b %Y")
            monthly[key] += b.get("totals", {}).get("total_otc", 0)
        except Exception:
            pass

    def _mk(label: str):
        try:
            return datetime.strptime(label, "%b %Y")
        except Exception:
            return datetime.min

    top_vendors = sorted(vendor_spend.items(), key=lambda x: -x[1])[:8]
    top_cats = sorted(cat_spend.items(), key=lambda x: -x[1])[:8]
    top_skus = sorted(sku_count.items(), key=lambda x: -x[1])[:10]
    trend = [{"month": k, "spend": round(v, 2)}
             for k, v in sorted(monthly.items(), key=lambda x: _mk(x[0]))][-12:]

    return {
        "total_boms": total_boms,
        "total_value_usd": round(total_value, 2),
        "boms_by_status": dict(by_status),
        "avg_cycle_time_days": avg_cycle,
        "boms_pending_approval": pending_approval,
        "eol_line_items": eol_count,
        "top_vendors_by_spend": [{"vendor": v, "spend": round(s, 2), "bom_count": vendor_bom_count[v]} for v, s in top_vendors],
        "top_categories_by_spend": [{"category": c, "spend": round(s, 2)} for c, s in top_cats],
        "top_10_skus_by_frequency": [{"sku": s, "count": c} for s, c in top_skus],
        "monthly_spend_trend": trend,
    }


def _semantic_context(question: str) -> str:
    """Best-effort: search the BOM embedding index for question-relevant chunks."""
    try:
        from services.search_service import search_bom_context
        results = search_bom_context(query=question, top_k=3)
        if not results:
            return ""
        lines = [
            f"[{r.get('filename','?')} | {r.get('vendor','')}] {r['chunk_text'][:300]}"
            for r in results
        ]
        return "\nRELEVANT BOM CHUNKS:\n" + "\n---\n".join(lines)
    except Exception:
        return ""


class AnalyticsAgent:
    """
    Stateless agent. Call ask(question) → dict with answer + suggested_questions.
    """

    def ask(self, question: str) -> Dict[str, Any]:
        snapshot = _build_data_snapshot()
        sem_ctx = _semantic_context(question)

        user_content = (
            f"QUESTION: {question}\n\n"
            f"DATA SNAPSHOT:\n{json.dumps(snapshot, indent=2)}"
            + (f"\n\n{sem_ctx}" if sem_ctx else "")
        )

        raw = call_ai(
            messages=[{"role": "user", "content": user_content}],
            system=ANALYTICS_SYSTEM,
        )

        # Parse JSON response from AI
        if raw:
            # Strip accidental markdown fences
            clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            try:
                parsed = json.loads(clean)
                return {
                    "answer": parsed.get("answer", raw),
                    "suggested_questions": parsed.get("suggested_questions", DEFAULT_SUGGESTIONS[:3]),
                    "data_snapshot": snapshot,
                }
            except json.JSONDecodeError:
                # AI returned prose, not JSON — wrap it
                return {
                    "answer": raw,
                    "suggested_questions": DEFAULT_SUGGESTIONS[:3],
                    "data_snapshot": snapshot,
                }

        # Rule-based fallback
        return self._rule_based_answer(question, snapshot)

    def _rule_based_answer(self, question: str, snapshot: Dict) -> Dict[str, Any]:
        q = question.lower()

        if any(w in q for w in ("vendor", "supplier")):
            top = snapshot["top_vendors_by_spend"]
            if top:
                v = top[0]
                answer = f"Top vendor by spend: **{v['vendor']}** — ${v['spend']:,.0f} across {v['bom_count']} BOMs."
            else:
                answer = "No vendor spend data available yet."

        elif any(w in q for w in ("cycle", "time", "approval", "pending")):
            answer = (
                f"Avg BOM cycle time: **{snapshot['avg_cycle_time_days']} days**.\n"
                f"BOMs pending approval: **{snapshot['boms_pending_approval']}**."
            )

        elif any(w in q for w in ("eol", "end of life", "risk")):
            answer = f"There are **{snapshot['eol_line_items']} EOL line items** flagged across all BOMs."

        elif any(w in q for w in ("category", "spend", "breakdown")):
            top = snapshot["top_categories_by_spend"]
            lines = "\n".join(f"• {c['category']}: ${c['spend']:,.0f}" for c in top[:5])
            answer = f"Spend by category:\n{lines}" if lines else "No category spend data yet."

        elif any(w in q for w in ("total", "value", "how much")):
            answer = f"Total BOM value across all records: **${snapshot['total_value_usd']:,.0f}**. Total BOMs: {snapshot['total_boms']}."

        else:
            answer = (
                f"Data snapshot: {snapshot['total_boms']} BOMs | "
                f"Total value: ${snapshot['total_value_usd']:,.0f} | "
                f"Pending approval: {snapshot['boms_pending_approval']} | "
                f"EOL items: {snapshot['eol_line_items']}"
            )

        return {
            "answer": answer,
            "suggested_questions": DEFAULT_SUGGESTIONS[:3],
            "data_snapshot": snapshot,
        }
