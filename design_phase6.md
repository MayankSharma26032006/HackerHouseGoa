# Phase 6: End-to-End Orchestration

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

## 1. What Phase 6 Adds

A single entry point that runs the whole pipeline for one consented
subject, in order, for the screen-recording demo:

```
python -m demo.run_pipeline --subject <name>
```

Each stage runs as its **own subprocess** (`python -m <module>`), not an
in-process function call. Why:

- Every stage keeps performing the **real operation** — nothing is
  bypassed or stubbed.
- Every stage stays **independently re-runnable** from its own CLI.
- A failure in any stage is isolated: the orchestrator aborts with that
  stage's exit code and a clear message, and the reviewer can re-run
  just the failed stage.
- The transcript shows the exact commands executed — a reviewer can
  reproduce each line by hand.

---

## 2. Stage Order

| # | Stage | Command run | Produces |
|---|-------|-------------|----------|
| 1 | Phase 1 — face detection + embedding | `python -m face_id.run --subject <name> [--images ...]` | `face_id/embeddings/<name>.json` |
| 2 | Phase 2 — reverse image search | `python -m web_search.run --subject <name>` | `web_search/results/<name>.json` |
| 3 | Phase 3 — fingerprinting | `python -m chain.fingerprint --subject <name>` | `chain/fingerprints/<name>.json` |
| 4 | Phase 4 — blockchain upload | `python -m chain.upload --subject <name>` | `chain/uploads/<name>.json` |
| 5 | Phase 5 — on-chain verification | `python -m chain.verify --subject <name>` | `chain/verifications/<name>.json` |

**Known current blocker:** Phase 4 requires testnet ETH in the wallet
(`WALLET_PRIVATE_KEY` in `.env`, funded via https://sepoliafaucet.com).
With a zero-balance wallet the pipeline aborts at Stage 4 with the
insufficient-balance error — this is the expected behavior until the
wallet is funded. Use `--skip-upload` (and `--skip-verify`) to run a
full offline demo up to the fingerprint.

---

## 3. CLI Flags

| Flag | Effect |
|------|--------|
| `--subject <name>` | Required. Subject with `consent.txt` in `data/subjects/<name>/` |
| `--images <path>...` | Optional. Passed through to Phase 1 (specific image paths) |
| `--skip-upload` | Stop after Phase 3; no blockchain interaction |
| `--skip-verify` | Run through upload but skip the Phase 5 verification |
| `--dry-run` | Print every command the pipeline would run, without executing anything |

---

## 4. Transcript Format

```text
============================================================
=== face-verify-chain pipeline for 'alice' — 5 stages ===
============================================================

>>> Stage 1/5: Phase 1 — face detection + embedding
============================================================
=== Phase 1 — face detection + embedding
============================================================
$ python -m face_id.run --subject alice
[face_id] Processing 1 image(s)...
[face_id]   Consent verified: data/subjects/alice/consent.txt
... (real stage output streams through) ...

✓ Phase 1 — face detection + embedding completed.

>>> Stage 2/5: Phase 2 — reverse image search
...
```

Stage output is **streamed** (inherited stdout/stderr) — the transcript
is the concatenation of each stage's real verifiable output, which is
exactly what the screen recording needs.

---

## 5. Failure Handling

| Failure | Behavior |
|---------|----------|
| **Any stage exits non-zero** | `✗ <stage> FAILED (exit code N). Pipeline aborted.`, orchestrator exits with N |
| **No consent.txt** | Stage 1 (or 2) raises `PermissionError` → abort before any processing |
| **Wallet has no testnet ETH** | Stage 4 raises insufficient-balance `ValueError` → abort with faucet link |
| **`--dry-run`** | Prints all commands, executes nothing, exits 0 |
| **Zero-balance demo** | `--skip-upload --skip-verify` → offline run completes through fingerprint |

---

## 6. Testability

```bash
# Preview without executing (works with zero setup):
python -m demo.run_pipeline --subject alice --dry-run

# Offline demo (no blockchain, no API credits beyond search):
python -m demo.run_pipeline --subject alice --skip-upload --skip-verify

# Full pipeline (requires funded testnet wallet + APIFY_API_TOKEN):
python -m demo.run_pipeline --subject alice
```

---

## 7. Definition of Done

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | One command runs all stages in order | `python -m demo.run_pipeline --subject <name>` executes 5 stages in order |
| 2 | Each stage is a real subprocess | Transcript shows `$ python -m ...` lines; modules independently runnable |
| 3 | Stage output streams through | Console shows each module's real logs, not summaries |
| 4 | Failure aborts with exit code | Break a stage (e.g. bad subject) → pipeline stops, nonzero exit |
| 5 | `--skip-upload` works offline | Runs stages 1–3 without any blockchain interaction |
| 6 | `--dry-run` executes nothing | Prints commands only, exit 0 |
| 7 | Uses no new dependencies | `demo/` uses only stdlib (`subprocess`, `argparse`, `shlex`) |
| 8 | Constraints block in design document | Present at top of `design_phase6.md` |