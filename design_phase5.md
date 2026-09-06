# Phase 5: On-Chain Re-Verification

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

## 1. What Phase 5 Adds

Phase 3 computed a `record_hash` binding 5 content-bearing fields
(subject, image_file, matched_url, content_hash, platform) and Phase 4
uploaded it to Sepolia in a self-transaction's calldata. Phase 5 proves,
**at any later time**, that:

1. The on-chain record still matches the local Phase 4 record — the
   transaction's calldata decodes (UTF-8) to exactly the uploaded
   `record_hash`.
2. The matched post's content is **unchanged** — the page is re-fetched
   and re-hashed with the same method Phase 2 used, and the recomputed
   `record_hash` still matches the on-chain one.

If a post is edited, replaced, or taken over, the re-fetched content
hash differs, the recomputed `record_hash` differs from the on-chain
value, and the verifier reports `tampered` — this is the tamper
detection the pipeline promises.

---

## 2. Input Contract

```
python -m chain.verify --subject <name>
```

Reads (in order):

| Input | Path | Required |
|-------|------|----------|
| Phase 4 upload record | `chain/uploads/<subject>.json` | Yes — has `tx_hash`, `record_hash` |
| Phase 3 fingerprint | `chain/fingerprints/<subject>.json` | Yes — has the 5 fields + original `content_hash` |
| RPC URL | `BLOCKCHAIN_RPC_URL` env var (from `.env`) | Yes — read-only; **no wallet key needed** |

Consent is **not** re-checked here: no new images or external identity
resolution happen in this stage — it only re-verifies records that were
already produced under consent gates.

---

## 3. Mechanics

### 3.1 Fetch and decode the on-chain record

```python
tx = w3.eth.get_transaction(tx_hash)          # read-only RPC call
raw = tx["input"]                              # 0x-prefixed hex calldata
record = bytes.fromhex(raw[2:]).decode("utf-8")  # the uploaded record_hash
```

- If calldata is empty, not hex, or not valid UTF-8 → error reported,
  status `record_mismatch` (the chain record is not usable).
- `record == upload["record_hash"]` → on-chain record is intact.

### 3.2 Re-fetch and re-hash the post

Reuses `web_search.searcher.fetch_content_hash(url)` — the exact same
function Phase 2 used — so hashing is byte-for-byte consistent:
`sha256:<hexdigest of the raw fetched page bytes>`.

### 3.3 Recompute and compare

Reuses `chain.fingerprint.compute_record_hash()` over the same canonical
dict (sorted keys, compact separators, `ensure_ascii=True`) with the
**current** `content_hash` substituted in. If the content is unchanged,
the recomputed hash equals the on-chain record_hash.

---

## 4. Verdict Logic

| Condition | Status | Meaning |
|-----------|--------|---------|
| Transaction could not be fetched / RPC error | `unverifiable` | The on-chain record could not be read — local record intact, chain state unchecked |
| Calldata does not decode to the uploaded `record_hash` | `record_mismatch` | Chain and local records disagree — serious integrity failure |
| Original `content_hash` was null (page inaccessible at Phase 2 time) | `unverifiable` | No content proof was ever recorded; chain record itself is intact |
| Current re-fetch fails / URL dead | `unverifiable` | Post no longer accessible; chain record itself is intact |
| Current hash == original hash **and** recomputed `record_hash` == on-chain | `verified` | Post unchanged; record intact |
| Current hash != original hash | `tampered` | Post content changed since upload — detectable tampering |
| Current hash == original but recomputed `record_hash` != on-chain | `record_mismatch` | Fingerprint doesn't correspond to the chain record |

---

## 5. Output Contract

### File location

```
chain/verifications/<subject>.json
```

### Schema

```json
{
  "subject": "alice",
  "verified_at": "2026-09-07T10:00:00.123456+00:00",
  "tx_hash": "0xabc123...",
  "uploaded_record_hash": "sha256:a1b2c3d4e5f6...",
  "on_chain_record_hash": "sha256:a1b2c3d4e5f6...",
  "calldata_matches_upload": true,
  "matched_url": "https://www.instagram.com/p/ABC123/",
  "original_content_hash": "sha256:e3b0c44298fc1c149...",
  "current_content_hash": "sha256:e3b0c44298fc1c149...",
  "recomputed_record_hash": "sha256:a1b2c3d4e5f6...",
  "status": "verified",
  "detail": "Post content unchanged and recomputed record_hash matches the on-chain record."
}
```

