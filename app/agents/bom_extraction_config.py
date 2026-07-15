"""
app/agents/bom_extraction_config.py
────────────────────────────────────
BOM-domain ExtractionSchema — maps all 15 BOM_EXTRACTION_DECISION_KEYS to
ExtractionField instances with regex patterns and LLM hints.

Consumed by: app/agents/bom_creation_agent.py → state_extraction node.

Design notes:
  • Patterns are anchored loosely so they fire even in mid-sentence context.
  • The named capture group ``(?P<value>...)`` is required by extract_heuristic.
  • normalise functions fold case and strip punctuation where needed.
  • The LLM description is a one-sentence extraction hint — NOT a question to
    the user; it guides the extraction LLM only.
"""

from __future__ import annotations

import re

from app.memory_config import BOM_EXTRACTION_DECISION_KEYS
from framework.agents.state_extractor import ExtractionField, ExtractionSchema

# ─────────────────────────────────────────────────────────────────────────────
# Normaliser helpers
# ─────────────────────────────────────────────────────────────────────────────

def _lower_strip(s: str) -> str:
    return s.lower().strip(" ,.")


def _title_strip(s: str) -> str:
    return s.strip(" ,.").title()


def _bool_normalise(s: str) -> str:
    """Convert yes/no/true/false variants to 'yes' or 'no'."""
    if re.search(r"\b(yes|true|required|needed|engaged?)\b", s, re.I):
        return "yes"
    if re.search(r"\b(no|false|not\s+required|not\s+needed)\b", s, re.I):
        return "no"
    return s.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Field definitions
# ─────────────────────────────────────────────────────────────────────────────

