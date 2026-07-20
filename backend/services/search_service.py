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

# Legacy global index — kept as fallback for direct-upload files with no category
_LEGACY_INDEX = "bom-embeddings"


def category_to_index_name(category: str) -> str:
    """
    Derive a deterministic Azure Search index name from a category string.

    Rules:
      • Lowercase, replace all non-alphanumeric chars with hyphens
      • Collapse consecutive hyphens, strip leading/trailing hyphens
      • Prefix with 'bom-' so all BOM indexes are easily identified
      • Max 128 chars (Azure Search limit)

    Examples:
      'SD-WAN'              → 'bom-sd-wan'
      'Data Center - COLO'  → 'bom-data-center-colo'
      'Network & Telecom'   → 'bom-network-telecom'
      'Cybersecurity'       → 'bom-cybersecurity'
      ''                    → 'bom-embeddings'  (legacy fallback)
    """
    if not category or not category.strip():
        return _LEGACY_INDEX
    slug = re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return f"bom-{slug}"[:128]


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
    Create (or update) an Azure Search index for the given category.
    Returns True if Azure Search is available, False if using mock.

    index_name should come from category_to_index_name(category).
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
            SimpleField(name="sp_file_id",      type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="content_hash",    type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="sp_etag",         type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="chunk_index",     type=SearchFieldDataType.Int32),
            # Searchable + filterable provenance fields
            # SearchableField enables search.ismatch() for flexible category/vendor filtering
            SearchableField(name="filename",        type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="vendor",          type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="category",        type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="folder_path",     type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="sharepoint_path", type=SearchFieldDataType.String, filterable=True),
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
        logger.error("ensure_index failed for '%s': %s", index_name, exc)
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
    Upload/merge BOM chunk documents into the category-specific search index.
    Returns the number of documents upserted.

    index_name should come from category_to_index_name(docs[0].category).
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


def _build_category_filter(category: str, vendor: str, bom_id: str) -> Optional[str]:
    """
    Build an OData filter expression that scopes the search to BOMs matching
    the session category and/or vendor.

    Uses search.ismatch() on the searchable category/folder_path/vendor fields
    for flexible, case-insensitive, partial matching.
    e.g. category='Network & Telecom' matches folder 'Networking', 'SD-WAN', etc.
    """
    parts: list = []

    if bom_id:
        safe = bom_id.replace("'", "''")
        parts.append(f"bom_id eq '{safe}'")
        return parts[0]  # bom_id is the most specific filter; skip category

    if category:
        # Normalise: take meaningful tokens, strip punctuation
        tokens = [t.strip() for t in re.split(r"[&/,\-]+", category) if len(t.strip()) >= 3]
        if tokens:
            # Match any token against category OR folder_path
            token_filters = [
                f"search.ismatch('{t.replace(chr(39), chr(39)*2)}', 'category, folder_path, sharepoint_path')"
                for t in tokens[:3]   # cap at 3 tokens to keep filter simple
            ]
            parts.append("(" + " or ".join(token_filters) + ")")

    if vendor:
        safe_v = vendor.replace("'", "''")
        parts.append(
            f"search.ismatch('{safe_v}', 'vendor, folder_path, sharepoint_path')"
        )

    return " and ".join(parts) if parts else None


def _mock_search_filtered(
    query_vector: List[float],
    top_k: int,
    bom_id: str,
    category: str,
    vendor: str,
) -> List[Dict]:
    """Mock store search with optional category/vendor filtering."""
    candidates = _mock_store
    if bom_id:
        candidates = [d for d in candidates if d["bom_id"] == bom_id]
    elif category:
        # Case-insensitive partial match on category or folder_path
        cat_lower = category.lower()
        candidates = [
            d for d in candidates
            if cat_lower in (d.get("category") or "").lower()
            or cat_lower in (d.get("folder_path") or "").lower()
        ]
    if vendor:
        vnd_lower = vendor.lower()
        candidates = [
            d for d in candidates
            if vnd_lower in (d.get("vendor") or "").lower()
            or vnd_lower in (d.get("folder_path") or "").lower()
        ]
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


