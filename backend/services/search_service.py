"""
Azure Cognitive Search Service
Manages the BOM embeddings index: creation, upsert, and semantic vector search.
Falls back to an in-memory mock store when Azure Search credentials are absent
(e.g. local development without Azure).

Index schema mirrors ma-workstream-planner/ingest_backend/ingest.py but is
scoped to BOMs:  bom_id, vendor, category, filename, chunk_text, chunk_index,
                 embedding (3072-dim vector).
"""
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services.embedding_service import EMBEDDING_DIM, embed_text

logger = logging.getLogger(__name__)

# Legacy single-index name — used as fallback for uncategorised BOMs
# and for backward-compat reads during the migration period.
_LEGACY_INDEX = "bom-embeddings"

# ── Category → index name mapping ─────────────────────────────────────────────
# Each logical BOM category gets its own Azure Search index so RAG queries are
# scoped to the relevant knowledge base and then further narrowed by vendor.
_CATEGORY_INDEX_MAP: Dict[str, str] = {
    # Network / Telecom family
    "SD-WAN":                "bom-network",
    "Network Equipment":     "bom-network",
    "Network & Telecom":     "bom-network",
    "Access Points":         "bom-network",
    # Data Centre family
    "Data Center / COLO":    "bom-datacenter",
    "Data Center":           "bom-datacenter",
    "COLO":                  "bom-datacenter",
    # Security
    "Cybersecurity":         "bom-cybersecurity",
    # Productivity / Cloud
    "M365 & Power Platform": "bom-m365",
    "Cloud Infrastructure":  "bom-cloud",
    # End-of-life / hardware refresh
    "EOL Replacement":       "bom-eol",
    # End-user computing
    "Laptops":               "bom-laptops",
    "End User Computing":    "bom-laptops",
}


def category_to_index_name(category: str) -> str:
    """Return the Azure Search index name for a BOM category.

    Falls back to the legacy 'bom-embeddings' index for unknown/empty
    categories so existing data is never silently lost.
    """
    if not category:
        return _LEGACY_INDEX
    if category in _CATEGORY_INDEX_MAP:
        return _CATEGORY_INDEX_MAP[category]
    # Case-insensitive substring fallback
    cat_lower = category.lower()
    for key, index in _CATEGORY_INDEX_MAP.items():
        if key.lower() in cat_lower or cat_lower in key.lower():
            return index
    return _LEGACY_INDEX


# ── Document model ─────────────────────────────────────────────────────────────

@dataclass
class BOMChunkDocument:
    id: str                      # deterministic chunk ID: sha256(sp_file_id::content_hash::chunk_index)
    bom_id: str                  # SharePoint Graph item ID (stable across renames/moves)
    filename: str
    vendor: str
    category: str                # top-level SharePoint folder name (e.g. 'SD-WAN', 'Data Center - COLO')
    chunk_index: int
    chunk_text: str
    embedding: List[float]
    sp_file_id: str = ""         # SharePoint Graph item ID (same as bom_id for SP files)
    content_hash: str = ""       # SHA-256 of raw file bytes — used for dedup / version tracking
    sp_etag: str = ""            # SharePoint eTag — persisted for quick-skip on subsequent syncs
    folder_path: str = ""        # parent folder(s) relative to drive root, e.g. 'SD-WAN'
    sharepoint_path: str = ""    # full relative path within the drive, e.g. 'SD-WAN/quote.xlsx'
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── In-memory mock store (local dev / CI) ─────────────────────────────────────

_mock_store: List[Dict[str, Any]] = []


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b + 1e-10)


def _mock_upsert(docs: List[BOMChunkDocument]) -> int:
    global _mock_store
    ids = {d["id"] for d in _mock_store}
    added = 0
    for doc in docs:
        entry = {
            "id": doc.id,
            "bom_id": doc.bom_id,
            "filename": doc.filename,
            "vendor": doc.vendor,
            "category": doc.category,
            "chunk_index": doc.chunk_index,
            "chunk_text": doc.chunk_text,
            "embedding": doc.embedding,
            **doc.metadata,
        }
        if doc.id in ids:
            _mock_store = [e if e["id"] != doc.id else entry for e in _mock_store]
        else:
            _mock_store.append(entry)
            added += 1
    return added


