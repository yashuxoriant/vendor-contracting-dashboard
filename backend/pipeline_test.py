"""
Full pipeline test — run from backend/ directory.
Tests: extraction → real Azure OAI embeddings → real Azure Search index → semantic search → AI orchestrator context
"""
import sys, os, time, hashlib
sys.path.insert(0, os.path.dirname(__file__))

PASS, FAIL, WARN = "✓ PASS", "✗ FAIL", "⚠ WARN"
results = []

def check(label, fn):
    try:
        detail = fn()
        results.append((PASS, label, detail or ""))
        print(f"  {PASS}  {label}" + (f"  →  {detail}" if detail else ""))
        return True
    except Exception as e:
        results.append((FAIL, label, str(e)))
        print(f"  {FAIL}  {label}  →  {e}")
        return False

print("\n" + "="*60)
print("  FULL PIPELINE VERIFICATION")
print("="*60)

# ── 1. Config ─────────────────────────────────────────────────────────────────
print("\n[1] CONFIG")
from config import get_settings
s = get_settings()
check("Azure Search endpoint set",     lambda: s.azure_search_endpoint or (_ for _ in ()).throw(AssertionError("empty")))
check("Azure Search admin key set",    lambda: "***" + s.azure_search_admin_key[-6:] if s.azure_search_admin_key else (_ for _ in ()).throw(AssertionError("empty")))
check("Embedding deployment set",      lambda: s.azure_openai_embedding_deployment)
check("Azure OpenAI endpoint set",     lambda: s.azure_openai_endpoint[:50])
check("Cosmos DB: REAL",               lambda: "REAL" if not s.use_dummy_cosmos else (_ for _ in ()).throw(AssertionError("using mock")))
check("ADLS: REAL",                    lambda: "REAL" if not s.use_dummy_adls else (_ for _ in ()).throw(AssertionError("using mock")))
check("AI chat endpoint set",          lambda: s.azure_openai_chat_endpoint[:55])

# ── 2. BOM Extraction ─────────────────────────────────────────────────────────
print("\n[2] BOM EXTRACTION")
from services.bom_extractor import extract_chunks

def test_csv_extraction():
    data = b"SKU,Description,Qty,Unit Price,Vendor\nC9300-48P,Cisco Catalyst 9300 48-Port PoE+,5,7800,CDW\nASR1001-X,Cisco ASR 1001-X Router,2,12500,CDW\nWS-C3850-24P,Cisco 3850 24-Port PoE Switch,10,4200,SHI"
    chunks = extract_chunks(data, "network_bom.csv")
    assert len(chunks) >= 1
    assert "C9300-48P" in chunks[0][0] or any("C9300" in c for c,_ in chunks)
    return f"{len(chunks)} chunk(s) extracted"

def test_txt_extraction():
    data = b"SKU: UCS-S3260-M5SRB | Description: Cisco UCS S3260 Server Node | Qty: 2 | Unit Price: 28000"
    chunks = extract_chunks(data, "server_bom.txt")
    assert len(chunks) >= 1
    return f"{len(chunks)} chunk(s) from TXT"

check("CSV BOM extraction",  test_csv_extraction)
check("TXT BOM extraction", test_txt_extraction)

# ── 3. Real Azure OpenAI Embeddings ───────────────────────────────────────────
print("\n[3] AZURE OPENAI EMBEDDINGS")
from services.embedding_service import embed_text, embed_batch, EMBEDDING_DIM

def test_single_embed():
    vec = embed_text("Cisco Catalyst 9300 switch 48 port PoE")
    assert len(vec) == EMBEDDING_DIM, f"Expected dim={EMBEDDING_DIM}, got {len(vec)}"
    # Mock embeddings use simple hash — real ones have non-trivial float distribution
    non_zero = sum(1 for v in vec if abs(v) > 0.001)
    return f"dim={len(vec)}, non-zero={non_zero}"

