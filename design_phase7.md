# Phase 7: README, Honest Limitations & Submission Packaging

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

## 1. What Phase 7 Adds

No new pipeline functionality. Phase 7 packages the project for
submission and the screen-recording demo:

1. **README.md** — what the project does, how to run every stage, and
   its **honest limitations** (nothing hidden from a reviewer).
2. **`demo/CHECKLIST.md`** — pre-flight checks and the recording script,
   including fallbacks for the unfunded-wallet blocker.
3. **Submission hygiene** — remove accidental artifacts from the repo
   (e.g. the committed `=6.0.0` pip-log file), fix `.env.example`
   formatting, and confirm nothing sensitive is tracked.

---

## 2. README Requirements

| # | Requirement | Where |
|---|-------------|-------|
| 1 | One-liner: what the pipeline does | Top of README |
| 2 | The consent constraints block (verbatim) | Top of README |
| 3 | Pipeline overview diagram + per-stage artifact table | "What this does" |
| 4 | Setup instructions (venv, deps, `.env`, consented subject) | "Quick Start" |
| 5 | How to run every stage + the orchestrator + flags | "Running it" |
| 6 | What real evidence each stage prints | "Running it" |
| 7 | Honest limitations (wallet blocker, Apify cost, scraper fragility, null content_hash, model download, non-general tool) | "Honest limitations" |
| 8 | Roadmap table with per-phase status | "Roadmap" |
| 9 | Consent policy + testnet wallet warning | Bottom of README |
| 10 | No secrets, no mocked results, no real keys/URLs anywhere in the repo | Global |

---

## 3. Demo Checklist (`demo/CHECKLIST.md`)

Must cover:

- **Pre-flight:** Python/venv, dependencies, `.env` secrets,
  `consent.txt` + photos, wallet funding check, InsightFace model cache,
  Apify credits, and the full-vs-offline demo decision.
- **Recording script:** the exact command to run, the per-stage evidence
  to capture on screen, and the "close the loop" step (Etherscan →
  decode Input Data → compare with `record_hash`).
- **Offline fallback:** `--skip-upload --skip-verify` script with a
  suggested on-camera explanation of the blocker.
- **Screenshot list** and a **what-could-go-wrong** table with fixes.

---

## 4. Submission Hygiene

- `=6.0.0` (raw `pip install` output committed by accident) → deleted.
- `.env.example` stray `[TEMPLATE]` header lines → removed.
- `git status` must show no `.env`, no `data/subjects/`, and no generated
  artifacts (embeddings/results/fingerprints/uploads/verifications).

---

## 5. Definition of Done

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | README explains what it does | One-liner + pipeline overview present |
| 2 | README shows how to run every stage | All 5 stage commands + orchestrator documented |
| 3 | README lists honest limitations | Section exists covering the wallet blocker, Apify cost, scraper fragility, null content_hash |
| 4 | README status table is accurate | Phases 0–3 ✅, 4 ⏸ (blocked), 5–6 🚧, 7 ✅ |
| 5 | Constraints block preserved | Ctrl+F finds "Constraints (non-negotiable)" in README + all design docs |
| 6 | Demo checklist exists | `demo/CHECKLIST.md` has pre-flight, recording script, fallback, troubleshooting |
| 7 | No accidental files in repo | `=6.0.0` deleted; `.env.example` clean |
| 8 | No secrets committed | `git log --all -p` contains no real keys/URLs; `git status` shows no `.env` |
| 9 | Links work | README links to `data/CONSENT.md` and `demo/CHECKLIST.md` resolve |