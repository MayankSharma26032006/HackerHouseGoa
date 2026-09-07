"""demo.run_pipeline - Phase 6: end-to-end orchestration for the demo recording.

Runs every stage of the pipeline as its own subprocess so each one
performs the real operation and stays independently re-runnable:

    [1] Phase 1  face_id.run        face detection + embedding (consent-gated)
    [2] Phase 2  web_search.run     reverse image search for matching posts
    [3] Phase 3  chain.fingerprint  deterministic record_hash
    [4] Phase 4  chain.upload       upload record_hash to Sepolia testnet
    [5] Phase 5  chain.verify       re-fetch + re-hash + compare on-chain

Stage output streams straight to the console (each module logs its own
verifiable evidence), and the script aborts with a clear message and the
stage's exit code on the first failure.

Usage:
    python -m demo.run_pipeline --subject alice
    python -m demo.run_pipeline --subject alice --skip-upload   # dry demo, no chain
    python -m demo.run_pipeline --subject alice --dry-run       # show commands only
"""

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

STAGES = [
    ("Phase 1 — face detection + embedding", "face_id.run"),
    ("Phase 2 — reverse image search", "web_search.run"),
    ("Phase 3 — fingerprinting", "chain.fingerprint"),
    ("Phase 4 — blockchain upload", "chain.upload"),
    ("Phase 5 — on-chain verification", "chain.verify"),
]


def build_commands(subject, images=None, skip_upload=False, skip_verify=False, platform=None):
    """Return the list of (stage_label, argv) the pipeline would run."""
    commands = []
    commands.append((STAGES[0][0], ["-m", "face_id.run", "--subject", subject]
                     + (["--images"] + list(images) if images else [])))
    web_search_cmd = ["-m", "web_search.run", "--subject", subject]
    if platform:
        web_search_cmd += ["--platform", platform]
    commands.append((STAGES[1][0], web_search_cmd))
    commands.append((STAGES[2][0], ["-m", "chain.fingerprint", "--subject", subject]))
    if not skip_upload:
        commands.append((STAGES[3][0], ["-m", "chain.upload", "--subject", subject]))
    if not skip_verify:
        commands.append((STAGES[4][0], ["-m", "chain.verify", "--subject", subject]))
    return commands


def run_stage(label, argv, dry_run=False):
    """Run one stage. Returns True on success, False on failure."""
    print("\n" + "=" * 72)
    print(f"=== {label}")
    print("=" * 72)

    cmd = [sys.executable] + argv
    if dry_run:
        print("$ " + " ".join(shlex.quote(c) for c in cmd))
        return 0

    print("$ " + " ".join(shlex.quote(c) for c in cmd))
    print()
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if proc.returncode != 0:
        print(f"\n[FAILED] {label} (exit code {proc.returncode}). Pipeline aborted.")
        return proc.returncode
    print(f"\n[OK] {label} completed.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Run the face-verify-chain pipeline end-to-end for a consented subject"
    )
    parser.add_argument("--subject", required=True,
                        help="Subject name (must have consent.txt in data/subjects/<name>/)")
    parser.add_argument("--images", nargs="*", default=None,
                        help="Optional: specific image paths for Phase 1")
    parser.add_argument("--skip-upload", action="store_true",
                        help="Stop after fingerprinting; do not touch the blockchain")
    parser.add_argument("--skip-verify", action="store_true",
                        help="Do not run the Phase 5 verification stage")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the commands that would run, without executing them")
    parser.add_argument("--platform", default=None,
                        help="Filter web search to a specific platform (e.g. Twitter/X, Instagram, LinkedIn)")
    args = parser.parse_args()

    commands = build_commands(args.subject, args.images, args.skip_upload, args.skip_verify,
                             platform=args.platform)
    total = len(commands)

    print("=" * 72)
    print(f"=== face-verify-chain pipeline for '{args.subject}' — {total} stages ===")
    print("=" * 72)

    try:
        for i, (label, argv) in enumerate(commands, start=1):
            print(f"\n>>> Stage {i}/{total}: {label}")
            code = run_stage(label, argv, dry_run=args.dry_run)
            if code != 0:
                sys.exit(code)
    except KeyboardInterrupt:
        print("\nInterrupted — pipeline aborted.")
        sys.exit(130)

    if args.dry_run:
        print("\n(dry run — no commands were executed)")
        sys.exit(0)

    print("\n" + "=" * 72)
    print("=== PIPELINE COMPLETE ===")
    print("=" * 72)
    print("Artifacts:")
    print(f"  face_id/embeddings/{args.subject}.json")
    print(f"  web_search/results/{args.subject}.json")
    print(f"  chain/fingerprints/{args.subject}.json")
    if not args.skip_upload:
        print(f"  chain/uploads/{args.subject}.json")
    if not args.skip_verify:
        print(f"  chain/verifications/{args.subject}.json")


if __name__ == "__main__":
    main()