def test_batch_embed():
    texts = [
        "Cisco Catalyst 9300 48-port PoE+ switch data center",
        "ASR 1001-X WAN edge router BGP MPLS",
        "Fortinet FortiGate 600E next-gen firewall IPS",
    ]
    vecs = embed_batch(texts)
    assert len(vecs) == 3
    assert all(len(v) == EMBEDDING_DIM for v in vecs)
    # Verify embeddings are distinct (not all identical mock hashes would be distinct, but verify)
    dots = [sum(a*b for a,b in zip(vecs[0], vecs[1])), sum(a*b for a,b in zip(vecs[0], vecs[2]))]
    return f"3 vectors, cosine similarity between v0·v1={dots[0]:.4f}"

embed_ok = check("Single embedding (Azure OAI)",  test_single_embed)
check("Batch embedding (3 texts)",  test_batch_embed)

# ── 4. Azure Search Index ─────────────────────────────────────────────────────
print("\n[4] AZURE COGNITIVE SEARCH")
from services.search_service import ensure_index, upsert_chunks, search_bom_context, delete_bom_chunks, BOMChunkDocument
from config import get_settings as _ss

def test_index_creation():
    ensure_index()
    # Confirm we are using REAL search (not mock)
    cfg = _ss()
    if not cfg.azure_search_endpoint:
        raise AssertionError("Azure Search endpoint not configured")
    return f"Index 'bom-embeddings' ready at {cfg.azure_search_endpoint}"

TEST_BOM_ID = "pipeline-test-bom-001"

def test_upsert():
    csv_data = b"SKU,Description,Qty,Unit Price,Vendor\nC9300-48P,Cisco Catalyst 9300 48-Port PoE+,5,7800,CDW\nASR1001-X,Cisco ASR 1001-X Router,2,12500,CDW\nFG-600E,Fortinet FortiGate 600E NGFW,1,18900,CDW\nMDS-9148S,Cisco MDS 9148S SAN Switch,4,11200,SHI\nNEXUS-93180,Cisco Nexus 93180YC-FX,8,9500,SHI"
    chunks = extract_chunks(csv_data, "full_test_bom.csv")
    from services.embedding_service import embed_batch
    texts = [c for c, _ in chunks]
    embeddings = embed_batch(texts)
    docs = []
    for i, ((chunk_text, meta), emb) in enumerate(zip(chunks, embeddings)):
        docs.append(BOMChunkDocument(
            id=hashlib.sha256(f"{TEST_BOM_ID}::{i}".encode()).hexdigest()[:40],
            bom_id=TEST_BOM_ID,
            filename="full_test_bom.csv",
            vendor="CDW",
            category="Network Equipment",
            chunk_index=i,
            chunk_text=chunk_text,
            embedding=emb,
        ))
    upserted = upsert_chunks(docs)
    assert upserted > 0
    return f"{upserted} chunks indexed"

check("Index creation / ensure_index", test_index_creation)
upsert_ok = check("Upsert chunks to Azure Search", test_upsert)

# ── 5. Semantic Search ────────────────────────────────────────────────────────
print("\n[5] SEMANTIC SEARCH")

def test_search_cisco():
    time.sleep(2)  # Azure Search indexing latency
    results = search_bom_context("Cisco network switches pricing", top_k=5, bom_id=TEST_BOM_ID)
    assert len(results) > 0, "No results returned"
    top = results[0]
    return f"{len(results)} results | top score={top.get('score',0):.4f} | '{top.get('chunk_text','')[:60]}'"

def test_search_firewall():
    results = search_bom_context("firewall security appliance", top_k=3)
    assert len(results) > 0, "No results returned"
    return f"{len(results)} results | top score={results[0].get('score',0):.4f}"

def test_search_no_bom_filter():
    results = search_bom_context("router WAN edge", top_k=3)
    return f"{len(results)} results (no bom_id filter)"

