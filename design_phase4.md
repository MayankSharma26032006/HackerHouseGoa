# Phase 4: Blockchain Upload

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

## 1. Blockchain Choice: Ethereum Sepolia Testnet

**Sepolia is the right call.** Reasons:
- Most widely supported testnet — web3.py, Etherscan, all tooling
- Free faucets: Alchemy (https://sepoliafaucet.com), Infura, Sepolia PoW faucet
- Free RPC: `https://rpc.sepolia.org` (already in `.env`)
- Etherscan verification: `https://sepolia.etherscan.io/tx/<hash>`
- Polygon Amoy is equally free but has less tooling/community support

---

## 2. Library: web3.py + eth-account

```python
from web3 import Web3
from eth_account import Account
```

Connect via `BLOCKCHAIN_RPC_URL` (from `.env`). Sign with `WALLET_PRIVATE_KEY`.

---

## 3. Upload Mechanism: Self-Transaction with Data Field

**Chosen: 0-value self-transaction with record_hash embedded in the data field.**

### Why this over deploying a contract

- No contract deployment step (saves ~100-200k gas + complexity)
- No contract address to manage
- Same wallet sends to itself: `from_addr -> from_addr`
- Data field: UTF-8 bytes of the record_hash string (~71 bytes)
- Gas cost: only 21000 (base tx cost) — cheapest possible on-chain operation
- Verification: on Etherscan, decode Input Data -> UTF-8 -> compare with record_hash

### Why not a contract

- Contract deployment adds a separate step (deploy, wait, then call)
- More code, more failure modes
- For a hackathon, the self-transaction is simpler and equally verifiable
- A contract would give cleaner event logs, but isn't worth the added complexity

---

## 4. Transaction Mechanics

1. Load fingerprint from `chain/fingerprints/<subject>.json`
2. Connect to blockchain via `Web3(Web3.HTTPProvider(RPC_URL))`
3. Derive sender address from private key
4. Build transaction:
   - `from`: sender address
   - `to`: sender address (self-send)
   - `value`: 0
   - `data`: record_hash encoded as UTF-8 bytes
   - `nonce`: `w3.eth.get_transaction_count(address)`
   - `gas`: 21000 (fixed — self-transfer with data)
   - `gasPrice`: `w3.eth.gas_price`
   - `chainId`: 11155111 (Sepolia)
5. Sign with private key
6. Send via `w3.eth.send_raw_transaction()`
7. Wait for receipt: `w3.eth.wait_for_transaction_receipt(tx_hash)`
8. Extract `blockNumber` and `status` from receipt

---

## 5. Output Contract

### File location

```
chain/uploads/<subject>.json
```

### Schema

```json
{
  "subject": "kritika",
  "record_hash": "sha256:7b062950f52423dfce26875038ffeed490e4941c6f09d981821cb1671c6da0f7",
  "tx_hash": "0xabc123...",
  "block_number": 12345678,
  "chain_id": 11155111,
  "network": "sepolia",
  "explorer_url": "https://sepolia.etherscan.io/tx/0xabc123...",
  "uploaded_at": "2026-09-06T16:00:00.123456+00:00",
  "from_address": "0x...",
  "data_hex": "7368613235363a..."
}
```

---

## 6. CLI Entry Point

```bash
python -m chain.upload --subject <name>
```

---

## 7. Failure Handling

| Failure | Behavior |
|---------|----------|
| **Fingerprint file missing** | `FileNotFoundError` raised, logged, `sys.exit(1)` |
| **WALLET_PRIVATE_KEY missing** | `RuntimeError` raised, logged, `sys.exit(1)` |
| **BLOCKCHAIN_RPC_URL missing** | `RuntimeError` raised, logged, `sys.exit(1)` |
| **RPC connection failure** | `ConnectionError` caught, logged, `sys.exit(1)` |
| **Insufficient balance** | `ValueError` raised: "Insufficient testnet ETH — get testnet ETH from https://sepoliafaucet.com", `sys.exit(1)` |
| **Transaction rejected** | `ValueError` from `send_raw_transaction`, logged, `sys.exit(1)` |
| **Transaction reverted** | Receipt `status == 0`, `ValueError`, `sys.exit(1)` |
| **Already uploaded** | If `chain/uploads/<subject>.json` exists, log warning and overwrite (idempotent) |

---

## 8. Verifiability

Console prints:
- The real `tx_hash`
- A clickable Etherscan link: `https://sepolia.etherscan.io/tx/<tx_hash>`
- The data field content (hex + decoded UTF-8) for human verification

### What the reviewer sees

```
2026-09-06 16:00:00 [INFO] Loading fingerprint: chain/fingerprints/kritika.json
2026-09-06 16:00:00 [INFO] Subject: kritika
2026-09-06 16:00:00 [INFO] record_hash: sha256:7b062950f52423dfce26875038ffeed490e4941c6f09d981821cb1671c6da0f7
2026-09-06 16:00:00 [INFO] Connecting to Sepolia via https://rpc.sepolia.org ...
2026-09-06 16:00:00 [INFO] Sender address: 0x...
2026-09-06 16:00:00 [INFO] Balance: 0.05 ETH (sufficient)
2026-09-06 16:00:00 [INFO] Building self-transaction with record_hash in data field ...
2026-09-06 16:00:00 [INFO] Signing transaction ...
2026-09-06 16:00:00 [INFO] Sending transaction ...
2026-09-06 16:00:05 [INFO] Transaction sent: 0xabc123...
2026-09-06 16:00:10 [INFO] Transaction confirmed in block 12345678 (status=1)
2026-09-06 16:00:10 [INFO] Etherscan: https://sepolia.etherscan.io/tx/0xabc123...
2026-09-06 16:00:10 [INFO] Data field (UTF-8): sha256:7b062950f52423dfce26875038ffeed490e4941c6f09d981821cb1671c6da0f7
2026-09-06 16:00:10 [INFO] Upload saved to chain/uploads/kritika.json

=== Blockchain Upload for 'kritika' ===
tx_hash: 0xabc123...
block: 12345678
network: Sepolia
explorer: https://sepolia.etherscan.io/tx/0xabc123...
record_hash: sha256:7b062950f52423dfce26875038ffeed490e4941c6f09d981821cb1671c6da0f7
Saved to: chain/uploads/kritika.json
```

---

## 9. Definition of Done

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | Real transaction confirmed on Sepolia (status=1) | Receipt status == 1, blockNumber > 0 |
| 2 | tx_hash viewable on Etherscan | Open sepolia.etherscan.io/tx/<hash> in browser |
| 3 | Data field contains the exact record_hash | Decode Input Data on Etherscan -> UTF-8 -> compare |
| 4 | `chain/uploads/<subject>.json` saved | File exists and is valid JSON |
| 5 | No hardcoded tx_hash values in code | `grep` shows no literal 0x... strings in `chain/*.py` |
| 6 | Missing fingerprint -> FileNotFoundError, exit 1 | `--subject nonexistent` test |
| 7 | Missing wallet key -> clear error, exit 1 | Unset WALLET_PRIVATE_KEY test |
| 8 | Insufficient balance -> clear error with faucet link | Low-balance wallet test |
| 9 | Constraints block in design document | Present at top of `design_phase4.md` |
| 10 | Output gitignored | `chain/uploads/*.json` in `.gitignore` |
