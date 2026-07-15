"""
BOM File Extractor
Converts raw BOM file bytes into a list of text chunks suitable for embedding.

Supported formats:
  .xlsx  — multi-sheet workbook, each sheet chunked in row groups
  .csv   — single sheet, row groups
  .pdf   — text extraction via pdfminer / unstructured (best-effort)
  .docx  — paragraph + table extraction
  .txt / .md — plain text, sliding window chunks

BOM-specific intelligence:
  • Auto-detects the real header row (skips title/logo rows)
  • Emits structured text: "SKU: X | Description: Y | Qty: Z | Unit Price: ..."
    so the embedding captures column semantics, not just raw cell values.
  • Strips blank / summary-only rows
  • Returns (chunk_text, chunk_metadata) pairs
"""
import io
import logging
import os
import re
from typing import Iterator, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

ROWS_PER_CHUNK: int = int(os.getenv("BOM_ROWS_PER_CHUNK", "40"))
PROSE_CHUNK_SIZE: int = int(os.getenv("BOM_PROSE_CHUNK_SIZE", "800"))
PROSE_CHUNK_OVERLAP: int = int(os.getenv("BOM_PROSE_CHUNK_OVERLAP", "120"))

# Common BOM column synonyms used for structured text formatting
_COL_SYNONYMS = {
    # SKU / part number
    "sku":          "SKU",
    "part":         "SKU",
    "part number":  "SKU",
    "part_number":  "SKU",
    "part no":      "SKU",
    "item":         "SKU",
    "item no":      "SKU",
    "item number":  "SKU",
    "model":        "Model",
    "model number": "Model",
    "model no":     "Model",
    # Description
    "description":  "Description",
    "desc":         "Description",
    "product":      "Description",
    "product name": "Description",
    "name":         "Description",
    # Quantity
    "qty":          "Qty",
    "quantity":     "Qty",
    "count":        "Qty",
    "units":        "Qty",
    # Pricing
    "unit price":   "Unit Price",
    "unit_price":   "Unit Price",
    "price":        "Unit Price",
    "list price":   "List Price",
    "msrp":         "MSRP",
    "extended":     "Extended Price",
    "extended price": "Extended Price",
    "total":        "Total",
    # Vendor / manufacturer
    "vendor":       "Vendor",
    "manufacturer": "Manufacturer",
    "mfr":          "Manufacturer",
    "brand":        "Brand",
    # Category / type
    "category":     "Category",
    "type":         "Type",
    "product type": "Type",
    # Lead time / availability
    "lead time":    "Lead Time",
    "availability": "Availability",
    "stock":        "Stock",
}


# ── Header detection (same logic as ma-workstream extractors) ──────────────────