def _mock_search(query_vector: List[float], top_k: int = 5, bom_id: Optional[str] = None) -> List[Dict]:
    candidates = _mock_store
    if bom_id:
        candidates = [d for d in candidates if d["bom_id"] == bom_id]
    scored = [
        (d, _cosine_similarity(query_vector, d["embedding"]))
        for d in candidates
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [
        {**d, "score": round(s, 4)}
        for d, s in scored[:top_k]
        if s > 0.0
    ]


def _mock_delete_by_bom(bom_id: str) -> int:
    global _mock_store
    before = len(_mock_store)
    _mock_store = [d for d in _mock_store if d["bom_id"] != bom_id]
    return before - len(_mock_store)


# ── Azure Search index management ─────────────────────────────────────────────

def _chunk_doc_id(bom_id: str, content_hash: str, chunk_index: int) -> str:
    """Version-aware chunk ID. Changes when file content changes, preventing stale duplicates."""
    raw = f"{bom_id}::{content_hash[:16]}::{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def _get_search_clients(index_name: str = _LEGACY_INDEX):
    """Return (SearchClient, SearchIndexClient) or (None, None) if unconfigured."""
    try:
        from config import get_settings
        s = get_settings()
        endpoint = s.azure_search_endpoint
        key = s.azure_search_admin_key
        if not endpoint or "dummy" in endpoint or not key or "dummy" in key:
            return None, None

        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        from azure.search.documents.indexes import SearchIndexClient

        cred = AzureKeyCredential(key)
        idx_client = SearchIndexClient(endpoint=endpoint, credential=cred)
        sc = SearchClient(endpoint=endpoint, index_name=index_name, credential=cred)
        return sc, idx_client
    except Exception as exc:
        logger.warning("SearchService: client init failed (%s) — using mock", exc)
        return None, None


def ensure_index(index_name: str = _LEGACY_INDEX) -> bool:
    """
    Create the named Azure Search index if it doesn't exist.
    Returns True if Azure Search is available, False if using mock.
    """
    _, idx_client = _get_search_clients(index_name)
    if idx_client is None:
        logger.info("SearchService: using in-memory mock index")
        return False

    try:
        from azure.search.documents.indexes.models import (
            HnswAlgorithmConfiguration,
            SearchField,
            SearchFieldDataType,
            SearchIndex,
            SearchableField,
            SemanticConfiguration,
            SemanticField,
            SemanticPrioritizedFields,
            SemanticSearch,
            SimpleField,
            VectorSearch,
            VectorSearchProfile,
        )

        fields = [
            SimpleField(name="id",              type=SearchFieldDataType.String, key=True),
            SimpleField(name="bom_id",          type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="filename",        type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="vendor",          type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="category",        type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="chunk_index",     type=SearchFieldDataType.Int32),
            # Version-tracking & provenance fields — enable idempotent upserts, dedup, and RAG source attribution
            SimpleField(name="sp_file_id",      type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="content_hash",    type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="sp_etag",         type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="folder_path",     type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="sharepoint_path", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="chunk_text", type=SearchFieldDataType.String),
            SearchField(
                name="embedding",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=EMBEDDING_DIM,
                vector_search_profile_name="hnsw-profile",
            ),
        ]

        vector_search = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw-algo")],
            profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-algo")],
        )

        semantic_search = SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name="bom-semantic",
                    prioritized_fields=SemanticPrioritizedFields(
                        content_fields=[SemanticField(field_name="chunk_text")]
                    ),
                )
            ]
        )

        index = SearchIndex(
            name=index_name,
            fields=fields,
            vector_search=vector_search,
            semantic_search=semantic_search,
        )
        idx_client.create_or_update_index(index)
        logger.info("SearchService: Azure Search index '%s' ready", index_name)
        return True
    except Exception as exc:
        logger.error("ensure_index('%s') failed: %s", index_name, exc)
        return False


# ── Public API ─────────────────────────────────────────────────────────────────

def get_bom_indexed_state(bom_id: str, index_name: str = _LEGACY_INDEX) -> Optional[Dict[str, str]]:
    """
    Return the stored {content_hash, sp_file_id} for an already-indexed BOM,
    or None if no chunks exist for this bom_id.
    Used by the ingest pipeline to skip re-embedding unchanged content.
    """
    sc, _ = _get_search_clients(index_name)
    if sc is None:
        chunks = [d for d in _mock_store if d["bom_id"] == bom_id]
        if chunks:
            return {"content_hash": chunks[0].get("content_hash", ""),
                    "sp_file_id":   chunks[0].get("sp_file_id", "")}
        return None
    try:
        results = list(sc.search(
            search_text="*",
            filter=f"bom_id eq '{bom_id}'",
            select=["content_hash", "sp_file_id"],
            top=1,
        ))
        if results:
            return {"content_hash": results[0].get("content_hash") or "",
                    "sp_file_id":   results[0].get("sp_file_id") or ""}
        return None
    except Exception as exc:
        logger.warning("get_bom_indexed_state failed: %s", exc)
        return None


