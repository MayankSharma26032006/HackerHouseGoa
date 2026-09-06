"""chain.fingerprint - Deterministic fingerprint record for blockchain upload.

Takes Phase 2 output JSON and produces a canonical, deterministic fingerprint
record — combining content_hash with subject name, matched URL, and platform
into one structure, then hashing it into a single record_hash.

The record_hash covers exactly 5 content-bearing fields (subject, image_file,
matched_url, content_hash, platform) serialized with sorted keys and no
whitespace, ensuring the same inputs always produce the same hash.
"""

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# The 5 content-bearing fields included in the record_hash
HASH_FIELDS = ("subject", "image_file", "matched_url", "content_hash", "platform")


def load_phase2_output(subject):
    """Load the Phase 2 search results for a given subject.

    Returns the parsed JSON dict. Raises FileNotFoundError or ValueError
    if the file is missing, malformed, or has no best_match.
    """
    results_path = (
        Path(__file__).resolve().parent.parent / "web_search" / "results" / f"{subject}.json"
    )
    if not results_path.is_file():
        raise FileNotFoundError(
            f"Phase 2 output not found: {results_path}\n"
            f"Run 'python -m web_search.run --subject {subject}' first."
        )

    try:
        with open(results_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Phase 2 output is not valid JSON: {results_path}\n{e}") from e

    if data.get("best_match") is None:
        raise ValueError(
            f"No best_match in Phase 2 output for '{subject}' "
            f"(file: {results_path}).\n"
            "Run 'python -m web_search.run --subject {subject}' and ensure "
            "it finds a social media match."
        )

    return data


def build_fingerprint_record(phase2_data):
    """Build the fingerprint record dict from Phase 2 output.

    Returns (record_dict, canonical_dict) where:
    - record_dict is the full output to save as JSON
    - canonical_dict is the 5-field dict used for hashing
    """
    best = phase2_data["best_match"]
    subject = phase2_data["subject"]

    # Extract the 5 content-bearing fields
    content_hash = best.get("content_hash")  # may be null
    image_file = phase2_data.get("image_file", "")
    matched_url = best.get("url", "")
    platform = best.get("platform", "")
    match_type = best.get("match_type", "")

    # Build the canonical dict (alphabetical key order for determinism)
    canonical_dict = {
        "content_hash": content_hash,
        "image_file": image_file,
        "matched_url": matched_url,
        "platform": platform,
        "subject": subject,
    }

    # Build the full record
    record = {
        "subject": subject,
        "image_file": image_file,
        "matched_url": matched_url,
        "platform": platform,
        "match_type": match_type,
        "content_hash": content_hash,
        "phase2_search_timestamp": phase2_data.get("search_timestamp", ""),
        "fingerprint_generated_at": datetime.now(timezone.utc).isoformat(),
        "record_hash": "",  # filled in by compute_record_hash
    }

    return record, canonical_dict


def compute_record_hash(canonical_dict):
    """Compute the deterministic record_hash from the 5-field canonical dict.

    Uses json.dumps with sort_keys=True, compact separators, and
    ensure_ascii=True to guarantee reproducibility.
    Returns the hash string (e.g. "sha256:abcdef...").
    """
    canonical_bytes = json.dumps(
        canonical_dict,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")

    return "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()


def save_fingerprint(record, subject):
    """Save the fingerprint record to chain/fingerprints/<subject>.json.

    Creates the directory if it doesn't exist.
    """
    out_dir = Path(__file__).resolve().parent / "fingerprints"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{subject}.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    return out_path


def fingerprint_subject(subject):
    """Full fingerprinting pipeline for a subject.

    1. Load Phase 2 output
    2. Build canonical dict from 5 content fields
    3. Compute record_hash
    4. Save fingerprint record
    Returns the record dict.
    """
    # 1. Load Phase 2 output
    phase2_data = load_phase2_output(subject)
    logger.info("Loaded Phase 2 output: %s", phase2_data.get("image_file", "?"))

    best = phase2_data["best_match"]
    content_hash = best.get("content_hash")
    matched_url = best.get("url", "")
    platform = best.get("platform", "")
    match_type = best.get("match_type", "")

    logger.info("Subject: %s", subject)
    logger.info("Matched URL: %s", matched_url)
    logger.info("Platform: %s | match_type: %s", platform, match_type)

    if content_hash is None:
        logger.warning(
            "content_hash is null (URL was inaccessible) "
            "-- record_hash computed without content proof"
        )

    # 2. Build fingerprint record and canonical dict
    record, canonical_dict = build_fingerprint_record(phase2_data)

    # Log the canonical input for verifiability
    logger.info(
        "Canonical input (5 fields): subject=%s, image_file=%s, matched_url=%s, content_hash=%s, platform=%s",
        canonical_dict["subject"],
        canonical_dict["image_file"],
        canonical_dict["matched_url"][:60] + "..." if len(canonical_dict["matched_url"]) > 60 else canonical_dict["matched_url"],
        canonical_dict["content_hash"],
        canonical_dict["platform"],
    )

    # 3. Compute record_hash
    record_hash = compute_record_hash(canonical_dict)
    record["record_hash"] = record_hash
    logger.info("record_hash: %s", record_hash)

    # 4. Save fingerprint
    out_path = save_fingerprint(record, subject)
    logger.info("Fingerprint saved to %s", out_path)

    return record


def main():
    """CLI entry point for chain.fingerprint module."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate a deterministic fingerprint record for blockchain upload"
    )
    parser.add_argument(
        "--subject",
        required=True,
        help="Subject name (must have web_search/results/<subject>.json from Phase 2)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    try:
        record = fingerprint_subject(args.subject)
        print(f"\n=== Fingerprint for '{args.subject}' ===")
        print(f"record_hash: {record['record_hash']}")
        print(f"matched_url: {record['matched_url']}")
        print(f"platform: {record['platform']}")
        ch = record["content_hash"]
        if ch:
            print(f"content_hash: {ch[:60]}...")
        else:
            print("content_hash: null (URL inaccessible)")
        print(f"Saved to: chain/fingerprints/{args.subject}.json")
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        sys.exit(1)
    except KeyError as e:
        logger.error("Missing field in Phase 2 output: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
