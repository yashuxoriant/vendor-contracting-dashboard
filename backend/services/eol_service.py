"""
EOL/EOS Validation Service
Checks SKUs against the local reference database.
Fuzzy matching handles partial SKUs (e.g. 'C9300-48P' matches 'C9300-48P-A').
"""
from __future__ import annotations
import json
import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DATA_PATH = Path(__file__).parent.parent / "data" / "eol_skus.json"


@lru_cache(maxsize=1)
def _load_db() -> dict:
    """Load EOL database once and cache it in memory."""
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return raw.get("skus", {})
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _normalise(sku: str) -> str:
    """Normalise a SKU for comparison: uppercase, collapse whitespace/dashes."""
    return re.sub(r"[\s\-_/]+", "-", sku.upper().strip())


def check_eol_status(sku: str) -> dict:
    """
    Check the EOL/EOS status of a given SKU.

    Returns a dict:
      {
        "sku": str,
        "found": bool,
        "eol_flag": bool,          # True when end_of_sale is in the past
        "eos_flag": bool,          # True when end_of_support is in the past
        "severity": "none"|"warning"|"critical",
        "end_of_sale": str|None,
        "end_of_support": str|None,
        "replacement_sku": str|None,
        "replacement_desc": str|None,
        "message": str,
      }
    """
    db = _load_db()
    today = date.today()

    # --- Exact match first ---
    norm = _normalise(sku)
    record = db.get(sku) or db.get(norm)

    # --- Fuzzy prefix match (e.g. "PA-220" in description of "PA-220-HA") ---
    if record is None:
        for key, val in db.items():
            if norm.startswith(_normalise(key)) or _normalise(key).startswith(norm):
                record = val
                break

    if record is None:
        return {
            "sku": sku,
            "found": False,
            "eol_flag": False,
            "eos_flag": False,
            "severity": "none",
            "end_of_sale": None,
            "end_of_support": None,
            "replacement_sku": None,
            "replacement_desc": None,
            "message": f"SKU '{sku}' not found in EOL database — no action needed.",
        }

    # --- Parse dates safely ---
    def _parse(d: Optional[str]) -> Optional[date]:
        if not d:
            return None
        try:
            return datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            return None

    eos_date = _parse(record.get("end_of_sale"))
    eosupport_date = _parse(record.get("end_of_support"))

    eol_flag = bool(eos_date and eos_date <= today)
    eos_flag = bool(eosupport_date and eosupport_date <= today)

    # Override severity when dates have passed (upgrade warning → critical)
    severity = record.get("severity", "none")
    if eos_flag:
        severity = "critical"
    elif eol_flag and severity == "none":
        severity = "warning"

    # Build human-readable message
    parts = []
    if eos_flag:
        parts.append(f"End-of-Support reached on {eosupport_date}")
    elif eosupport_date:
        days_left = (eosupport_date - today).days
        if days_left <= 365:
            parts.append(f"End-of-Support in {days_left} days ({eosupport_date})")

    if eol_flag:
        parts.append(f"End-of-Sale was {eos_date}")
    elif eos_date:
        days_left = (eos_date - today).days
        if days_left <= 180:
            parts.append(f"End-of-Sale in {days_left} days ({eos_date})")

    if record.get("replacement_sku"):
        parts.append(f"Recommended replacement: {record['replacement_sku']}")

    message = "; ".join(parts) if parts else f"SKU '{sku}' is current — no EOL concerns."

    return {
        "sku": sku,
        "found": True,
        "eol_flag": eol_flag,
        "eos_flag": eos_flag,
        "severity": severity,
        "end_of_sale": record.get("end_of_sale"),
        "end_of_support": record.get("end_of_support"),
        "replacement_sku": record.get("replacement_sku"),
        "replacement_desc": record.get("replacement_desc"),
        "message": message,
    }


def check_bom_eol(line_items: list[dict]) -> list[dict]:
    """
    Run EOL check on a list of BOM line items.
    Each item should have at minimum a 'sku' or 'description' field.
    Returns enriched items with eol_flag, eol_warning, replacement_sku set.
    """
    enriched = []
    for item in line_items:
        sku = item.get("sku") or ""
        if sku:
            eol_info = check_eol_status(sku)
            item = {
                **item,
                "eol_flag": eol_info["eol_flag"] or eol_info["eos_flag"],
                "eol_warning": eol_info["message"] if eol_info["eol_flag"] or eol_info["eos_flag"] else None,
                "replacement_sku": eol_info.get("replacement_sku") or item.get("replacement_sku"),
            }
        enriched.append(item)
    return enriched