_FIELDS: list[ExtractionField] = [

    ExtractionField(
        key="ma_phase",
        description=(
            "The M&A lifecycle phase: one of 'pre-close', 'day 1', "
            "'post-close', or 'steady-state'."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>pre[\s\-]?close|day\s*1|post[\s\-]?close|steady[\s\-]?state)\b",
                re.I,
            )
        ],
        normalise=_lower_strip,
    ),

    ExtractionField(
        key="workstream_category",
        description=(
            "The IT workstream category, e.g. 'Data Center / COLO', 'SD-WAN', "
            "'Cybersecurity', 'Network Equipment', 'M365', 'Cloud Infrastructure', "
            "'EOL Replacement', or 'Laptops / EUC'."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>"
                r"data\s+center\s*/\s*colo?"
                r"|data\s+center"
                r"|colo(?:cation)?"
                r"|sd[\s\-]?wan"
                r"|cyber\s*security"
                r"|network\s+equipment"
                r"|m365|microsoft\s+365"
                r"|cloud\s+infra(?:structure)?"
                r"|eol\s+replacement"
                r"|laptops?\s*/\s*euc"
                r"|laptops?"
                r"|end[\s\-]?user\s+computing"
                r")\b",
                re.I,
            )
        ],
        normalise=_title_strip,
    ),

    ExtractionField(
        key="triggering_event",
        description=(
            "The event driving this BOM request, e.g. acquisition close, "
            "hardware refresh, EOL replacement, or site migration."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>"
                r"acquisition\s+close"
                r"|hardware\s+refresh"
                r"|eol\s+replacement"
                r"|site\s+migration"
                r"|day\s*1\s+cutover"
                r"|merger"
                r"|divestiture"
                r")\b",
                re.I,
            )
        ],
        normalise=_title_strip,
    ),

    ExtractionField(
        key="site_entity_scope",
        description=(
            "The legal entity name(s) or site name(s) in scope for this BOM."
        ),
        patterns=[
            re.compile(
                r"(?:site|entity|location|facility)\s+(?:is|:)?\s*(?P<value>[A-Z][^\n,;]{3,60})",
                re.I,
            ),
        ],
        normalise=_title_strip,
    ),

    ExtractionField(
        key="site_classification_type",
        description=(
            "Physical site type: 'new build', 'existing DC', 'co-lo / cage', "
            "'cloud', or 'hybrid'."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>"
                r"new\s+build"
                r"|existing\s+(?:data\s+)?dc"
                r"|co[\s\-]?lo(?:\s+cage)?"
                r"|colocation"
                r"|cloud(?:\s+only)?"
                r"|hybrid"
                r")\b",
                re.I,
            )
        ],
        normalise=_lower_strip,
    ),

    ExtractionField(
        key="site_classification_size",
        description=(
            "Site scale: 'small' (<50 users), 'medium' (50-500), "
            "'large' (500-2000), or 'enterprise' (2000+).  "
            "Also accept raw user/server counts."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>small|medium|large|enterprise)\s+(?:site|dc|deployment)",
                re.I,
            ),
            re.compile(
                r"\b(?P<value>\d[\d,]+)\s+(?:users?|endpoints?|servers?|seats?)\b",
                re.I,
            ),
        ],
        normalise=_lower_strip,
    ),

    ExtractionField(
        key="site_classification_criticality",
        description=(
            "Business criticality: 'mission-critical', 'standard', or 'dev-test'."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>mission[\s\-]?critical|standard|dev[\s\-]?test|non[\s\-]?critical)\b",
                re.I,
            )
        ],
        normalise=_lower_strip,
    ),

    ExtractionField(
        key="conveyance_status",
        description=(
            "Which assets are conveyed in the deal.  Look for phrases like "
            "'all assets conveyed', 'hardware excluded', or specific asset lists."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>"
                r"all\s+assets?\s+conveyed"
                r"|no\s+assets?\s+conveyed"
                r"|hardware\s+(?:is\s+)?(?:excluded|included|conveyed)"
                r"|partial(?:ly)?\s+conveyed"
                r")\b",
                re.I,
            )
        ],
        normalise=_lower_strip,
    ),

    ExtractionField(
        key="asset_lifecycle_status",
        description=(
            "Hardware age, warranty status, or EOL/EOS flags mentioned in the conversation."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>"
                r"(?:\d+[\s\-]?year[\s\-]?old)"
                r"|eol|eos"
                r"|end[\s\-]of[\s\-](?:life|support)"
                r"|under\s+warranty"
                r"|out\s+of\s+warranty"
                r")\b",
                re.I,
            )
        ],
        normalise=_lower_strip,
    ),

    ExtractionField(
        key="required_by_date",
        description=(
            "The hard deadline or Day 1 cutover date, in any date format."
        ),
        patterns=[
            # ISO date: 2026-01-15
            re.compile(
                r"\b(?P<value>\d{4}[-/]\d{1,2}[-/]\d{1,2})\b"
            ),
            # US/UK: Jan 15, 2026 / 15 January 2026 / 01/15/2026
            re.compile(
                r"\b(?P<value>"
                r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
                r"|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
                r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
                r")\b",
                re.I,
            ),
            re.compile(
                r"\b(?P<value>\d{1,2}/\d{1,2}/\d{2,4})\b"
            ),
        ],
    ),

    ExtractionField(
        key="vendor_standard_preferred",
        description=(
            "Preferred vendor name(s) for procurement, "
            "e.g. 'CDW', 'SHI', 'PC Connection', 'Dell', 'Cisco'."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>"
                r"cdw|shi\b|pc\s+connection|dell(?:\s+direct)?|cisco(?:\s+direct)?"
                r"|hp(?:e)?|hewlett|lenovo|juniper|aruba|palo\s+alto"
                r")\b",
                re.I,
            )
        ],
        normalise=_title_strip,
    ),

    ExtractionField(
        key="vendor_open_to_competitive",
        description=(
            "Whether competitive quotes from multiple vendors are acceptable ('yes' or 'no')."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>"
                r"open\s+to\s+competitive"
                r"|competitive\s+(?:bid|quote|tender)"
                r"|single\s+vendor"
                r"|no\s+competitive"
                r")\b",
                re.I,
            ),
            re.compile(
                r"competitive\s+quotes?\s+(?:are\s+)?(?P<value>(?:not\s+)?(?:acceptable|required|needed|ok))",
                re.I,
            ),
        ],
        normalise=_bool_normalise,
    ),

    ExtractionField(
        key="existing_inventory_ref",
        description=(
            "Reference to an existing inventory document, BOM, or spreadsheet "
            "mentioned in the conversation."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>"
                r"rev\s*\d+"
                r"|(?:bom|inventory|spreadsheet|document)\s+(?:named?|called?|titled?|ref(?:erence)?)?[\s:]+[\w\-\.]{3,50}"
                r")\b",
                re.I,
            )
        ],
        normalise=_title_strip,
    ),

    ExtractionField(
        key="requestor",
        description=(
            "Who is requesting the BOM: 'Buyer IT', 'Seller IT', or 'SI / JBR'."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>"
                r"buyer\s+it"
                r"|seller\s+it"
                r"|si\s*/\s*jbr"
                r"|systems?\s+integrator"
                r")\b",
                re.I,
            )
        ],
        normalise=_title_strip,
    ),

    ExtractionField(
        key="vendor_engagement_required",
        description=(
            "Whether vendor outreach / RFQ is required for this BOM ('yes' or 'no')."
        ),
        patterns=[
            re.compile(
                r"\b(?P<value>"
                r"vendor\s+(?:engagement|outreach|rfq)\s+(?:is\s+)?(?:required|needed)"
                r"|no\s+vendor\s+(?:engagement|outreach)"
                r")\b",
                re.I,
            )
        ],
        normalise=_bool_normalise,
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Validate at module load: schema keys must match memory_config constants
# ─────────────────────────────────────────────────────────────────────────────

_defined_keys = {f.key for f in _FIELDS}
_expected_keys = set(BOM_EXTRACTION_DECISION_KEYS)
_missing = _expected_keys - _defined_keys
if _missing:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "bom_extraction_config: no ExtractionField defined for keys: %s",
        sorted(_missing),
    )

# ─────────────────────────────────────────────────────────────────────────────
# Public schema object
# ─────────────────────────────────────────────────────────────────────────────

BOM_EXTRACTION_SCHEMA = ExtractionSchema(
    name="bom_decision",
    fields=_FIELDS,
)

__all__ = ["BOM_EXTRACTION_SCHEMA"]
