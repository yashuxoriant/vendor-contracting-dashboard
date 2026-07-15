"""
app/memory_config.py — BOM domain memory configuration.

Defines:
  BOM_VALID_STEPS     — ordered tuple of all 13 pipeline step keys
  BOM_DEFAULT_STEP_MAP — human-readable label for each step key
  BOM_EXTRACTION_DECISION_KEYS — structured fields the agent must capture

These constants are consumed by:
  - framework/memory/store.py  (advance_step validation)
  - app/agents/bom_creation_agent.py  (LangGraph node routing, Step 9)
  - app/agents/bom_prompt_config.py   (prompt builder context, Step 6)

Source: Vendor_Contracting_Agent_System_Instructions — 13-step pipeline
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Valid pipeline steps  (insertion order matters — first = earliest)
# ---------------------------------------------------------------------------

BOM_VALID_STEPS: tuple[str, ...] = (
    "01_ma_phase",                  # Step  1 — Identify M&A Phase
    "02_workstream_category",       # Step  2 — Identify Workstream / Category
    "03_vendor_qualification",      # Step  3 — Determine Vendor Engagement Necessity
    "04_generic_intake",            # Step  4 — Generic Qualifying Information
    "05_missing_fields_detected",   # Step  5 — Identify Missing Fields
    "06_followup_complete",         # Step  6 — Follow-up Complete (all fields captured)
    "07_completeness_confirmed",    # Step  7 — Validate Completeness
    "08_category_resolved",         # Step  8 — Resolve Category Skill File
    "09_skill_invoked",             # Step  9 — Invoke Category Skill File
    "10_skill_output_validated",    # Step 10 — Receive & Validate Skill Output
    "11_human_review",              # Step 11 — Stage for Human Review (3-party approval)
    "12_rfq_handoff",               # Step 12 — RFQ Handoff
    "13_vendor_response_captured",  # Step 13 — Vendor Response Capture
)

# ---------------------------------------------------------------------------
# Human-readable labels (used in UI status strings and audit logs)
# ---------------------------------------------------------------------------

BOM_DEFAULT_STEP_MAP: dict[str, str] = {
    "01_ma_phase":                 "Identify M&A Phase",
    "02_workstream_category":      "Identify Workstream / Category",
    "03_vendor_qualification":     "Determine Vendor Engagement Necessity",
    "04_generic_intake":           "Generic Qualifying Information",
    "05_missing_fields_detected":  "Missing Fields Detected",
    "06_followup_complete":        "Follow-up Complete",
    "07_completeness_confirmed":   "Completeness Confirmed",
    "08_category_resolved":        "Category Skill File Resolved",
    "09_skill_invoked":            "Category Skill File Invoked",
    "10_skill_output_validated":   "Skill Output Validated",
    "11_human_review":             "Staged for Human Review",
    "12_rfq_handoff":              "RFQ Handoff",
    "13_vendor_response_captured": "Vendor Response Captured",
}

# ---------------------------------------------------------------------------
# Structured decision fields the agent must populate before reaching Step 7
# ---------------------------------------------------------------------------

BOM_EXTRACTION_DECISION_KEYS: tuple[str, ...] = (
    "ma_phase",                  # Pre-close / Day 1 / Post-close / Steady-state
    "workstream_category",       # Data Center / SD-WAN / Cybersecurity / EUC / etc.
    "triggering_event",          # What is driving this BOM request
    "site_entity_scope",         # Legal entity / site name(s) in scope
    "site_classification_type",  # New build / existing DC / co-lo / cloud / hybrid
    "site_classification_size",  # Small (<50 users) / Medium / Large / Enterprise
    "site_classification_criticality",  # Mission-critical / Standard / Dev-test
    "conveyance_status",         # Which assets are conveyed in the deal
    "asset_lifecycle_status",    # Age, warranty, EOL/EOS flags
    "required_by_date",          # Hard Day 1 cutover or procurement deadline
    "vendor_standard_preferred", # Preferred vendor (CDW / SHI / Dell / etc.)
    "vendor_open_to_competitive",# Whether competitive quotes are acceptable
    "existing_inventory_ref",    # Reference to existing inventory/BOM if any
    "requestor",                 # Who is requesting (Buyer IT / Seller IT / SI)
    "vendor_engagement_required",# True / False — does this need vendor outreach
)

# ---------------------------------------------------------------------------
# Computed helpers
# ---------------------------------------------------------------------------

_STEP_INDEX: dict[str, int] = {step: i for i, step in enumerate(BOM_VALID_STEPS)}


def step_index(step_key: str) -> int:
    """Return the 0-based position of *step_key* in BOM_VALID_STEPS."""
    try:
        return _STEP_INDEX[step_key]
    except KeyError:
        raise ValueError(f"Unknown BOM step key: {step_key!r}") from None


def is_valid_step(step_key: str) -> bool:
    """Return True if *step_key* is a recognised BOM pipeline step."""
    return step_key in _STEP_INDEX


def step_label(step_key: str) -> str:
    """Return the human-readable label for *step_key*."""
    return BOM_DEFAULT_STEP_MAP.get(step_key, step_key)


def missing_decision_keys(state: dict) -> list[str]:
    """
    Return the list of BOM_EXTRACTION_DECISION_KEYS not yet present (or None)
    in *state*.  Used by the agent to decide whether to advance past Step 5.
    """
    return [k for k in BOM_EXTRACTION_DECISION_KEYS if not state.get(k)]
