"""chain.upload - Blockchain upload of fingerprint record_hash to Sepolia testnet.

Embeds the record_hash in a 0-value self-transaction's data field.
No smart contract deployment needed — the hash is stored as UTF-8 bytes
in the transaction's input data, verifiable on Etherscan.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

logger = logging.getLogger(__name__)

EXPLORER_BASE = "https://sepolia.etherscan.io/tx/"
SEPOLIA_CHAIN_ID = 11155111

# Fixed gas limit for the self-transaction. The record_hash is ~71 bytes
# of calldata (~22136 intrinsic gas), but some Sepolia nodes enforce a
# higher minimum. 50000 is safe, cheap (well under the 0.05 ETH
# balance), and unused gas is refunded.
GAS_LIMIT = 50000


def load_fingerprint(subject):
    """Load the Phase 3 fingerprint record for a given subject.

    Returns the parsed JSON dict. Raises FileNotFoundError if missing.
    """
    fp_path = (
        Path(__file__).resolve().parent / "fingerprints" / f"{subject}.json"
    )
    if not fp_path.is_file():
        raise FileNotFoundError(
            f"Fingerprint not found: {fp_path}\n"
            f"Run 'python -m chain.fingerprint --subject {subject}' first."
        )

    with open(fp_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "record_hash" not in data:
        raise ValueError(
            f"Fingerprint file missing 'record_hash' field: {fp_path}"
        )

    return data


def get_web3():
    """Connect to the blockchain via RPC. Returns (w3, address)."""
    from web3 import Web3

    rpc_url = os.environ.get("BLOCKCHAIN_RPC_URL")
    if not rpc_url:
        raise RuntimeError(
            "BLOCKCHAIN_RPC_URL environment variable is not set. "
            "Set it in your .env file (e.g. https://ethereum-sepolia-rpc.publicnode.com)."
        )

    private_key = os.environ.get("WALLET_PRIVATE_KEY")
    if not private_key:
        raise RuntimeError(
            "WALLET_PRIVATE_KEY environment variable is not set. "
            "Set it in your .env file with your testnet wallet private key."
        )

    # Normalize private key
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ConnectionError(
            f"Cannot connect to blockchain RPC: {rpc_url}\n"
            "Check your BLOCKCHAIN_RPC_URL in .env."
        )

    address = w3.eth.account.from_key(private_key).address
    logger.info("Connected to %s (chainId=%s)", rpc_url, w3.eth.chain_id)
    logger.info("Sender address: %s", address)

    return w3, private_key, address


def check_balance(w3, address):
    """Check the wallet balance. Returns balance in ETH."""
    balance_wei = w3.eth.get_balance(address)
    balance_eth = w3.from_wei(balance_wei, "ether")
    logger.info("Balance: %s ETH", balance_eth)

    if balance_wei < w3.to_wei(0.001, "ether"):
        raise ValueError(
            f"Insufficient testnet ETH ({balance_eth} ETH).\n"
            "Get free testnet ETH from: https://sepoliafaucet.com"
        )

    return balance_eth


def build_and_send_tx(w3, private_key, address, record_hash):
    """Build, sign, and send the self-transaction with record_hash in data.

    Returns (tx_hash, receipt).
    """
    # Encode the record_hash as UTF-8 bytes for the data field
    data_bytes = record_hash.encode("utf-8")
    logger.info("Data field (UTF-8): %s", record_hash)
    logger.info("Data field (hex): %s", data_bytes.hex())

    # Build transaction with fixed gas limit.
    logger.info("Gas limit: %d (record_hash: %d bytes)", GAS_LIMIT, len(data_bytes))

    tx = {
        "from": address,
        "to": address,  # self-send
        "value": 0,
        "data": data_bytes,
        "nonce": w3.eth.get_transaction_count(address),
        "gas": GAS_LIMIT,
        "gasPrice": w3.eth.gas_price,
        "chainId": SEPOLIA_CHAIN_ID,
    }

    logger.info("Signing transaction ...")
    signed_tx = w3.eth.account.sign_transaction(tx, private_key)

    logger.info("Sending transaction ...")
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hash_hex = tx_hash.hex()
    if not tx_hash_hex.startswith("0x"):
        tx_hash_hex = "0x" + tx_hash_hex
    logger.info("Transaction sent: %s", tx_hash_hex)

    logger.info("Waiting for confirmation ...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt.status != 1:
        raise ValueError(
            f"Transaction reverted (status=0). tx_hash={tx_hash_hex}"
        )

    logger.info(
        "Transaction confirmed in block %d (status=%d)",
        receipt.blockNumber,
        receipt.status,
    )

    return tx_hash_hex, receipt


def save_upload_result(subject, record_hash, tx_hash, receipt, address):
    """Save the upload result to chain/uploads/<subject>.json."""
    out_dir = Path(__file__).resolve().parent / "uploads"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{subject}.json"

    result = {
        "subject": subject,
        "record_hash": record_hash,
        "tx_hash": tx_hash,
        "block_number": receipt.blockNumber,
        "chain_id": SEPOLIA_CHAIN_ID,
        "network": "sepolia",
        "explorer_url": EXPLORER_BASE + tx_hash,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "from_address": address,
        "data_hex": record_hash.encode("utf-8").hex(),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return out_path


def upload_subject(subject):
    """Full upload pipeline for a subject.

    1. Load fingerprint
    2. Connect to blockchain
    3. Check balance
    4. Build, sign, send transaction
    5. Save result
    Returns the result dict.
    """
    # 1. Load fingerprint
    fingerprint = load_fingerprint(subject)
    record_hash = fingerprint["record_hash"]
    logger.info("Subject: %s", subject)
    logger.info("record_hash: %s", record_hash)

    # 2. Connect to blockchain
    w3, private_key, address = get_web3()

    # 3. Check balance
    check_balance(w3, address)

    # 4. Build, sign, send
    logger.info("Building self-transaction with record_hash in data field ...")
    tx_hash, receipt = build_and_send_tx(w3, private_key, address, record_hash)

    # Log verification info
    explorer_url = EXPLORER_BASE + tx_hash
    logger.info("Etherscan: %s", explorer_url)

    # 5. Save result
    out_path = save_upload_result(subject, record_hash, tx_hash, receipt, address)
    logger.info("Upload saved to %s", out_path)

    return {
        "subject": subject,
        "record_hash": record_hash,
        "tx_hash": tx_hash,
        "block_number": receipt.blockNumber,
        "explorer_url": explorer_url,
    }


def main():
    """CLI entry point for chain.upload module."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Upload fingerprint record_hash to Sepolia testnet"
    )
    parser.add_argument(
        "--subject",
        required=True,
        help="Subject name (must have chain/fingerprints/<subject>.json from Phase 3)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    try:
        result = upload_subject(args.subject)
        print(f"\n=== Blockchain Upload for '{result['subject']}' ===")
        print(f"tx_hash: {result['tx_hash']}")
        print(f"block: {result['block_number']}")
        print(f"network: Sepolia")
        print(f"explorer: {result['explorer_url']}")
        print(f"record_hash: {result['record_hash']}")
        print(f"Saved to: chain/uploads/{result['subject']}.json")
    except FileNotFoundError as e:
        logger.error("%s", e)
        sys.exit(1)
    except RuntimeError as e:
        logger.error("%s", e)
        sys.exit(1)
    except ValueError as e:
        logger.error("%s", e)
        sys.exit(1)
    except ConnectionError as e:
        logger.error("Blockchain connection failed: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
