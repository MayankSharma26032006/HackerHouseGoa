# face-verify-chain

Face-consent verification pipeline — scan a face, find a matching post on the web, then upload and re-verify that data on-chain.

---

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

---

## What this does

The pipeline turns a photo of a **consenting subject** into an
**on-chain proof that a specific social post about them existed at a
specific time** — and can later prove whether that post has been
tampered with:

```
consented face photo
  │
  ▼ [1] Face detection + 512-d embedding      (InsightFace/ONNX, local, consent-gated)
  ▼ [2] Reverse image search for the post     (Google Lens via Apify actor)
  ▼ [3] Deterministic fingerprint record_hash (SHA-256 over subject + image + URL + content + platform)
  ▼ [4] Upload record_hash to Sepolia         (0-value self-transaction, hash in calldata)
  ▼ [5] Re-verify later                       (re-fetch post → re-hash → compare on-chain)
  │
  └── all chained by [6] demo/run_pipeline.py
```

Each stage writes a JSON artifact that the next stage consumes, so every
stage stays independently runnable and reviewable:

| Stage | Command | Artifact |
|-------|---------|----------|
| 1 — Face embedding | `python -m face_id.run --subject <name>` | `face_id/embeddings/<name>.json` |
| 2 — Reverse image search | `python -m web_search.run --subject <name>` | `web_search/results/<name>.json` |
| 3 — Fingerprint | `python -m chain.fingerprint --subject <name>` | `chain/fingerprints/<name>.json` |
| 4 — On-chain upload | `python -m chain.upload --subject <name>` | `chain/uploads/<name>.json` |
| 5 — On-chain verification | `python -m chain.verify --subject <name>` | `chain/verifications/<name>.json` |
| 6 — Everything, one command | `python -m demo.run_pipeline --subject <name>` | — |

All artifacts are **gitignored** — they are generated evidence, not
committed files.

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url> && cd face-verify-chain

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up secrets
cp .env.example .env
# Then fill in .env: APIFY_API_TOKEN, BLOCKCHAIN_RPC_URL,
# and WALLET_PRIVATE_KEY (testnet-only wallet)

# 5. Add a consented subject
mkdir -p data/subjects/<name>
# place a photo + consent.txt in data/subjects/<name>/ (see data/CONSENT.md)
```

## Running it

Every stage requires a **consented subject** first: `data/subjects/<name>/`
must contain at least one photo **and** a `consent.txt` file. Without it,
the pipeline refuses to run (`PermissionError`).

```bash
# Run everything for one subject (requires funded testnet wallet)
python -m demo.run_pipeline --subject <name>

# Offline demo — stop after fingerprinting, no blockchain involved
python -m demo.run_pipeline --subject <name> --skip-upload --skip-verify

# Preview the commands without executing anything
python -m demo.run_pipeline --subject <name> --dry-run
```

Or run any stage on its own — each one re-verifies consent before doing
real work:

```bash
python -m face_id.run --subject <name>            # detect + embed
python -m web_search.run --subject <name>         # find the social post
python -m chain.fingerprint --subject <name>      # build record_hash
python -m chain.upload --subject <name>           # upload to Sepolia
python -m chain.verify --subject <name>           # re-verify on-chain + post
```

### What honest evidence each stage prints

| Stage | Evidence on screen |
|-------|--------------------|
| 1 | Real bounding box + confidence from InsightFace, embedding preview |
| 2 | Apify run ID, raw hit counts, best-match URL (live, from the API) |
| 3 | The canonical 5-field input and the deterministic `record_hash` |
| 4 | Real `tx_hash` + Etherscan link; calldata decodes to the `record_hash` |
| 5 | On-chain calldata, current vs. original content hash, verdict (`verified` / `tampered` / …) |

---

## Roadmap (8-phase build plan)

| Phase | Purpose | Status |
|-------|---------|--------|
| 0 | Repo setup, `.env`/`.gitignore`, consent policy (`CONSENT.md`) | ✅ Done |
| 1 | Face detection + embedding (InsightFace/ONNX), gated on `consent.txt` | ✅ Done |
| 2 | Reverse image search for matching social posts; hash the matched page | ✅ Done (tested with real results) |
| 3 | Deterministic, reproducible fingerprint (`record_hash`) | ✅ Done (reproducibility-tested) |
| 4 | Upload fingerprint to Sepolia testnet via self-transaction | ⏸ Code + error handling done; **blocked — testnet wallet has 0 ETH** |
| 5 | Re-fetch the post, re-hash it, compare to the on-chain record | 🚧 Built, unproven end-to-end (waits on Phase 4) |
| 6 | One script running all stages end-to-end for the demo recording | 🚧 Built, unproven end-to-end (waits on Phase 4) |
| 7 | README + honest limitations + submission packaging | ✅ Done |

Design docs for every phase: `design_phase0.md` … `design_phase7.md`.
Demo pre-flight + recording script: [`demo/CHECKLIST.md`](demo/CHECKLIST.md).

---

## Honest limitations

Read this before trusting the pipeline — nothing here is hidden:

1. **Phase 4 needs a funded testnet wallet.** The upload code is written
   and its error handling is tested, but no real transaction has ever
   succeeded because the wallet has 0 testnet ETH. Free ETH is available
   from https://sepoliafaucet.com. Until then, Phases 5–6 are built but
   unproven end-to-end.
2. **Phase 2 is not free.** Phases 3–6 declare a hard constraint that
   every tool must be free, but the Apify Google Lens actor is
   **pay-per-event** (new accounts get trial credits, no card required).
   It is the single paid step in the pipeline and may eventually run out
   of credits. A genuinely free reverse-image-search alternative would
   resolve this contradiction.
3. **Phase 2 relies on an unofficial, community-maintained scraper.**
   The Apify `borderline/google-lens` actor is not an official Google
   product: results vary by region/time, anti-scraping can break it, and
   the actor may change or disappear without notice. A "no match" result
   does not prove a post doesn't exist.
4. **`content_hash` can be null.** Social platforms frequently block
   automated fetches, so the matched page may not be hashable at search
   time. In that case the fingerprint is still uploaded, but content
   tamper-detection (Phase 5) cannot be performed — the verifier reports
   `unverifiable` instead of `verified`.
5. **First run downloads models.** InsightFace downloads the `buffalo_l`
   model (~300 MB) on first use; afterwards it runs fully offline.
6. **This is not a general face-identification tool.** It only ever
   processes the fixed set of consented subjects in `data/subjects/`, by
   design and by constraint.

---

## Folder Overview

| Directory      | Purpose                                                  |
|----------------|----------------------------------------------------------|
| `face_id/`     | Face detection + embedding extraction                    |
| `web_search/`  | Reverse image / web search for matching social posts     |
| `chain/`       | Deterministic fingerprinting + Sepolia upload + on-chain verification |
| `demo/`        | End-to-end orchestration script for the screen recording |
| `data/`        | Local storage for consented subjects' images only        |

> ⚠️ **`data/subjects/` is gitignored.** Consent policy lives in [`data/CONSENT.md`](data/CONSENT.md).

---

## Consent

Every image in `data/subjects/` must belong to a person who gave explicit consent. See **[`data/CONSENT.md`](data/CONSENT.md)** for details and the tracking format.

## ⚠️ Wallet Warning

The `WALLET_PRIVATE_KEY` in your `.env` **must** correspond to a testnet-only wallet (e.g. Sepolia). Never fund it with real assets.