def _detect_header_row(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Find the real header row (max non-empty string cells) and promote it."""
    if df_raw.empty:
        return df_raw
    str_counts = df_raw.apply(
        lambda row: sum(1 for v in row if isinstance(v, str) and str(v).strip()),
        axis=1,
    )
    header_idx = int(str_counts.idxmax())
    raw_headers = df_raw.iloc[header_idx].fillna("").astype(str).str.strip()
    columns: list[str] = [h if h else f"Col_{i}" for i, h in enumerate(raw_headers)]

    # Deduplicate column names
    seen: dict = {}
    deduped: list[str] = []
    for col in columns:
        if col in seen:
            seen[col] += 1
            deduped.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            deduped.append(col)

    df = df_raw.iloc[header_idx + 1:].copy()
    df.columns = deduped
    df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    return df


def _normalise_col(col: str) -> str:
    return _COL_SYNONYMS.get(col.strip().lower(), col.strip())


def _row_to_text(row: pd.Series) -> str:
    """Convert a DataFrame row to 'Label: value | Label: value ...' format."""
    parts = []
    for col, val in row.items():
        if pd.isna(val) or str(val).strip() in ("", "nan"):
            continue
        label = _normalise_col(str(col))
        parts.append(f"{label}: {val}")
    return " | ".join(parts)


def _df_to_chunks(
    df: pd.DataFrame,
    filename: str,
    sheet_name: str = "",
    rows_per_chunk: int = ROWS_PER_CHUNK,
) -> List[Tuple[str, dict]]:
    """Split a DataFrame into text chunks of ~rows_per_chunk rows each."""
    chunks: List[Tuple[str, dict]] = []
    header = f"[File: {filename}" + (f" | Sheet: {sheet_name}" if sheet_name else "") + "]\n"

    for start in range(0, len(df), rows_per_chunk):
        end = min(start + rows_per_chunk, len(df))
        slice_df = df.iloc[start:end]
        rows_text = "\n".join(
            _row_to_text(row) for _, row in slice_df.iterrows()
            if _row_to_text(row).strip()
        )
        if not rows_text.strip():
            continue
        chunk_text = header + rows_text
        meta = {
            "sheet": sheet_name,
            "row_start": start,
            "row_end": end - 1,
            "row_count": end - start,
        }
        chunks.append((chunk_text, meta))
    return chunks


# ── Format-specific extractors ─────────────────────────────────────────────────

def _extract_xlsx(data: bytes, filename: str) -> List[Tuple[str, dict]]:
    chunks = []
    xl = pd.ExcelFile(io.BytesIO(data), engine="openpyxl")
    for sheet in xl.sheet_names:
        try:
            df_raw = xl.parse(sheet, header=None, dtype=str)
            df = _detect_header_row(df_raw)
            chunks.extend(_df_to_chunks(df, filename, sheet_name=sheet))
        except Exception as exc:
            logger.warning("XLSX sheet '%s' extraction error: %s", sheet, exc)
    return chunks


def _extract_csv(data: bytes, filename: str) -> List[Tuple[str, dict]]:
    try:
        # Try to detect encoding
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                df_raw = pd.read_csv(io.BytesIO(data), header=None, dtype=str, encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        df = _detect_header_row(df_raw)
        return _df_to_chunks(df, filename)
    except Exception as exc:
        logger.warning("CSV extraction error: %s", exc)
        return []


def _extract_pdf(data: bytes, filename: str) -> List[Tuple[str, dict]]:
    try:
        from unstructured.partition.pdf import partition_pdf
        elements = partition_pdf(file=io.BytesIO(data))
        full_text = "\n".join(str(e) for e in elements if str(e).strip())
        return _prose_to_chunks(full_text, filename)
    except ImportError:
        logger.warning("PDF extraction requires 'unstructured' library")
        return []
    except Exception as exc:
        logger.warning("PDF extraction error: %s", exc)
        return []


def _extract_docx(data: bytes, filename: str) -> List[Tuple[str, dict]]:
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
        lines = []
        for para in doc.paragraphs:
            if para.text.strip():
                lines.append(para.text.strip())
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    lines.append(" | ".join(cells))
        return _prose_to_chunks("\n".join(lines), filename)
    except ImportError:
        logger.warning("DOCX extraction requires 'python-docx' library")
        return []
    except Exception as exc:
        logger.warning("DOCX extraction error: %s", exc)
        return []


def _prose_to_chunks(text: str, filename: str) -> List[Tuple[str, dict]]:
    """Split prose text with a sliding window."""
    chunks = []
    size = PROSE_CHUNK_SIZE
    overlap = PROSE_CHUNK_OVERLAP
    words = text.split()
    step = max(1, size - overlap)
    i = 0
    idx = 0
    header = f"[File: {filename}]\n"
    while i < len(words):
        chunk_words = words[i: i + size]
        chunk_text = header + " ".join(chunk_words)
        chunks.append((chunk_text, {"word_start": i, "word_end": i + len(chunk_words)}))
        i += step
        idx += 1
    return chunks


# ── Public entry point ─────────────────────────────────────────────────────────

def extract_chunks(
    data: bytes,
    filename: str,
) -> List[Tuple[str, dict]]:
    """
    Extract text chunks from a BOM file.

    Args:
        data:     raw file bytes
        filename: original filename (used to determine format + in chunk text)

    Returns:
        List of (chunk_text, metadata_dict) tuples
    """
    ext = os.path.splitext(filename.lower())[1]

    dispatch = {
        ".xlsx": _extract_xlsx,
        ".xls":  _extract_xlsx,
        ".csv":  _extract_csv,
        ".pdf":  _extract_pdf,
        ".docx": _extract_docx,
        ".doc":  _extract_docx,
        ".txt":  lambda d, f: _prose_to_chunks(d.decode("utf-8", errors="replace"), f),
        ".md":   lambda d, f: _prose_to_chunks(d.decode("utf-8", errors="replace"), f),
    }

    extractor = dispatch.get(ext)
    if extractor is None:
        logger.warning("Unsupported BOM file extension: %s", ext)
        return []

    try:
        chunks = extractor(data, filename)
        logger.info("Extracted %d chunks from '%s'", len(chunks), filename)
        return chunks
    except Exception as exc:
        logger.error("extract_chunks failed for '%s': %s", filename, exc)
        return []
