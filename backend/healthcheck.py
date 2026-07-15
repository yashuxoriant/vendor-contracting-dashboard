"""Quick pipeline health check — run from backend/ directory."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

errors = []
warnings = []

# ── 1. Config ────────────────────────────────────────────────────────────────
try:
    from config import get_settings
    s = get_settings()
    print(f"[CFG] Port={s.port} | Cosmos={'REAL' if not s.use_dummy_cosmos else 'MOCK'} | ADLS={'REAL' if not s.use_dummy_adls else 'MOCK'}")
    print(f"[CFG] AI endpoint: {s.azure_openai_chat_endpoint[:60]}")
    if not s.azure_search_endpoint:
        warnings.append("WARN Azure Search not configured → using in-memory mock (data lost on restart)")
    if not s.azure_openai_embedding_deployment:
        warnings.append("WARN AZURE_OPENAI_EMBEDDING_DEPLOYMENT not set in .env → defaults to 'text-embedding-3-large'")
    print("OK  Config loaded")
except Exception as e:
    errors.append(f"FAIL Config: {e}")

# ── 2. Imports ───────────────────────────────────────────────────────────────
try:
    from api import chat, bom, analytics, templates, audit, catalog, sharepoint, notify, ingest
    print("OK  All routers import")
except Exception as e:
    errors.append(f"FAIL Router import: {e}")

try:
    from services.bom_extractor import extract_chunks
    from services.embedding_service import embed_text, embed_batch
    from services.search_service import ensure_index, upsert_chunks, search_bom_context, BOMChunkDocument
    from services.bom_ingest import ingest_bom, ingest_bom_background, get_ingest_status
    from services.bom_delta_pipeline import run_bom_delta_pipeline
    print("OK  All services import")
except Exception as e:
    errors.append(f"FAIL Service import: {e}")

try:
    from ai.client import get_ai_client, call_ai
    from ai.agents.orchestrator import BOMOrchestrator, _retrieve_bom_context
    print("OK  AI orchestrator imports")
except Exception as e:
    errors.append(f"FAIL AI import: {e}")

# ── 3. Embedding pipeline end-to-end ────────────────────────────────────────
try:
    import hashlib
    csv_data = b"SKU,Description,Qty,Unit Price,Vendor\nC9300-48P,Cisco Catalyst 9300,5,7800,CDW\nASR1001X,Cisco ASR Router,2,12500,CDW"
    chunks = extract_chunks(csv_data, "test_bom.csv")
    assert len(chunks) > 0, "No chunks extracted"
    print(f"OK  Extractor: {len(chunks)} chunks from CSV")

    texts = [c for c, _ in chunks]
    embeddings = embed_batch(texts)
    assert len(embeddings) == len(chunks), "Embedding count mismatch"
    assert len(embeddings[0]) > 100, "Embedding dimension too small"
    print(f"OK  Embeddings: {len(embeddings)} vectors dim={len(embeddings[0])}")

    ensure_index()
    docs = []
    for i, ((chunk_text, _), emb) in enumerate(zip(chunks, embeddings)):
        docs.append(BOMChunkDocument(
            id=hashlib.sha256(f"healthcheck::{i}".encode()).hexdigest()[:40],
            bom_id="healthcheck-bom",
            filename="test_bom.csv",
            vendor="CDW",
            category="Network Equipment",
            chunk_index=i,
            chunk_text=chunk_text,
            embedding=emb,
        ))
    upserted = upsert_chunks(docs)
    print(f"OK  Search index: {upserted} chunks upserted")

    results = search_bom_context("Cisco router pricing", top_k=3)
    print(f"OK  Search query: {len(results)} results returned")
    if results:
        score = results[0].get("score", 0)
        snippet = results[0].get("chunk_text", "")[:70]
        print(f"    Top hit score={score:.4f} | {snippet}")
except Exception as e:
    errors.append(f"FAIL Pipeline: {e}")

# ── 4. BOM retrieval context (orchestrator) ───────────────────────────────────
try:
    ctx = _retrieve_bom_context("what Cisco switches are in this BOM", bom_id=None, top_k=3)
    print(f"OK  _retrieve_bom_context: returned {len(ctx)} chars")
except Exception as e:
    errors.append(f"FAIL _retrieve_bom_context: {e}")

# ── 5. DB connectivity ────────────────────────────────────────────────────────
try:
    from db import get_cosmos_client
    client = get_cosmos_client()
    print(f"OK  Cosmos DB: {type(client).__name__} connected")
except Exception as e:
    errors.append(f"FAIL Cosmos DB: {e}")

try:
    from db import get_adls_client
    adls = get_adls_client()
    print(f"OK  ADLS: {type(adls).__name__} connected")
except Exception as e:
    errors.append(f"FAIL ADLS: {e}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "="*60)
for w in warnings:
    print(w)
if errors:
    print(f"\n{len(errors)} ERROR(S):")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print(f"\nALL CHECKS PASSED ({len(warnings)} warnings)")