def upsert_chunks(docs: List[BOMChunkDocument], index_name: str = _LEGACY_INDEX) -> int:
    """
    Upload/merge BOM chunk documents into the named search index.
    Returns the number of documents upserted.
    """
    if not docs:
        return 0

    sc, _ = _get_search_clients(index_name)
    if sc is None:
        return _mock_upsert(docs)

    try:
        batch = [
            {
                "id":               doc.id,
                "bom_id":           doc.bom_id,
                "filename":         doc.filename,
                "vendor":           doc.vendor,
                "category":         doc.category,
                "chunk_index":      doc.chunk_index,
                "chunk_text":       doc.chunk_text,
                "embedding":        doc.embedding,
                "sp_file_id":       doc.sp_file_id,
                "content_hash":     doc.content_hash,
                "sp_etag":          doc.sp_etag,
                "folder_path":      doc.folder_path,
                "sharepoint_path":  doc.sharepoint_path,
                # NOTE: doc.metadata is NOT spread here — Azure Search index schema
                # only contains the fields above; extra chunk metadata (e.g. "sheet")
                # would cause a 400 from the service.
            }
            for doc in docs
        ]
        result = sc.merge_or_upload_documents(documents=batch)
        succeeded = sum(1 for r in result if r.succeeded)
        logger.info("SearchService: upserted %d/%d chunks", succeeded, len(docs))
        return succeeded
    except Exception as exc:
        logger.error("upsert_chunks failed: %s", exc)
        raise


def search_bom_context(
    query: str,
    top_k: int = 5,
    bom_id: Optional[str] = None,
    index_name: str = _LEGACY_INDEX,
    vendor: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Semantic vector search over BOM chunks.

    Precision strategy (Option B):
      1. Search category-specific index with vendor filter (most precise)
      2. If no results: retry same index without vendor filter
      3. If still no results and index ≠ legacy: fall back to legacy 'bom-embeddings'

    Args:
        query:      Natural-language search query.
        top_k:      Max results to return.
        bom_id:     Optionally scope search to a single BOM document.
        index_name: Target Azure Search index (derived from category).
        vendor:     Optional vendor filter (e.g. 'Cisco') for intra-category precision.
    """
    query_vec = embed_text(query)

    sc, _ = _get_search_clients(index_name)
    if sc is None:
        return _mock_search(query_vec, top_k=top_k, bom_id=bom_id)

    def _run_search(client, filter_expr: Optional[str]) -> List[Dict[str, Any]]:
        from azure.search.documents.models import VectorizedQuery
        vector_query = VectorizedQuery(
            vector=query_vec,
            k_nearest_neighbors=top_k,
            fields="embedding",
        )
        hits = client.search(
            search_text=None,
            vector_queries=[vector_query],
            filter=filter_expr,
            select=["id", "bom_id", "filename", "vendor", "category", "chunk_text", "chunk_index"],
            top=top_k,
        )
        return [
            {
                "id":          r["id"],
                "bom_id":      r["bom_id"],
                "filename":    r["filename"],
                "vendor":      r.get("vendor", ""),
                "category":    r.get("category", ""),
                "chunk_text":  r["chunk_text"],
                "chunk_index": r.get("chunk_index", 0),
                "score":       round(r.get("@search.score", 0.0), 4),
            }
            for r in hits
        ]

    try:
        # Build filter: bom_id and/or vendor
        filters: List[str] = []
        if bom_id:
            filters.append(f"bom_id eq '{bom_id}'")
        if vendor:
            safe_vendor = vendor.replace("'", "''")
            filters.append(f"vendor eq '{safe_vendor}'")
        filter_expr = " and ".join(filters) if filters else None

        # Pass 1 — category index + vendor filter
        results = _run_search(sc, filter_expr)

        # Pass 2 — if vendor filter returned nothing, retry without it
        if not results and vendor:
            bom_filter = f"bom_id eq '{bom_id}'" if bom_id else None
            logger.debug(
                "search_bom_context: no results with vendor='%s', retrying without vendor filter",
                vendor,
            )
            results = _run_search(sc, bom_filter)

        # Pass 3 — fall back to legacy index during migration
        if not results and index_name != _LEGACY_INDEX:
            logger.debug(
                "search_bom_context: no results in '%s', falling back to '%s'",
                index_name, _LEGACY_INDEX,
            )
            sc_legacy, _ = _get_search_clients(_LEGACY_INDEX)
            if sc_legacy:
                legacy_filter = f"bom_id eq '{bom_id}'" if bom_id else None
                results = _run_search(sc_legacy, legacy_filter)

        return results
    except Exception as exc:
        logger.error("search_bom_context failed: %s", exc)
        return []


def delete_bom_chunks(bom_id: str, index_name: str = _LEGACY_INDEX) -> int:
    """Remove all indexed chunks for a given BOM from the specified index."""
    sc, _ = _get_search_clients(index_name)
    if sc is None:
        return _mock_delete_by_bom(bom_id)

    try:
        # Search for all chunks belonging to this bom_id
        results = list(sc.search(
            search_text="*",
            filter=f"bom_id eq '{bom_id}'",
            select=["id"],
            top=1000,
        ))
        if not results:
            return 0
        keys = [{"id": r["id"]} for r in results]
        sc.delete_documents(documents=keys)
        logger.info("SearchService: deleted %d chunks for bom_id=%s", len(keys), bom_id)
        return len(keys)
    except Exception as exc:
        logger.error("delete_bom_chunks failed: %s", exc)
        return 0
