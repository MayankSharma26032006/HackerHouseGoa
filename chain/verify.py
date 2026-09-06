"""chain.verify - Phase 5: live re-verification against the blockchain.

Takes the Phase 4 upload record for a subject and proves the on-chain
fingerprint is still intact AND that the original matched post's content
has not changed:

1. Read the upload record (chain/uploads/<subject>.json) for the tx_hash
   and the record_hash that was uploaded.
2. Fetch the transaction from the chain and decode its calldata (UTF-8).
   It must equal the uploaded record_hash — otherwise the chain record
   and the local record disagree (record_mismatch).
3. Re-fetch the matched post from the web and re-hash its content
   (same method as Phase 2's content_hash).
4. Recompute the deterministic record_hash over the 5 content-bearing
   fields with the *new* content hash and compare with the on-chain one:
     - same content hash  -> recomputed record_hash matches -> verified
     - different content  -> recomputed record_hash differs  -> tampered
     - original or current content unavailable               -> unverifiable

Statuses:
  verified         - on-chain record intact AND post content unchanged
  tampered         - on-chain record intact, but post content changed
  record_mismatch  - calldata on-chain does not decode to the uploaded
                     record_hash (local/chain records disagree)
  unverifiable     - content proof missing or page now inaccessible
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Reuse the deterministic hashing from Phase 3 and the content fetch
# from Phase 2 so verification is byte-for-byte consistent with them.
from chain.fingerprint import compute_record_hash
from web_search.searcher import fetch_content_hash

# Load .env file if present (BLOCKCHAIN_RPC_URL)
load_dotenv()

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_upload_record(subject):
    """Load the Phase 4 upload record for a subject.

    Returns the parsed JSON dict. Raises FileNotFoundError if missing.
    """
    upload_path = PROJECT_ROOT / "chain" / "uploads" / f"{subject}.json"
    if not upload_path.is_file():
        raise FileNotFoundError(
            f"Phase 4 upload record not found: {upload_path}\n"
            f"Run 'python -m chain.upload --subject {subject}' first."
        )
    with open(upload_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_fingerprint(subject):
    """Load the Phase 3 fingerprint record for a subject.

    Raises FileNotFoundError if missing.
    """
    fp_path = PROJECT_ROOT / "chain" / "fingerprints" / f"{subject}.json"
    if not fp_path.is_file():
        raise FileNotFoundError(
            f"Phase 3 fingerprint not found: {fp_path}\n"
            f"Run 'python -m chain.fingerprint --subject {subject}' first."
        )
    with open(fp_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_rpc_web3():
    """Connect read-only to the blockchain. Requires only the RPC URL."""
    from web3 import Web3

    rpc_url = os.environ.get("BLOCKCHAIN_RPC_URL")
    if not rpc_url:
        raise RuntimeError(
            "BLOCKCHAIN_RPC_URL environment variable is not set. "
            "Set it in your .env file (e.g. https://ethereum-sepolia-rpc.publicnode.com)."
        )

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ConnectionError(
            f"Cannot connect to blockchain RPC: {rpc_url}\n"
            "Check your BLOCKCHAIN_RPC_URL in .env."
        )
    logger.info("Connected to %s (chainId=%s)", rpc_url, w3.eth.chain_id)
    return w3


def decode_calldata(tx):
    """Decode a transaction's calldata field as UTF-8.

    Returns (decoded_string_or_None, error_or_None).
    Handles the 0x-prefixed hex string returned by get_transaction.
    """
    raw = tx.get("input") or tx.get("data")
    if not raw:
        return None, "transaction has no calldata"
    # HexBytes / bytes: strip 0x prefix as bytes or str
    if isinstance(raw, (bytes, bytearray)):
        hex_str = raw.hex()
        hex_str = hex_str[2:] if hex_str.startswith("0x") else hex_str
    else:
        hex_str = raw[2:] if raw.startswith("0x") else raw
    if not hex_str:
        return None, "calldata is empty"
    try:
        return bytes.fromhex(hex_str).decode("utf-8"), None
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"calldata is not UTF-8 text: {exc}"


def fetch_on_chain_record(w3, tx_hash):
    """Fetch a transaction and decode its calldata to the record string.

    Returns (record_str_or_None, error_or_None).
    """
    try:
        tx = w3.eth.get_transaction(tx_hash)
    except Exception as exc:
        return None, f"could not fetch tx {tx_hash}: {exc}"
    return decode_calldata(tx)


def verify_subject(subject):
    """Run the full verification pipeline for a subject.

    Returns the verification result dict and saves it to
    chain/verifications/<subject>.json.
    """
    # 1. Load local records
    upload = load_upload_record(subject)
    fingerprint = load_fingerprint(subject)

    tx_hash = upload.get("tx_hash", "")
    uploaded_record_hash = upload.get("record_hash", "")
    logger.info("Subject: %s", subject)
    logger.info("Uploaded record_hash: %s", uploaded_record_hash)
    logger.info("tx_hash: %s", tx_hash)

    # 2. Fetch the on-chain record and decode the calldata
    w3 = get_rpc_web3()
    logger.info("Fetching transaction %s ...", tx_hash)
    on_chain_record, fetch_err = fetch_on_chain_record(w3, tx_hash)
    if fetch_err:
        logger.warning("On-chain fetch failed: %s", fetch_err)
    elif on_chain_record:
        logger.info("On-chain calldata (UTF-8): %s", on_chain_record)

    # 3. Re-fetch the matched post and re-hash its content
    matched_url = fingerprint.get("matched_url", "")
    original_content_hash = fingerprint.get("content_hash")
    logger.info("Matched URL: %s", matched_url)
    logger.info("Original content_hash: %s", original_content_hash or "null")

    logger.info("Re-fetching post content ...")
    current_content_hash = fetch_content_hash(matched_url)
    if current_content_hash:
        logger.info("Current content_hash: %s", current_content_hash[:60] + "...")
    else:
        logger.warning("Could not re-fetch post content (URL may be inaccessible)")

    # 4. Decide the verdict
    on_chain_matches_upload = (
        on_chain_record is not None and on_chain_record == uploaded_record_hash
    )

    if fetch_err:
        status = "unverifiable"
        detail = (
            "Could not read the on-chain record: " + str(fetch_err)
            + " (the local record is intact; the chain state could not be checked)"
        )
        recomputed_record_hash = None
    elif not on_chain_matches_upload:
        status = "record_mismatch"
        detail = (
            "On-chain calldata does not equal the uploaded record_hash. "
            "The chain record and the local Phase 4 record disagree."
        )
        recomputed_record_hash = None
    elif original_content_hash is None:
        status = "unverifiable"
        detail = (
            "The Phase 3 fingerprint was created without content proof "
            "(content_hash was null at upload time), so post-content "
            "integrity cannot be checked. The on-chain record itself is intact."
        )
        recomputed_record_hash = None
    elif current_content_hash is None:
        status = "unverifiable"
        detail = (
            "The matched post is no longer accessible, so its content "
            "cannot be re-hashed. The on-chain record itself is intact."
        )
        recomputed_record_hash = None
    else:
        # Recompute the deterministic record_hash with the current content
        recomputed_record_hash = compute_record_hash({
            "content_hash": current_content_hash,
            "image_file": fingerprint.get("image_file", ""),
            "matched_url": matched_url,
            "platform": fingerprint.get("platform", ""),
            "subject": subject,
        })
        logger.info("Recomputed record_hash: %s", recomputed_record_hash)
        if current_content_hash == original_content_hash:
            if recomputed_record_hash == uploaded_record_hash:
                status = "verified"
                detail = (
                    "Post content unchanged and recomputed record_hash "
                    "matches the on-chain record."
                )
            else:
                status = "record_mismatch"
                detail = (
                    "Post content matches the fingerprint, but the recomputed "
                    "record_hash differs from the on-chain record. The chain "
                    "record does not correspond to this fingerprint."
                )
        else:
            status = "tampered"
            detail = (
                "Post content has CHANGED since upload. Original content_hash "
                f"{original_content_hash} != current {current_content_hash}. "
                "A tamper/replacement would be detectable by re-running this "
                "verifier."
            )

    logger.info("VERDICT: %s", status.upper())

    # 5. Save the verification record
    result = {
        "subject": subject,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "tx_hash": tx_hash,
        "uploaded_record_hash": uploaded_record_hash,
        "on_chain_record_hash": on_chain_record,
        "on_chain_fetch_error": fetch_err,
        "calldata_matches_upload": on_chain_matches_upload,
        "matched_url": matched_url,
        "original_content_hash": original_content_hash,
        "current_content_hash": current_content_hash,
        "recomputed_record_hash": recomputed_record_hash,
        "status": status,
        "detail": detail,
    }

    out_dir = PROJECT_ROOT / "chain" / "verifications"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{subject}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    logger.info("Verification saved to %s", out_path)

    return result


def main():
    """CLI entry point for chain.verify module."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Re-verify a fingerprint against the blockchain and live post content"
    )
    parser.add_argument(
        "--subject",
        required=True,
        help="Subject name (must have chain/uploads/<subject>.json from Phase 4)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    try:
        result = verify_subject(args.subject)
        print(f"\n=== Verification for '{args.subject}' ===")
        print(f"status: {result['status']}")
        print(f"tx_hash: {result['tx_hash']}")
        print(f"uploaded record_hash: {result['uploaded_record_hash']}")
        print(f"on-chain record_hash: {result['on_chain_record_hash']}")
        print(f"matched_url: {result['matched_url']}")
        print(f"detail: {result['detail']}")
        print(f"Saved to: chain/verifications/{args.subject}.json")
    except FileNotFoundError as e:
        logger.error("%s", e)
        sys.exit(1)
    except (RuntimeError, ValueError) as e:
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