def search_bom_context(
    query: str,
    top_k: int = 5,
    bom_id: Optional[str] = None,
    category: str = "",
    vendor: str = "",
    index_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Semantic vector search over BOM chunks.

    index_name routing:
      • Explicitly supplied → use that index directly
      • category provided, index_name omitted → derive from category_to_index_name(category)
      • Neither supplied → use legacy global index (bom-embeddings)

    3-attempt graceful degradation (within the chosen index):
      1. category + vendor filter
      2. category filter only (drop vendor)
      3. No filter (full index scan)
    """
    # Resolve which index to query
    resolved_index = index_name or (category_to_index_name(category) if category else _LEGACY_INDEX)

    query_vec = embed_text(query)

    sc, _ = _get_search_clients(resolved_index)
    if sc is None:
        results = _mock_search_filtered(query_vec, top_k, bom_id or "", category, vendor)
        if not results and (category or vendor):
            results = _mock_search_filtered(query_vec, top_k, bom_id or "", "", "")
        return results

    def _run_search(filter_expr: Optional[str]) -> List[Dict]:
        from azure.search.documents.models import VectorizedQuery
        vector_query = VectorizedQuery(
            vector=query_vec,
            k_nearest_neighbors=top_k,
            fields="embedding",
        )
        results = sc.search(
            search_text=None,
            vector_queries=[vector_query],
            filter=filter_expr,
            select=[
                "id", "bom_id", "filename", "vendor", "category",
                "chunk_text", "chunk_index", "folder_path", "sharepoint_path",
            ],
            top=top_k,
        )
        return [
            {
                "id":              r["id"],
                "bom_id":         r["bom_id"],
                "filename":       r["filename"],
                "vendor":         r.get("vendor", ""),
                "category":       r.get("category", ""),
                "folder_path":    r.get("folder_path", ""),
                "sharepoint_path": r.get("sharepoint_path", ""),
                "chunk_text":     r["chunk_text"],
                "chunk_index":    r.get("chunk_index", 0),
                "score":          round(r.get("@search.score", 0.0), 4),
            }
            for r in results
        ]

    try:
        # Since we're already in the category-specific index, the vendor filter
        # is the only one needed. category filter kept as belt-and-suspenders.
        filter_expr = _build_category_filter(category, vendor, bom_id or "")
        hits = _run_search(filter_expr)

        if not hits and vendor and category:
            filter_expr = _build_category_filter(category, "", bom_id or "")
            hits = _run_search(filter_expr)
            if hits:
                logger.info("SearchService[%s]: vendor filter removed; %d results",
                            resolved_index, len(hits))

        if not hits and (category or vendor):
            hits = _run_search(None)
            if hits:
                logger.info("SearchService[%s]: all filters removed; top-%d global results",
                            resolved_index, top_k)

        return hits
    except Exception as exc:
        logger.error("search_bom_context[%s] failed: %s", resolved_index, exc)
        return []


def delete_bom_chunks(bom_id: str, index_name: str = _LEGACY_INDEX) -> int:
    """Remove all indexed chunks for a given BOM from the specified index.
    Paginates in batches of 1000 so large BOMs are fully cleaned up.
    """
    sc, _ = _get_search_clients(index_name)
    if sc is None:
        return _mock_delete_by_bom(bom_id)

    try:
        total_deleted = 0
        while True:
            results = list(sc.search(
                search_text="*",
                filter=f"bom_id eq '{bom_id}'",
                select=["id"],
                top=1000,
            ))
            if not results:
                break
            keys = [{"id": r["id"]} for r in results]
            sc.delete_documents(documents=keys)
            total_deleted += len(keys)
            logger.info("SearchService: deleted %d chunks (batch) for bom_id=%s index=%s",
                        len(keys), bom_id, index_name)
            if len(results) < 1000:
                break   # last page
        return total_deleted
    except Exception as exc:
        logger.error("delete_bom_chunks failed: %s", exc)
        return 0

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