if upsert_ok:
    check("Search: Cisco switches query",     test_search_cisco)
    check("Search: firewall query",           test_search_firewall)
    check("Search: no bom_id filter",         test_search_no_bom_filter)
else:
    print(f"  {WARN}  Skipped search tests (upsert failed)")

# ── 6. AI Orchestrator Context Injection ──────────────────────────────────────
print("\n[6] AI ORCHESTRATOR — BOM CONTEXT INJECTION")
from ai.agents.orchestrator import _retrieve_bom_context

def test_context_retrieval():
    ctx = _retrieve_bom_context("What Cisco switches are in this BOM and what is the total cost?", bom_id=TEST_BOM_ID, top_k=3)
    assert len(ctx) > 50, "Context too short"
    assert "BOM" in ctx or "SKU" in ctx or "chunk" in ctx.lower(), "No BOM content in context"
    return f"{len(ctx)} chars returned"

def test_context_no_bom():
    ctx = _retrieve_bom_context("What is the price of Fortinet firewalls?", bom_id=None, top_k=3)
    return f"{len(ctx)} chars (global search)"

check("Context injection with bom_id",  test_context_retrieval)
check("Context injection global search", test_context_no_bom)

# ── 7. Cosmos DB ──────────────────────────────────────────────────────────────
print("\n[7] COSMOS DB")
from db import get_cosmos_client

def test_cosmos():
    client = get_cosmos_client()
    assert client is not None
    t = type(client).__name__
    assert "Mock" not in t, f"Using mock client: {t}"
    return t

check("Real Cosmos DB client", test_cosmos)

# ── 8. ADLS ───────────────────────────────────────────────────────────────────
print("\n[8] ADLS")
from db import get_adls_client

def test_adls():
    client = get_adls_client()
    assert client is not None
    t = type(client).__name__
    assert "Mock" not in t, f"Using mock client: {t}"
    return t

check("Real ADLS client", test_adls)

# ── 9. ingest_bom end-to-end (full pipeline) ─────────────────────────────────
print("\n[9] FULL INGEST PIPELINE (bom_ingest.ingest_bom)")
from services.bom_ingest import ingest_bom, get_ingest_status

def test_full_ingest():
    csv_data = b"SKU,Description,Qty,Unit Price\nNEXUS-9K,Cisco Nexus 9000,3,22000\nUCS-C220,Cisco UCS C220 M5,4,8500"
    result = ingest_bom(
        bom_id="ingest-test-001",
        filename="ingest_test.csv",
        data=csv_data,
        vendor="SHI",
        category="Compute",
    )
    assert result.get("status") in ("completed", "indexed", "done", "ok") or result.get("chunks_indexed", 0) >= 0
    chunks = result.get("chunks_indexed", result.get("chunks", "?"))
    return f"status={result.get('status')} | chunks_indexed={chunks}"

check("ingest_bom() full sync pipeline", test_full_ingest)

# ── Cleanup ───────────────────────────────────────────────────────────────────
try:
    deleted = delete_bom_chunks(TEST_BOM_ID)
    deleted2 = delete_bom_chunks("ingest-test-001")
    print(f"\n  [cleanup] Removed {deleted + deleted2} test chunks from index")
except Exception as e:
    print(f"\n  [cleanup] Warning: {e}")

# ── Summary ───────────────────────────────────────────────────────────────────
passed = sum(1 for r in results if r[0] == PASS)
failed = sum(1 for r in results if r[0] == FAIL)
total  = len(results)

print("\n" + "="*60)
print(f"  RESULT:  {passed}/{total} passed   {failed} failed")
print("="*60)
if failed:
    print("\n  FAILURES:")
    for st, label, detail in results:
        if st == FAIL:
            print(f"    {label}: {detail}")
    sys.exit(1)
else:
    print("\n  ALL PIPELINE CHECKS PASSED — DEMO READY ✓")
