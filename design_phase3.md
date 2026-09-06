# Phase 3: Data Fingerprinting

## Constraints (non-negotiable)
- This pipeline operates ONLY on face images of consenting subjects — the
  project owner and/or friends/teammates who have explicitly agreed to be
  part of this demo. Multiple consenting subjects are fine.
- Do NOT build this as a general-purpose "identify any face" tool. Input
  should be drawn from a fixed, known set of consented images (e.g. a
  local folder/config list of approved subjects) — not an open upload
  flow that accepts arbitrary/unknown faces.
- Do not add functionality to search for or resolve the identity of
  anyone outside that consented set.
- No hardcoded/mocked results — every stage (search, hash, blockchain
  upload/verify) must perform the real operation and be independently
  re-runnable.
- HARD CONSTRAINT: every tool/service used in this project must be free
  — no paid tiers, no credit card requirements, no services that could
  incur real-world cost. Free testnets, free faucets, and free/open-
  source libraries only.

> **Note:** This constraints block must be copy-pasted at the top of every
> future phase's design.md.

---

## 1. What Phase 3 Adds

Phase 2 already computes a `content_hash` (SHA-256 of the fetched matched
page) and stores it in `web_search/results/<subject>.json` as part of
`best_match`. Phase 3 does **not** re-fetch or re-hash that content.

Instead, Phase 3 formalizes the pipeline's output into a **canonical,
deterministic fingerprint record** — a single structured document that
binds together:

- **Who:** the consented subject name
- **What image:** the source image filename
- **Where found:** the matched URL and platform
- **Content proof:** the content_hash from Phase 2
- **When:** the search timestamp from Phase 2

It then computes a single `record_hash` over the content-bearing fields,
producing one reproducible hash that can be uploaded to the blockchain
in Phase 4. This hash is what a later verifier (Phase 5) will recompute
to confirm the record hasn't been tampered with.

**In short:**
- Phase 2 content_hash = "I fetched this page; here is its hash."
- Phase 3 record_hash = "Here is a single fingerprint that binds
  subject + image + URL + content together — ready for on-chain upload."

**No-caching guarantee:** `chain/fingerprint.py` always reads
`web_search/results/<subject>.json` fresh from disk on every run — no
module-level cache, no `@lru_cache`, no stored state. If Phase 2 is
re-run and produces a different `best_match`, Phase 3's `record_hash`
correctly changes to reflect the new data. This is never stale.

---

## 2. Deterministic Hashing Specification

### What gets hashed

Only the 5 **content-bearing** fields are included in the hash input.
Timestamps, metadata, and presentation fields are excluded to ensure
reproducibility — running the fingerprinter twice on identical input
must produce the same `record_hash`.

| Field | Source | Example |
|-------|--------|---------|
| `subject` | Phase 2 output `subject` | `"kartik"` |
| `image_file` | Phase 2 output `image_file` | `"Kartike Dp.png"` |
| `matched_url` | `best_match.url` | `"https://in.linkedin.com/in/..."` |
| `content_hash` | `best_match.content_hash` | `"sha256:4708026285fc..."` or `null` |
| `platform` | `best_match.platform` | `"LinkedIn"` |

### Serialization method

The 5 fields are placed into a Python `dict` in **alphabetical key order**,
then serialized with:

```python
canonical_dict = {
    "content_hash": content_hash,   # string or null
    "image_file": image_file,
    "matched_url": matched_url,
    "platform": platform,
    "subject": subject,
}

canonical_bytes = json.dumps(
    canonical_dict,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
).encode("utf-8")
```

**Why these settings:**
- `sort_keys=True` — deterministic key ordering regardless of insertion order.
- `separators=(",", ":")` — no whitespace after commas/colons; compact form.
- `ensure_ascii=True` — non-ASCII characters escaped as `\uXXXX`; no
  dependence on system locale.
- `.encode("utf-8")` — bytes for hashing, not str.

### Hash computation

```python
record_hash = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
```

### Reproducibility guarantee

Given the same Phase 2 output JSON (same `subject`, `image_file`,
`best_match.url`, `best_match.content_hash`, `best_match.platform`),
the `record_hash` will be identical across any number of runs, on any
machine, regardless of when the fingerprint was generated.

The `null` content_hash case is deterministic too — `json.dumps` serializes
Python `None` as the literal string `null`, so `{"content_hash": null}`
always produces the same bytes.

---

## 3. Output Contract

### File location

```
chain/fingerprints/<subject>.json
```

### Schema

```json
{
  "subject": "kartik",
  "image_file": "Kartike Dp.png",
  "matched_url": "https://in.linkedin.com/in/prathmesh-bharadwaj-435089326",
  "platform": "LinkedIn",
  "match_type": "exact_match",
  "content_hash": null,
  "phase2_search_timestamp": "2026-09-06T13:51:30.552257+00:00",
  "fingerprint_generated_at": "2026-09-06T14:00:00.123456+00:00",
  "record_hash": "sha256:a1b2c3d4e5f6..."
}
```

### Field definitions

| Field | Type | Description |
|-------|------|-------------|
| `subject` | string | Consent subject name (from Phase 2) |
| `image_file` | string | Source image filename (from Phase 2) |
| `matched_url` | string | Resolved URL of the best match (from Phase 2 `best_match.url`) |
| `platform` | string | Social media platform name (from Phase 2) |
| `match_type` | string | `"exact_match"` or `"web_result"` (from Phase 2) |
| `content_hash` | string \| null | SHA-256 of the fetched page content (from Phase 2); `null` if fetch failed |
| `phase2_search_timestamp` | string | UTC ISO timestamp from the Phase 2 output (for traceability) |
| `fingerprint_generated_at` | string | UTC ISO timestamp of when this fingerprint was created |
| `record_hash` | string | SHA-256 fingerprint over the 5 content-bearing fields (see Section 2) |

