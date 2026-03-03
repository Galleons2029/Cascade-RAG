#!/usr/bin/env python3
"""End-to-end test for the knowledge management page API."""

import json
import time
import urllib.request
import urllib.error
import sys
import os
import tempfile

BASE = "http://localhost:8000/api/v1"
TEST_KB = "test_kb_e2e"
PASSED = 0
FAILED = 0


def api(method, path, body=None, content_type="application/json"):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        return {"_error": e.code, "_body": body_text}


def check(label, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ✓ {label}")
    else:
        FAILED += 1
        print(f"  ✗ {label}  {detail}")


# ── 1. Stats endpoint ────────────────────────────────────────
print("\n=== 1. Stats endpoint ===")
stats = api("GET", "/knowledge/stats")
check("Stats returns data", "data" in stats)
check("totalCollections >= 0", stats.get("data", {}).get("totalCollections", -1) >= 0)

# ── 2. List collections ──────────────────────────────────────
print("\n=== 2. List collections ===")
collections = api("GET", "/knowledge/collections")
check("Collections returns data", "data" in collections)
names = [c["name"] for c in collections.get("data", [])]
print(f"     Found: {names}")

# ── 3. Ensure test_kb_e2e exists (idempotent) ────────────────
print("\n=== 3. Create/ensure test KB ===")
if TEST_KB not in names:
    result = api("POST", "/knowledge/collections", {
        "name": TEST_KB,
        "displayName": "E2E测试知识库",
        "description": "端到端测试",
        "vectorSize": 1024,
        "distance": "Cosine",
    })
    check("Create KB succeeded", "data" in result, json.dumps(result, ensure_ascii=False)[:200])
else:
    print(f"     {TEST_KB} already exists, skipping create")
    check("KB exists", True)

# ── 4. Get single KB details ─────────────────────────────────
print("\n=== 4. Get KB details ===")
detail = api("GET", f"/knowledge/collections/{TEST_KB}")
check("Has data", "data" in detail)
kb = detail.get("data", {})
check("Name matches", kb.get("name") == TEST_KB)
check("Status is green", kb.get("status") == "green")
check("VectorSize is 1024", kb.get("vectorSize") == 1024)
check("DisplayName present", bool(kb.get("metadata", {}).get("displayName")))

# ── 5. Read existing chunks (test fixed format_chunk) ─────────
print("\n=== 5. Read chunks (tests format_chunk fix) ===")
chunks_resp = api("GET", f"/knowledge/collections/{TEST_KB}/chunks?limit=10")
check("Chunks endpoint works", "data" in chunks_resp)
chunks = chunks_resp.get("data", [])
print(f"     Chunks in {TEST_KB}: {len(chunks)}")
if chunks:
    c = chunks[0]
    check("Chunk has non-empty text", bool(c.get("text")), f"text={repr(c.get('text', '')[:50])}")
    check("Chunk has title (from filename)", c.get("title") is not None, f"title={c.get('title')}")

# ── 6. Upload a new document ──────────────────────────────────
print("\n=== 6. Upload document ===")
test_content = """# 知识库E2E测试文档

## 简介
这是一份用于端到端测试的 Markdown 文档。系统应该将其解析为向量块并存入 Qdrant。

## 内容
- 向量检索是 RAG 系统的核心
- Qdrant 提供高性能的向量搜索能力
- MinerU 可解析复杂格式的文档

## 结论
如果此文档被正确解析并入库，则 E2E 测试通过。
""".encode("utf-8")

boundary = "----E2ETestBoundary"
body_parts = []
body_parts.append(f"--{boundary}")
body_parts.append('Content-Disposition: form-data; name="file"; filename="e2e_test_doc.md"')
body_parts.append("Content-Type: text/markdown")
body_parts.append("")
body_parts.append(test_content.decode("utf-8"))
body_parts.append(f"--{boundary}")
body_parts.append('Content-Disposition: form-data; name="use_mineru"')
body_parts.append("")
body_parts.append("false")
body_parts.append(f"--{boundary}--")

body_str = "\r\n".join(body_parts)
body_bytes = body_str.encode("utf-8")

upload_url = f"{BASE}/knowledge/collections/{TEST_KB}/documents"
req = urllib.request.Request(upload_url, data=body_bytes, method="POST")
req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        upload_result = json.loads(resp.read())
    check("Upload returns taskId", "taskId" in upload_result)
    check("Upload status", upload_result.get("status") in ("completed", "processing", "pending"),
          f"status={upload_result.get('status')}")
    task_id = upload_result.get("taskId")
    print(f"     Task ID: {task_id}, Status: {upload_result.get('status')}")

    # Poll if still processing
    if upload_result.get("status") not in ("completed", "failed"):
        for i in range(15):
            time.sleep(2)
            task_resp = api("GET", f"/knowledge/documents/tasks/{task_id}")
            status = task_resp.get("status", "unknown")
            print(f"     Polling #{i+1}: {status}")
            if status in ("completed", "failed"):
                break
        check("Task completed", status == "completed", f"final status: {status}")
    elif upload_result.get("status") == "completed":
        check("Upload completed immediately", True)

except urllib.error.HTTPError as e:
    check("Upload succeeded", False, f"HTTP {e.code}: {e.read().decode()[:200]}")
    upload_result = {}

# ── 7. Verify chunks after upload ─────────────────────────────
print("\n=== 7. Verify chunks after upload ===")
# Give some time for async processing
time.sleep(3)
chunks_resp2 = api("GET", f"/knowledge/collections/{TEST_KB}/chunks?limit=20")
chunks2 = chunks_resp2.get("data", [])
print(f"     Total chunks now: {len(chunks2)}")
check("At least one chunk exists", len(chunks2) >= 1)

# Check that at least one chunk has non-empty text
non_empty = [c for c in chunks2 if c.get("text")]
check("At least one chunk has text content", len(non_empty) >= 1,
      f"non-empty: {len(non_empty)}/{len(chunks2)}")

if non_empty:
    sample = non_empty[0]
    preview = sample["text"][:100].replace("\n", " ")
    print(f"     Sample text: \"{preview}...\"")
    print(f"     Sample title: {sample.get('title')}")
    print(f"     Sample source: {sample.get('source')}")

# ── 8. Stats updated ─────────────────────────────────────────
print("\n=== 8. Updated stats ===")
stats2 = api("GET", "/knowledge/stats")
total_chunks = stats2.get("data", {}).get("totalChunks", 0)
total_collections = stats2.get("data", {}).get("totalCollections", 0)
print(f"     Collections: {total_collections}, Chunks: {total_chunks}")
check("Stats reflect new data", total_chunks >= 1)

# ── 9. Frontend page accessible ──────────────────────────────
print("\n=== 9. Frontend page check ===")
try:
    req = urllib.request.Request("http://localhost:3000/knowledge")
    with urllib.request.urlopen(req, timeout=10) as resp:
        status_code = resp.status
        html = resp.read().decode()
    check("Knowledge page returns 200", status_code == 200)
    check("Page contains expected content", "知识库" in html or "__next" in html or "knowledge" in html.lower())
except Exception as e:
    check("Knowledge page accessible", False, str(e))

# ── 10. Cleanup: delete test KB ───────────────────────────────
print("\n=== 10. Cleanup ===")
del_result = api("DELETE", f"/knowledge/collections/{TEST_KB}")
# Verify deletion
verify = api("GET", "/knowledge/collections")
remaining = [c["name"] for c in verify.get("data", [])]
check("Test KB deleted", TEST_KB not in remaining, f"remaining: {remaining}")

# ── Summary ───────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"  PASSED: {PASSED}   FAILED: {FAILED}")
print(f"{'='*50}")
sys.exit(0 if FAILED == 0 else 1)
