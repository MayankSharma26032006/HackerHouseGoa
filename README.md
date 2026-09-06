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
# Then fill in .env with your testnet wallet key and RPC URL
```

## Folder Overview

| Directory      | Purpose                                                  |
|----------------|----------------------------------------------------------|
| `face_id/`     | Face detection + embedding extraction                    |
| `web_search/`  | Reverse image / web search for matching social posts     |
| `chain/`       | Content hashing + blockchain upload + verification       |
| `demo/`        | End-to-end orchestration script for the screen recording |
| `data/`        | Local storage for consented subjects' images only        |

> ⚠️ **`data/subjects/` is gitignored.** Consent policy lives in [`data/CONSENT.md`](data/CONSENT.md).

## Roadmap

- **Phase 0** — Repo & environment setup *(current)*
- **Phase 1** — Face detection + embedding with InsightFace/ONNX
- **Phase 2** — Reverse image / web search for matching posts
- **Phase 3** — Content hashing + blockchain upload + on-chain verification
- **Phase 4** — End-to-end orchestration + screen-recording demo

## Consent

Every image in `data/subjects/` must belong to a person who gave explicit consent. See **[`data/CONSENT.md`](data/CONSENT.md)** for details and the tracking format.

## ⚠️ Wallet Warning

The `WALLET_PRIVATE_KEY` in your `.env` **must** correspond to a testnet-only wallet (e.g. Sepolia). Never fund it with real assets.
