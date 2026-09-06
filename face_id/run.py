"""
face_id.run - CLI entry point for face detection + embedding extraction.

Usage:
    python -m face_id.run --subject alice
    python -m face_id.run --subject alice --images photo1.jpg photo2.png
"""

import argparse
import logging
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Extract face embeddings from consented subject images."
    )
    parser.add_argument(
        "--subject",
        required=True,
        help="Subject name (must match a directory in data/subjects/)",
    )
    parser.add_argument(
        "--images",
        nargs="*",
        default=None,
        help="Optional: specific image paths instead of scanning the subject dir",
    )
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )

    # Import here to avoid loading model on --help
    from face_id.detector import process_subject

    try:
        result = process_subject(
            subject_name=args.subject,
            specific_images=args.images,
        )
        sys.exit(0)
    except (PermissionError, FileNotFoundError, ValueError) as exc:
        logging.getLogger("face_id").error(str(exc))
        sys.exit(1)
    except RuntimeError as exc:
        logging.getLogger("face_id").error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
