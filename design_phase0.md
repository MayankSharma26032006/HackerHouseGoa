# Phase 0: Repository & Environment Setup

> **This file specifies Phase 0 only. The constraints block below must be
> copy-pasted verbatim to the top of every future phase's `design.md`.**

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

## 1. Folder Structure

```
face-verify-chain/
├── face_id/              # face detection + embedding extraction
│   ├── __init__.py
│   └── .gitkeep
├── web_search/           # reverse image / web search for matching posts
│   ├── __init__.py
│   └── .gitkeep
├── chain/                # hashing + blockchain upload + verification
│   ├── __init__.py
│   └── .gitkeep
├── demo/                 # end-to-end orchestration for screen recording
│   └── .gitkeep
├── data/                 # LOCAL ONLY — consented subjects' images
│   ├── subjects/         # sub-folder for actual images (gitignored)
│   └── CONSENT.md        # consent policy
├── .env.example          # template for required secrets
├── .gitignore            # covers .env, venv/, __pycache__, data/subjects/
├── requirements.txt      # pinned Python dependencies
├── README.md             # project overview, setup instructions, constraints
└── design_phase0.md      # this file
```

**Notes:**
- Each pipeline stage is its own top-level package so it can be developed
  and tested independently.
- `data/subjects/` holds approved face images on disk. It is **gitignored**
  — these files never enter version control.
- `.gitkeep` files keep empty directories tracked until real code lands.

---

## 2. Language / Runtime

**Python 3.11+** (3.11 minimum; 3.12 preferred).

**Justification:**
- All target libraries (InsightFace / onnxruntime, Pillow, requests,
  web3.py, eth-account) have first-class Python support.
- Fastest language to prototype a hackathon pipeline in.
- No existing project conventions contradict this — repo is greenfield.

---

## 3. Dependency Management

**Approach: `requirements.txt` + plain `venv`.**

**Justification:**
- `requirements.txt` is universally understood and sufficient for a
  hackathon of this scope.
- A virtual environment (`python -m venv venv`) keeps deps isolated
  without adding tooling complexity (poetry, pdm, etc.).
- Pin exact versions with `==` for reproducibility.

**Phase 0 `requirements.txt` contents:**
```
# Phase 0 — no runtime deps yet; this is a placeholder.
# Future phases will add: insightface, onnxruntime, Pillow,
# requests, web3, eth-account, etc.
python-dotenv>=1.0,<2.0
```

`python-dotenv` is the sole dependency at this stage — needed immediately
for secrets loading (§4).

---

## 4. Secrets Handling

### `.env.example` (committed — placeholder values only)

```bash
# ── Blockchain (TEST WALLET ONLY — never fund with real assets) ──
BLOCKCHAIN_RPC_URL=https://rpc.sepolia.org
WALLET_PRIVATE_KEY=0x_YOUR_TEST_WALLET_PRIVATE_KEY  # TEST WALLET ONLY — never fund with real assets
CONTRACT_ADDRESS=0x_YOUR_DEPLOYED_CONTRACT_ADDR

# ── Search / Vision API (Phase 2+) ────────────────────────
# TAVILY_API_KEY=tvly-...
# GOOGLE_API_KEY=...

# ── Face detection (Phase 1+) ─────────────────────────────
# No API key needed — runs locally via InsightFace/ONNX.
```

### `.gitignore`

```gitignore
# ── Secrets ────────────────────────────────────────────────
.env
*.pem
*.key

# ── Python ─────────────────────────────────────────────────
__pycache__/
*.pyc
venv/
.venv/

# ── Local data (consented images — never committed) ────────
data/subjects/

# ── OS / IDE ───────────────────────────────────────────────
.DS_Store
Thumbs.db
.idea/
.vscode/
*.swp

# ── Build artifacts ────────────────────────────────────────
dist/
build/
*.egg-info/
```

**Rules:**
- `.env` is **never committed**. Only `.env.example` (with placeholders)
  is tracked.
- Private keys and RPC URLs are loaded at runtime via `python-dotenv`.
- `WALLET_PRIVATE_KEY` must correspond to a **testnet-only** wallet.
  README will carry a warning about this.

---

## 5. Consent Policy — `data/CONSENT.md`

```markdown
# Consent Policy

Every image placed in `data/subjects/` must belong to a person who has
**explicitly consented** to participate in this project demo.

## What counts as consent

- A verbal "yes" recorded during the project session, **or**
- A signed/digital consent form (template can be added later).

## How we track it

1. Each subject gets a subdirectory: `data/subjects/<name>/`.
2. Inside that directory, place a `consent.txt` file containing:
   - Subject's name (or alias)
   - Date consent was given
   - Brief description of how consent was obtained
   - Optionally: a line for "scope" (e.g. "demo only, not production")

Example:
```
# data/subjects/alice/consent.txt
Name: Alice
Date: 2026-09-02
Scope: hackathon demo only
Method: Verbal consent during team meeting, confirmed by two witnesses.
```

## What NOT to do

- Do **not** add images of anyone who has not given consent.
- Do **not** add images scraped from the internet or social media.
- Do **not** use this folder for testing with random/fake faces — the
  pipeline should work with **real** consented subjects only.

## Enforcement

A future Phase 1 script (`face_id/validate_consent.py`) will scan
`data/subjects/` and warn/error if any image directory is missing
`consent.txt`.
```

---

## 6. README.md Outline

1. **Project name & one-liner** — "Face-consent verification pipeline"
2. **Constraints block** (same as top of this file)
3. **Quick start** — clone → create venv → install → copy `.env.example`
4. **Folder overview** — one line per top-level directory
5. **Roadmap** — brief bullets for Phase 1–N
6. **Consent rules** — link to `data/CONSENT.md`

---

## 7. Definition of Done — Phase 0

| #  | Criterion | How to verify |
|----|-----------|---------------|
| 1  | Repo clones cleanly | `git clone <url>` succeeds with no warnings |
| 2  | Folder structure matches §1 | `tree -L 1` shows the 7 top-level entries |
| 3  | Virtual environment works | `python -m venv venv && source venv/bin/activate` |
| 4  | Dependencies install cleanly | `pip install -r requirements.txt` exits 0 |
| 5  | `.env.example` present & documented | File exists with all placeholder keys from §4 |
| 6  | `.env` is gitignored | `git status` does not show `.env` |
| 7  | `data/subjects/` is gitignored | Images placed there are not tracked |
| 8  | `data/CONSENT.md` exists | File present, content matches §5 |
| 9  | Constraints block in `design_phase0.md` | Ctrl+F finds "Constraints (non-negotiable)" |
| 10 | No secrets committed | `git log --all -p` contains no real keys/URLs |
| 11 | README.md present & accurate | Renders correctly, links work |