---

## 6. Failure Handling

| Failure | Behavior |
|---------|----------|
| **Upload record missing** | `FileNotFoundError` with path + "run Phase 4 first", `sys.exit(1)` |
| **Fingerprint missing** | `FileNotFoundError` with path + "run Phase 3 first", `sys.exit(1)` |
| **BLOCKCHAIN_RPC_URL missing** | `RuntimeError`, `sys.exit(1)` |
| **RPC connection failure** | `ConnectionError`, `sys.exit(1)` |
| **tx not found / RPC error on fetch** | Logged; `on_chain_fetch_error` set, status `unverifiable` (the chain state could not be checked — NOT a mismatch), result still saved |
| **Calldata not decodable** | `decode_calldata` returns error; status `record_mismatch`, result saved |
| **Post re-fetch fails** | `current_content_hash` null → status `unverifiable`, result saved |
| **Original content_hash null** | status `unverifiable` with explanation, result saved |

The verifier **never crashes on a bad verdict** — every outcome is
recorded to disk so the reviewer has evidence either way.

---

## 7. Verifiability

- **Real chain read:** the tx is fetched from Sepolia via RPC and the
  decoded calldata is printed — verifiable against Etherscan's Input Data
  tab for the same tx hash.
- **Real re-fetch:** the post URL is fetched over HTTP and re-hashed live;
  both old and new hashes are printed.
- **Real recomputation:** the deterministic `record_hash` is recomputed
  from the current content and compared, not looked up.
- **Status is evidence-backed:** each verdict carries a `detail` string
  explaining exactly which comparison produced it.

---

## 8. Testability

```bash
python -m chain.verify --subject alice
```

What the reviewer sees:

```
2026-09-07 10:00:00 [INFO] Subject: alice
2026-09-07 10:00:00 [INFO] Uploaded record_hash: sha256:a1b2c3d4e5f6...
2026-09-07 10:00:00 [INFO] tx_hash: 0xabc123...
2026-09-07 10:00:01 [INFO] Connected to https://ethereum-sepolia-rpc.publicnode.com (chainId=11155111)
2026-09-07 10:00:01 [INFO] On-chain calldata (UTF-8): sha256:a1b2c3d4e5f6...
2026-09-07 10:00:01 [INFO] Matched URL: https://www.instagram.com/p/ABC123/
2026-09-07 10:00:01 [INFO] Original content_hash: sha256:e3b0c44298fc1c149...
2026-09-07 10:00:02 [INFO] Current content_hash: sha256:e3b0c44298fc1c149...
2026-09-07 10:00:02 [INFO] Recomputed record_hash: sha256:a1b2c3d4e5f6...
2026-09-07 10:00:02 [INFO] VERDICT: VERIFIED
2026-09-07 10:00:02 [INFO] Verification saved to chain/verifications/alice.json

=== Verification for 'alice' ===
status: verified
tx_hash: 0xabc123...
uploaded record_hash: sha256:a1b2c3d4e5f6...
on-chain record_hash: sha256:a1b2c3d4e5f6...
matched_url: https://www.instagram.com/p/ABC123/
detail: Post content unchanged and recomputed record_hash matches the on-chain record.
Saved to: chain/verifications/alice.json
```

---

## 9. Definition of Done

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | Verifies a real on-chain tx | With a funded subject: decoded calldata equals uploaded `record_hash` |
| 2 | Detects unchanged content | Post unmodified → status `verified` |
| 3 | Detects changed content | Edit the matched post, re-run → status `tampered` |
| 4 | Handles dead URL gracefully | Unreachable post → status `unverifiable`, exit 0, result saved |
| 5 | Handles null original content_hash | Fingerprint with `content_hash: null` → status `unverifiable` with explanation |
| 6 | Reuses Phase 2/3 hashing | `verify.py` imports `fetch_content_hash` + `compute_record_hash` — no duplicated hashing code |
| 7 | No wallet key required | Verify runs with only `BLOCKCHAIN_RPC_URL` set |
| 8 | Output saved at expected path | `chain/verifications/<subject>.json` is valid JSON |
| 9 | Output gitignored | `chain/verifications/*.json` in `.gitignore` |
| 10 | Constraints block in design document | Present at top of `design_phase5.md` |
| 11 | No paid dependencies added | Uses only web3 (read), requests, stdlib — all already in requirements |