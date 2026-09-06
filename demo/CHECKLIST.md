# Demo Checklist & Screen-Recording Script

Use this to prepare and record the end-to-end demo. Every stage must show
**real** evidence on screen — the pipeline has no mocked results, so the
recording is only as good as the environment it runs in.

---

## 1. Pre-flight (complete before pressing record)

### Environment
- [ ] Python 3.11+ installed, virtual environment created and activated
- [ ] `pip install -r requirements.txt` completed without errors
- [ ] `data/subjects/<name>/consent.txt` exists with Name / Date / Scope / Method
      (format in `data/CONSENT.md`)
- [ ] At least one face photo in `data/subjects/<name>/` (real, consented)

### Secrets (`.env` — never committed)
- [ ] `APIFY_API_TOKEN` set — Apify Console → Settings → API & Integrations.
      Trial credits available on new accounts (no credit card needed).
- [ ] `BLOCKCHAIN_RPC_URL` set — e.g. `https://ethereum-sepolia-rpc.publicnode.com`
- [ ] `WALLET_PRIVATE_KEY` set — **testnet-only wallet, 0 real assets**

### Blockchain (full-pipeline demo only)
- [ ] Wallet funded with testnet ETH — check at
      https://sepolia.etherscan.io/address/<your-address>
      (free from https://sepoliafaucet.com)
- [ ] Decided the demo mode:
      **full** (funded wallet → all 5 stages) or
      **offline** (`--skip-upload --skip-verify` → stages 1–3)

### Network / APIs
- [ ] InsightFace model downloaded once (run `face_id` once; ~300 MB,
      needs internet on first run)
- [ ] Apify trial credits remaining > 0 (https://console.apify.com/billing)

---

## 2. Recording script — full pipeline

1. **Intro (30 s):** show the repo tree, read the one-liner from the README.
2. **Run:**
   ```bash
   python -m demo.run_pipeline --subject <name>
   ```
3. **Capture evidence per stage:**
   | Stage | What must appear on screen |
   |-------|---------------------------|
   | 1 | `bbox=…, conf=…` from InsightFace, embedding preview, saved JSON path |
   | 2 | Apify run ID, hit counts (`N exact-match, M web-result`), best-match URL + platform |
   | 3 | Canonical 5-field input, `record_hash`, saved fingerprint path |
   | 4 | `tx_hash`, `block: …`, Etherscan link |
   | 5 | Decoded on-chain calldata, `VERDICT: VERIFIED`, verification JSON path |
4. **Close the loop (30 s):** open the Etherscan link, click **Decode Input Data**,
   and show the UTF-8 text equals the `record_hash` printed in stage 3.

### Fallback — offline demo (wallet not funded)

```bash
python -m demo.run_pipeline --subject <name> --skip-upload --skip-verify
```

Stages 1–3 run with full real evidence. Say on camera:
*"Stages 4–5 are built and tested for error handling, but the demo wallet
has 0 testnet ETH, so the upload waits on faucet funding."*

### Pre-view without executing

```bash
python -m demo.run_pipeline --subject <name> --dry-run
```

---

## 3. Screenshots to collect

- [ ] Stage 1 output (bbox + confidence)
- [ ] Stage 2 output (run ID + best-match URL)
- [ ] Stage 3 output (record_hash)
- [ ] Stage 4 Etherscan page with decoded Input Data == record_hash
- [ ] Stage 5 verification verdict + `chain/verifications/<name>.json`
- [ ] `git status` showing all artifacts gitignored (nothing sensitive tracked)

---

## 4. What could go wrong (and the fix)

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PermissionError: consent.txt not found` | Subject not set up | Create `data/subjects/<name>/consent.txt` |
| `Apify API error (HTTP 402)` | Out of credits | Add Apify credits or switch to offline demo |
| `Insufficient testnet ETH` | Wallet unfunded | Fund via https://sepoliafaucet.com, or demo offline |
| `Intrinsic gas too low` (should never happen) | Gas regression | `chain/upload.py` computes gas from calldata (EIP-2028); re-run `python -c "from chain.upload import intrinsic_gas; print(intrinsic_gas(b'x'*71))"` → 22136 |
| Stage 2 returns no matches | Google Lens results vary | Re-run; Lens is best-effort, not deterministic |