### Fields consumed by Phase 4 (blockchain upload)

- `record_hash` — the single hash to upload on-chain as the fingerprint
- `subject` — metadata for the blockchain record
- `matched_url` — metadata for the blockchain record
- `platform` — metadata for the blockchain record
- `content_hash` — additional verification data

### What is NOT in the record hash

- `fingerprint_generated_at` — excluded because it changes per run; the
  hash must be reproducible.
- `phase2_search_timestamp` — excluded for the same reason.
- `match_type` — informational only; not part of the content fingerprint.

---

## 4. Reproducibility Test

The following test must pass — running the fingerprinter twice on the
same Phase 2 output must produce the identical `record_hash` both times.

### Test procedure

```bash
# Run 1
python -m chain.fingerprint --subject kartik
HASH1=$(python3 -c "
import json
with open('chain/fingerprints/kartik.json') as f:
    print(json.load(f)['record_hash'])
")

# Run 2 (immediately after)
python -m chain.fingerprint --subject kartik
HASH2=$(python3 -c "
import json
with open('chain/fingerprints/kartik.json') as f:
    print(json.load(f)['record_hash'])
")

# Verify
if [ "$HASH1" = "$HASH2" ]; then
    echo "PASS: record_hash is deterministic"
else
    echo "FAIL: $HASH1 != $HASH2"
fi
```

### Expected result

Both runs produce `record_hash` values that are byte-identical. The
`fingerprint_generated_at` timestamps will differ, but they are not
part of the hash.

---

## 5. Failure Handling

| Failure | Behavior |
|---------|----------|
| **Phase 2 output file missing** | `FileNotFoundError` raised with path, logged, `sys.exit(1)` |
| **Phase 2 output malformed / not valid JSON** | `json.JSONDecodeError` caught, logged with file path, `sys.exit(1)` |
| **`best_match` is null** | `ValueError` raised: "No best_match in Phase 2 output for '<subject>' — run Phase 2 first", `sys.exit(1)` |
| **`content_hash` is null** | Warning logged: "content_hash is null (URL was inaccessible) — record_hash computed without content proof". Fingerprint is still created using the other 4 fields. This is a valid state — the record proves the match was found even if the page couldn't be fetched. |
| **Required field missing from best_match** | `KeyError` caught, logged with the missing field name, `sys.exit(1)` |
| **Output directory doesn't exist** | Created automatically (`chain/fingerprints/` via `mkdir -p`) |
| **Same fingerprint already exists** | Overwritten (idempotent — re-running produces the same record_hash) |

---

## 6. Testability

### CLI entry point

```bash
python -m chain.fingerprint --subject <name>
```

### What the reviewer sees

```
2026-09-06 14:00:00 [INFO] Loading Phase 2 output: web_search/results/kartik.json
2026-09-06 14:00:00 [INFO] Subject: kartik
2026-09-06 14:00:00 [INFO] Matched URL: https://in.linkedin.com/in/prathmesh-bharadwaj-435089326
2026-09-06 14:00:00 [INFO] Platform: LinkedIn | match_type: exact_match
2026-09-06 14:00:00 [WARNING] content_hash is null (URL was inaccessible) — record_hash computed without content proof
2026-09-06 14:00:00 [INFO] Canonical input (5 fields): subject=kartik, image_file=Kartike Dp.png, matched_url=https://in.linkedin.com/..., content_hash=null, platform=LinkedIn
2026-09-06 14:00:00 [INFO] record_hash: sha256:a1b2c3d4e5f6...
2026-09-06 14:00:00 [INFO] Fingerprint saved to chain/fingerprints/kartik.json

=== Fingerprint for 'kartik' ===
record_hash: sha256:a1b2c3d4e5f6...
matched_url: https://in.linkedin.com/in/prathmesh-bharadwaj-435089326
platform: LinkedIn
content_hash: null (URL inaccessible)
Saved to: chain/fingerprints/kartik.json
```

---

## 7. Definition of Done

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | Fingerprint record is created at `chain/fingerprints/<subject>.json` | File exists and is valid JSON after running CLI |
| 2 | `record_hash` is deterministic | Running twice on same input produces byte-identical `record_hash` |
| 3 | `record_hash` contains all 5 content-bearing fields | Canonical JSON includes `subject`, `image_file`, `matched_url`, `content_hash`, `platform` |
| 4 | Null `content_hash` is handled gracefully | Fingerprint created with warning; `record_hash` computed from other 4 fields |
| 5 | Missing Phase 2 output produces clear error | `--subject nonexistent` -> `FileNotFoundError`, exit 1 |
| 6 | Null `best_match` produces clear error | Phase 2 output with `"best_match": null` -> `ValueError`, exit 1 |
| 7 | No hardcoded hash values in code | `grep` shows no literal SHA-256 strings in `chain/*.py` |
| 8 | Output is gitignored | `chain/fingerprints/*.json` in `.gitignore` |
| 9 | Constraints block in design document | Present at top of `design_phase3.md` |
| 10 | No paid dependencies added | `requirements.txt` has no new packages (uses only `hashlib`, `json`, `pathlib` — all stdlib) |
