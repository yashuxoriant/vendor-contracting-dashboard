# extractor/catalog_builder.py
# Updated for per-license records with SKU, quantity, and unit-price tracking

import json
import re
from datetime import datetime
from config import (
    OUTPUT_FILE,
    ERROR_LOG_FILE,
    PROGRESS_FILE,
    MIN_VALID_PRICE,
    MAX_VALID_PRICE,
)


class CatalogBuilder:
    """
    Builds the master catalog of vendor quote line items.
    
    Each record represents a single line item (one SKU/service per record):
      {
        "file":       "Original filename",
        "proj":       "Panasonic | Idemia | Tenneco",
        "region":     "Americas | EMEA | APAC | Global",
        "country":    "Country name",
        "cat":        "Category",
        "vendor":     "Vendor name (normalised)",
        "service":    "Service/product name",
        "sku":        "Vendor SKU/Part Number",
        "qty":        Quantity (integer),
        "unit_price": Price per unit (USD),
        "line_total": qty × unit_price (USD),
        "year":       2025,
        "quarter":    "Q1",
        "folder":     "Sub-folder name (e.g., panasonic, idemia, tenneco)",
        "confidence": 0-100  (AI extraction confidence)
      }
    """

    def __init__(self, keep_confidence: bool = True):
        self.records         = []
        self.errors          = []
        self.skipped         = []
        self.duplicates      = []
        self.keep_confidence = keep_confidence

    # ============================================================
    # PUBLIC: Add records
    # ============================================================
    def add_records(self, records_list):
        """Add a list of records (one per line item)."""
        added = 0
        for record in records_list:
            if self.add_record(record):
                added += 1
        return added

    def add_record(self, record):
        """Add a single record after validation, cleaning, and dedup."""
        if not record:
            return False
        
        issues = self._validate(record)
        if issues:
            self.skipped.append({
                "file":   record.get("file", "unknown"),
                "service": record.get("service", "unknown"),
                "sku":    record.get("sku", ""),
                "issues": issues,
            })
            return False
        
        cleaned = self._clean(record)
        
        if self._is_duplicate(cleaned):
            self.duplicates.append({
                "file":    cleaned.get("file", ""),
                "service": cleaned.get("service", ""),
                "sku":     cleaned.get("sku", ""),
            })
            return False
        
        self.records.append(cleaned)
        return True

    def add_error(self, filename, category, error_msg):
        """Log an extraction error."""
        self.errors.append({
            "file":     filename,
            "category": category,
            "error":    str(error_msg),
            "time":     datetime.now().isoformat(),
        })

    # ============================================================
    # VALIDATION
    # ============================================================
    def _validate(self, record):
        """
        Validate a record. Returns list of issues (empty if valid).
        """
        issues = []
        
        # Required text fields
        if not record.get("cat"):
            issues.append("missing category")
        if not record.get("file"):
            issues.append("missing filename")
        if not record.get("service"):
            issues.append("missing service")
        
        # Unit price validation
        unit_price = record.get("unit_price", 0)
        try:
            unit_price = float(unit_price)
        except (TypeError, ValueError):
            issues.append(f"invalid unit_price: {unit_price}")
            return issues
        
        if unit_price <= 0:
            issues.append("unit_price is zero or negative")
        elif unit_price > MAX_VALID_PRICE:
            issues.append(f"unit_price too high: ${unit_price:,.0f}")
        
        # Quantity validation
        qty = record.get("qty", 1)
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            issues.append(f"invalid qty: {qty}")
            return issues
        
        if qty <= 0:
            issues.append("qty must be at least 1")
        elif qty > 10_000_000:  # sanity cap
            issues.append(f"qty unreasonably large: {qty}")
        
        # Optional: validate line_total math (warn but don't reject)
        line_total = record.get("line_total")
        if line_total is not None:
            try:
                line_total = float(line_total)
                expected = qty * unit_price
                if expected > 0 and abs(line_total - expected) / expected > 0.10:
                    # Math is off by >10% — flag but don't reject
                    record["_math_warning"] = (
                        f"line_total ${line_total:.2f} ≠ qty × unit_price ${expected:.2f}"
                    )
            except (TypeError, ValueError):
                pass
        
        return issues

    # ============================================================
    # CLEANING
    # ============================================================
    def _clean(self, record):
        """Normalise field types, vendor names, and derive missing values."""
        cleaned = dict(record)
        
        # ── Vendor normalisation ──────────────────────────────────
        cleaned["vendor"] = self._normalise_vendor(
            str(cleaned.get("vendor", "Unknown")).strip()
        )
        
        # ── Text fields ────────────────────────────────────────────
        cleaned["cat"]     = str(cleaned.get("cat", "")).strip()
        cleaned["service"] = str(cleaned.get("service", "")).strip()
        cleaned["file"]    = str(cleaned.get("file", "")).strip()
        
        # ── SKU normalisation ──────────────────────────────────────
        sku = str(cleaned.get("sku", "")).strip().upper()
        if not sku or sku in ("NONE", "NULL", "N/A", "—", "-"):
            sku = self._generate_sku(cleaned["vendor"], cleaned["service"])
        cleaned["sku"] = sku
        
        # ── Numeric fields ─────────────────────────────────────────
        try:
            cleaned["qty"] = max(1, int(cleaned.get("qty", 1)))
        except (TypeError, ValueError):
            cleaned["qty"] = 1
        
        try:
            cleaned["unit_price"] = round(float(cleaned.get("unit_price", 0)), 2)
        except (TypeError, ValueError):
            cleaned["unit_price"] = 0.0
        
        # ── Auto-derive line_total if missing ──────────────────────
        line_total = cleaned.get("line_total", 0)
        try:
            line_total = float(line_total)
        except (TypeError, ValueError):
            line_total = 0.0
        
        if line_total <= 0:
            line_total = round(cleaned["qty"] * cleaned["unit_price"], 2)
        
        cleaned["line_total"] = round(line_total, 2)
        
        # ── Year ───────────────────────────────────────────────────
        try:
            year = int(cleaned.get("year", 2025))
            if year < 2020 or year > 2030:
                year = 2025
        except (TypeError, ValueError):
            year = 2025
        cleaned["year"] = year
        
        # ── Quarter ────────────────────────────────────────────────
        q = str(cleaned.get("quarter", "Q1")).upper().strip()
        if q not in ("Q1", "Q2", "Q3", "Q4"):
            q = "Q1"
        cleaned["quarter"] = q
        
        # ── Project / Region / Country ────────────────────────────
        cleaned["proj"]    = self._normalise_project(cleaned.get("proj", ""))
        cleaned["region"]  = self._normalise_region(cleaned.get("region", ""))
        cleaned["country"] = str(cleaned.get("country", "")).strip()
        cleaned["folder"]  = str(cleaned.get("folder", "")).strip()
        
        # ── Confidence (optional) ──────────────────────────────────
        if self.keep_confidence:
            try:
                conf = int(cleaned.get("confidence", 0))
                cleaned["confidence"] = max(0, min(100, conf))
            except (TypeError, ValueError):
                cleaned["confidence"] = 0
        else:
            cleaned.pop("confidence", None)
        
        # ── Remove internal fields ────────────────────────────────
        for field in ("source", "_math_warning"):
            cleaned.pop(field, None)
        
        return cleaned

    # ============================================================
    # NORMALISATION HELPERS
    # ============================================================
    def _normalise_vendor(self, vendor):
        """Map vendor name variations to canonical form."""
        normalise_map = {
            "ntt data":       "NTT Data",
            "ntt docomo":     "NTT DOCOMO",
            "nttdata":        "NTT Data",
            "ntt-data":       "NTT Data",
            "trendmicro":     "TrendMicro",
            "trend micro":    "TrendMicro",
            "trend-micro":    "TrendMicro",
            "knowbe4":        "KnowBe4",
            "know be4":       "KnowBe4",
            "shi":            "SHI",
            "shi inc":        "SHI",
            "shi international": "SHI",
            "pc connection":  "PC Connection",
            "pcconnection":   "PC Connection",
            "cdw":            "CDW",
            "cdw-g":          "CDW",
            "equinix":        "Equinix",
            "quest":          "Quest",
            "quest software": "Quest",
            "servicenow":     "ServiceNow",
            "service now":    "ServiceNow",
            "microsoft":      "Microsoft",
            "msft":           "Microsoft",
            "proquire":       "Proquire LLC",
            "proquire llc":   "Proquire LLC",
            "ricoh":          "Ricoh",
            "honeywell":      "Honeywell",
            "copeland":       "Copeland LP",
            "copeland lp":    "Copeland LP",
            "thrive":         "Thrive",
            "cisco":          "Cisco",
            "cisco systems":  "Cisco",
            "palo alto":      "Palo Alto Networks",
            "paloalto":       "Palo Alto Networks",
            "cyberark":       "CyberArk",
            "forescout":      "Forescout",
            "vmware":         "VMware",
            "oracle":         "Oracle",
            "netapp":         "NetApp",
            "ibm":            "IBM",
            "pure storage":   "Pure Storage",
            "purestorage":    "Pure Storage",
            "zscaler":        "Zscaler",
        }
        v_lower = vendor.lower().strip()
        for key, canonical in normalise_map.items():
            if key in v_lower:
                return canonical
        return vendor

    def _normalise_project(self, proj):
        """Map project name variations to canonical form."""
        if not proj:
            return ""
        p_lower = str(proj).lower().strip()
        if "panasonic" in p_lower or p_lower.startswith("pas"):
            return "Panasonic"
        if "idemia" in p_lower:
            return "Idemia"
        if "tenneco" in p_lower or "lubrizol" in p_lower:
            return "Tenneco"
        return str(proj).strip()

    def _normalise_region(self, region):
        """Map region variations to canonical form."""
        if not region:
            return "Global"
        r_lower = str(region).lower().strip()
        if r_lower in ("americas", "amer", "us", "usa", "americas region", "north america"):
            return "Americas"
        if r_lower in ("emea", "europe", "eu", "emea region"):
            return "EMEA"
        if r_lower in ("apac", "asia pacific", "asia-pacific", "ap", "apj"):
            return "APAC"
        if r_lower in ("global", "worldwide", "ww", "multi-region"):
            return "Global"
        return str(region).strip() or "Global"

    def _generate_sku(self, vendor: str, service: str) -> str:
        """Generate a fallback SKU when the vendor doesn't provide one."""
        if not vendor or not service:
            return "UNKNOWN-SKU"
        
        v_prefix = re.sub(r"[^A-Z]", "", vendor.upper())[:3]
        s_words  = service.upper().split()[:2]
        s_prefix = "-".join(
            re.sub(r"[^A-Z0-9]", "", w)[:4]
            for w in s_words if w
        )
        
        if not v_prefix:
            v_prefix = "GEN"
        if not s_prefix:
            s_prefix = "SVC"
        
        return f"{v_prefix}-{s_prefix}"

    # ============================================================
    # DEDUPLICATION
    # ============================================================
    def _is_duplicate(self, record):
        """
        Check if this record is a duplicate of an existing one.
        Same file + same SKU + same unit price = duplicate.
        """
        for existing in self.records:
            if (existing.get("file")       == record.get("file") and
                existing.get("sku")        == record.get("sku") and
                existing.get("service")    == record.get("service") and
                existing.get("unit_price") == record.get("unit_price")):
                return True
        return False

    def deduplicate(self):
        """Remove exact duplicates from the records list."""
        seen   = set()
        unique = []
        for r in self.records:
            key = (
                f"{r.get('file','')}|"
                f"{r.get('sku','')}|"
                f"{r.get('service','')}|"
                f"{r.get('unit_price', 0)}|"
                f"{r.get('qty', 0)}"
            )
            if key not in seen:
                seen.add(key)
                unique.append(r)
        
        removed = len(self.records) - len(unique)
        if removed > 0:
            print(f"   🔄 Removed {removed} duplicates")
        self.records = unique

    # ============================================================
    # SAVE & STATS
    # ============================================================
    def save(self):
        """Save the catalog to disk along with errors and stats."""
        self.deduplicate()
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(self.records, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Saved {len(self.records)} records → {OUTPUT_FILE}")
        
        if self.errors:
            with open(ERROR_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.errors, f, indent=2)
            print(f"⚠️  {len(self.errors)} errors → {ERROR_LOG_FILE}")
        
        stats = self.get_stats()
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
        
        return OUTPUT_FILE

    def get_stats(self):
        """Compute summary statistics."""
        by_category = {}
        by_vendor   = {}
        by_sku      = {}
        by_project  = {}
        
        total_qty   = 0
        total_value = 0
        
        for r in self.records:
            cat   = r.get("cat",     "Unknown")
            ven   = r.get("vendor",  "Unknown")
            sku   = r.get("sku",     "UNKNOWN-SKU")
            proj  = r.get("proj",    "Unknown")
            qty   = r.get("qty",     0)
            up    = r.get("unit_price", 0)
            lt    = r.get("line_total", qty * up)
            
            total_qty   += qty
            total_value += lt
            
            # ── By Category ────────────────────────────────────
            if cat not in by_category:
                by_category[cat] = {
                    "count":       0,
                    "total_qty":   0,
                    "total_value": 0,
                    "unit_prices": [],
                    "min_unit":    float("inf"),
                    "max_unit":    0,
                }
            by_category[cat]["count"]       += 1
            by_category[cat]["total_qty"]   += qty
            by_category[cat]["total_value"] += lt
            by_category[cat]["unit_prices"].append(up)
            by_category[cat]["min_unit"] = min(by_category[cat]["min_unit"], up)
            by_category[cat]["max_unit"] = max(by_category[cat]["max_unit"], up)
            
            # ── By Vendor ──────────────────────────────────────
            if ven not in by_vendor:
                by_vendor[ven] = {
                    "count":       0,
                    "total_qty":   0,
                    "total_value": 0,
                    "unique_skus": set(),
                }
            by_vendor[ven]["count"]       += 1
            by_vendor[ven]["total_qty"]   += qty
            by_vendor[ven]["total_value"] += lt
            by_vendor[ven]["unique_skus"].add(sku)
            
            # ── By SKU ─────────────────────────────────────────
            if sku not in by_sku:
                by_sku[sku] = {
                    "count":       0,
                    "total_qty":   0,
                    "unit_prices": [],
                    "vendors":     set(),
                }
            by_sku[sku]["count"]     += 1
            by_sku[sku]["total_qty"] += qty
            by_sku[sku]["unit_prices"].append(up)
            by_sku[sku]["vendors"].add(ven)
            
            # ── By Project ─────────────────────────────────────
            if proj not in by_project:
                by_project[proj] = {
                    "count":       0,
                    "total_value": 0,
                }
            by_project[proj]["count"]       += 1
            by_project[proj]["total_value"] += lt
        
        # ── Convert sets to counts for JSON serialisation ──────
        for v_data in by_vendor.values():
            v_data["unique_skus"] = len(v_data["unique_skus"])
        for s_data in by_sku.values():
            s_data["vendors"] = len(s_data["vendors"])
        
        # ── Replace inf with 0 for JSON serialisation ──────────
        for c_data in by_category.values():
            if c_data["min_unit"] == float("inf"):
                c_data["min_unit"] = 0
        
        return {
            "total_records":      len(self.records),
            "total_errors":       len(self.errors),
            "total_skipped":      len(self.skipped),
            "duplicates_removed": len(self.duplicates),
            "total_qty":          total_qty,
            "total_value":        round(total_value, 2),
            "unique_vendors":     len(by_vendor),
            "unique_skus":        len(by_sku),
            "unique_categories":  len(by_category),
            "by_category":        by_category,
            "by_vendor":          by_vendor,
            "by_project":         by_project,
            "top_skus":           dict(
                sorted(by_sku.items(), key=lambda x: x[1]["count"], reverse=True)[:20]
            ),
            "generated_at":       datetime.now().isoformat(),
        }

    def print_summary(self):
        """Print a human-readable summary to console."""
        stats = self.get_stats()
        
        print(f"\n{'='*70}")
        print(f"📊 EXTRACTION SUMMARY")
        print(f"{'='*70}")
        print(f"✅ Records:           {stats['total_records']:>6}")
        print(f"❌ Errors:            {stats['total_errors']:>6}")
        print(f"⏭️  Skipped:          {stats['total_skipped']:>6}")
        print(f"🔄 Duplicates:        {stats['duplicates_removed']:>6}")
        print(f"")
        print(f"📦 Total Quantity:    {stats['total_qty']:>10,}")
        print(f"💰 Total Value:       ${stats['total_value']:>15,.2f}")
        print(f"🏢 Unique Vendors:    {stats['unique_vendors']:>6}")
        print(f"🏷️  Unique SKUs:      {stats['unique_skus']:>6}")
        print(f"🗂️  Categories:        {stats['unique_categories']:>6}")
        
        # ── By Project ─────────────────────────────────────
        if stats.get("by_project"):
            print(f"\n📁 By Project:")
            for proj, data in sorted(
                stats["by_project"].items(),
                key=lambda x: x[1]["total_value"],
                reverse=True
            ):
                print(
                    f"  {proj[:25]:<25} "
                    f"{data['count']:>4} items | "
                    f"${data['total_value']:>14,.2f}"
                )
        
        # ── By Category ────────────────────────────────────
        print(f"\n🗂️  By Category:")
        for cat, data in sorted(
            stats["by_category"].items(),
            key=lambda x: x[1]["total_value"],
            reverse=True
        ):
            prices = data.get("unit_prices", [])
            avg    = sum(prices) / len(prices) if prices else 0
            print(
                f"  {cat[:30]:<30} "
                f"{data['count']:>3} items | "
                f"Avg unit: ${avg:>10,.2f} | "
                f"Total: ${data['total_value']:>13,.2f}"
            )
        
        # ── By Vendor (top 10) ─────────────────────────────
        print(f"\n🏢 Top 10 Vendors (by item count):")
        for ven, data in sorted(
            stats["by_vendor"].items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )[:10]:
            print(
                f"  {ven[:25]:<25} "
                f"{data['count']:>3} items | "
                f"{data['unique_skus']:>3} SKUs | "
                f"${data['total_value']:>13,.2f}"
            )
        
        # ── Top SKUs (top 10 by frequency) ─────────────────
        if stats.get("top_skus"):
            print(f"\n🏷️  Top 10 SKUs (most frequently quoted):")
            for sku, data in list(stats["top_skus"].items())[:10]:
                prices = data.get("unit_prices", [])
                avg    = sum(prices) / len(prices) if prices else 0
                mn     = min(prices) if prices else 0
                mx     = max(prices) if prices else 0
                print(
                    f"  {sku[:22]:<22} "
                    f"{data['count']:>3}× | "
                    f"{data['vendors']} vendor(s) | "
                    f"Unit ${mn:>8,.2f} – ${mx:>8,.2f} (avg ${avg:>8,.2f})"
                )
        
        print(f"\n{'='*70}\n")
