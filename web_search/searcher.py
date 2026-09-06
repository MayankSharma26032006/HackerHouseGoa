"""web_search.searcher - Reverse image search via Google Cloud Vision WEB_DETECTION.

Uses the Google Cloud Vision API to find web pages containing the same
or visually similar image as a consented subject photo.
Filters results to social media platforms and saves structured output for Phase 3.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from google.cloud import vision

logger = logging.getLogger(__name__)

SOCIAL_DOMAINS = {
    "instagram.com": "Instagram",
    "www.instagram.com": "Instagram",
    "twitter.com": "Twitter/X",
    "x.com": "Twitter/X",
    "www.x.com": "Twitter/X",
    "mobile.twitter.com": "Twitter/X",
    "m.x.com": "Twitter/X",
    "facebook.com": "Facebook",
    "www.facebook.com": "Facebook",
    "m.facebook.com": "Facebook",
    "linkedin.com": "LinkedIn",
    "www.linkedin.com": "LinkedIn",
    "reddit.com": "Reddit",
    "www.reddit.com": "Reddit",
    "old.reddit.com": "Reddit",
    "pinterest.com": "Pinterest",
    "www.pinterest.com": "Pinterest",
    "tumblr.com": "Tumblr",
    "www.tumblr.com": "Tumblr",
    "threads.net": "Threads",
    "www.threads.net": "Threads",
    "bsky.app": "Bluesky",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}


def verify_consent(subject):
    subjects_dir = Path(__file__).resolve().parent.parent / "data" / "subjects"
    subject_dir = subjects_dir / subject
    consent_file = subject_dir / "consent.txt"
    if not subject_dir.is_dir():
        raise FileNotFoundError(f"Subject dir not found: {subject_dir}")
    if not consent_file.is_file():
        raise PermissionError(f"CONSENT NOT FOUND for '{subject}' at {consent_file}")
    logger.info("Consent OK for '%s'", subject)
    return subject_dir


def select_image(subject_dir):
    candidates = sorted(p for p in subject_dir.iterdir()
                        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
    if not candidates:
        raise FileNotFoundError(f"No images in {subject_dir}")
    if len(candidates) > 1:
        logger.info("Multiple images, using first: %s", candidates[0].name)
    return candidates[0]


def _identify_platform(url):
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return SOCIAL_DOMAINS.get(host, "Unknown")


def search_reverse_image(image_path):
    client = vision.ImageAnnotatorClient()
    with open(image_path, "rb") as f:
        image_content = f.read()
    image = vision.Image(content=image_content)
    logger.info("Calling Vision API WEB_DETECTION on %s ...", image_path.name)
    response = client.web_detection(image=image)
    if response.error.message:
        raise RuntimeError(f"Vision API error: {response.error.message}")
    wd = response.web_detection
    if not wd:
        return {"pages_with_matching": [], "partial_matches": [], "visually_similar": []}
    def _parse(pages, mt):
        return [{"url": p.url, "page_title": p.page_title or "",
                 "match_type": mt, "platform": _identify_platform(p.url)} for p in pages]
    full = _parse(wd.pages_with_matching_images, "full")
    partial = _parse(wd.partial_matching_images, "partial")
    vis = _parse(wd.visually_similar_images, "visually_similar")
    logger.info("API: %d full, %d partial, %d visually similar", len(full), len(partial), len(vis))
    return {"pages_with_matching": full, "partial_matches": partial, "visually_similar": vis}


def filter_social_media(api_results):
    all_results, seen = [], set()
    priority = {"full": 0, "partial": 1, "visually_similar": 2}
    for key in ["pages_with_matching", "partial_matches", "visually_similar"]:
        for e in api_results.get(key, []):
            url = e["url"]
            if url in seen:
                continue
            seen.add(url)
            plat = _identify_platform(url)
            if plat == "Unknown":
                continue
            all_results.append({"url": url, "page_title": e["page_title"],
                                "platform": plat, "match_type": e["match_type"],
                                "relevance_score": priority.get(e["match_type"], 9)})
    all_results.sort(key=lambda r: r["relevance_score"])
    logger.info("Filtered to %d social-media results from %d total",
                len(all_results), sum(len(v) for v in api_results.values()))
    return all_results


def fetch_url_accessibility(url):
    import requests
    try:
        resp = requests.get(url, timeout=10, allow_redirects=True)
        return {"url": url, "http_status": resp.status_code,
                "accessible": 200 <= resp.status_code < 400, "final_url": resp.url}
    except requests.RequestException as e:
        return {"url": url, "http_status": None, "accessible": False, "error": str(e)}


def run_search(subject):
    subject_dir = verify_consent(subject)
    image_path = select_image(subject_dir)
    logger.info("Searching with image: %s", image_path)
    api_results = search_reverse_image(image_path)
    social = filter_social_media(api_results)
    total = sum(len(v) for v in api_results.values())
    logger.info("Raw API total hits: %d", total)
    if social:
        best = social[0]
        logger.info("Best match: %s [%s] (%s)", best["platform"], best["url"], best["match_type"])
        ac = fetch_url_accessibility(best["url"])
        logger.info("URL check: status=%s accessible=%s", ac["http_status"], ac["accessible"])
    else:
        logger.warning("No social media matches for '%s'", subject)
    output = {"subject": subject, "image_file": str(image_path.name),
              "search_timestamp": datetime.now(timezone.utc).isoformat(),
              "total_api_hits": total, "social_media_matches": social,
              "best_match": social[0] if social else None}
    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(exist_ok=True)
    output_path = results_dir / f"{subject}.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Results saved to %s", output_path)
    return output


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Reverse image search for consented subjects")
    parser.add_argument("--subject", required=True, help="Subject name (must have consent.txt)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
    try:
        result = run_search(args.subject)
        matches = result["social_media_matches"]
        print(f"\n=== Search Results for '{args.subject}' ===")
        print(f"Image: {result['image_file']}")
        print(f"Total API hits: {result['total_api_hits']}")
        print(f"Social media matches: {len(matches)}")
        if matches:
            for i, m in enumerate(matches[:5]):
                print(f"  [{i+1}] {m['platform']}: {m['url']}")
                print(f"      match_type={m['match_type']}, title={m['page_title'][:80]}")
        else:
            print("  No social media matches found.")
        print(f"\nResults saved to: web_search/results/{args.subject}.json")
    except (FileNotFoundError, PermissionError) as e:
        logger.error("%s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
