"""web_search.searcher - Reverse image search via Apify borderline/google-lens actor.

Uses the Apify Google Lens actor to find web pages containing the same
or visually similar image as a consented subject photo.
Filters results to social media platforms and saves structured output for Phase 3.
"""

import base64
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

# Load .env file if present (for APIFY_API_TOKEN and other vars)
load_dotenv()

logger = logging.getLogger(__name__)

# Apify actor endpoint (synchronous run -> dataset items)
APIFY_RUN_URL = (
    "https://api.apify.com/v2/acts/borderline~google-lens"
    "/run-sync-get-dataset-items"
)

# Search types to request — only web search and exact matches.
# Explicitly excludes: ai-mode, ocr, translate-ocr, products, homework
SEARCH_TYPES = ["exact-match", "all"]

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
    """Check that consent.txt exists for this subject. Raises if not."""
    subjects_dir = Path(__file__).resolve().parent.parent / "data" / "subjects"
    subject_dir = subjects_dir / subject
    consent_file = subject_dir / "consent.txt"
    if not subject_dir.is_dir():
        raise FileNotFoundError(f"Subject dir not found: {subject_dir}")
    if not consent_file.is_file():
        raise PermissionError(
            f"CONSENT NOT FOUND for '{subject}' at {consent_file}. "
            "Every image must belong to a subject who has given explicit consent."
        )
    logger.info("Consent OK for '%s'", subject)
    return subject_dir


def select_image(subject_dir):
    """Pick the first (alphabetically) supported image from the subject dir."""
    candidates = sorted(
        p for p in subject_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not candidates:
        raise FileNotFoundError(
            f"No supported images found in {subject_dir}. "
            f"Supported formats: {IMAGE_EXTENSIONS}"
        )
    if len(candidates) > 1:
        logger.info("Multiple images found, using first: %s", candidates[0].name)
    return candidates[0]


def encode_image_base64(image_path):
    """Read an image file and return its base64-encoded string."""
    with open(image_path, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode("ascii")
    logger.info("Encoded image as base64 (%d bytes -> %d base64 chars)", len(raw), len(b64))
    return b64


def call_apify_actor(image_b64):
    """Call the Apify borderline/google-lens actor with a base64 image.

    Returns the raw dataset items (list of dicts) from the Apify response.
    Raises RuntimeError on API failure.
    """
    api_token = os.environ.get("APIFY_API_TOKEN")
    if not api_token:
        raise RuntimeError(
            "APIFY_API_TOKEN environment variable is not set. "
            "Get your token from Apify Console -> Settings -> API & Integrations "
            "-> Personal API token, then add it to your .env file."
        )

    payload = {
        "searchTypes": SEARCH_TYPES,
        "imagesBase64": [image_b64],
    }

    logger.info(
        "Calling Apify actor borderline/google-lens (%s) ...",
        ", ".join(SEARCH_TYPES),
    )

    try:
        resp = requests.post(
            APIFY_RUN_URL,
            params={"token": api_token},
            json=payload,
            timeout=180,
        )
    except requests.ConnectionError as e:
        raise RuntimeError(f"Network error connecting to Apify API: {e}") from e
    except requests.Timeout as e:
        raise RuntimeError("Apify actor run timed out (120s limit)") from e

    # Log the HTTP status for verifiability
    logger.info("Apify API HTTP status: %d", resp.status_code)

    if resp.status_code == 401:
        raise RuntimeError(
            "Invalid Apify API token (HTTP 401). "
            "Check your APIFY_API_TOKEN in .env."
        )
    if resp.status_code == 402:
        raise RuntimeError(
            "Apify account out of credits (HTTP 402). "
            "Add credits at https://console.apify.com/billing."
        )

    # Apify sync endpoints return 200 or 201 on success
    if resp.status_code not in (200, 201):
        try:
            err_body = resp.json()
            error_msg = err_body.get("error", {}).get("message", resp.text[:500])
        except Exception:
            error_msg = resp.text[:500]
        raise RuntimeError(f"Apify API error (HTTP {resp.status_code}): {error_msg}")

    items = resp.json()
    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected Apify response shape: {type(items).__name__}")

    logger.info("Apify run complete — %d items returned", len(items))
    return items


# Cache for resolved redirect URLs (avoids redundant requests)
_redirect_cache = {}


def resolve_url(url):
    """Resolve a URL to its final destination, following redirects.

    For Google redirect URLs (google.com/goto?url=...), follows the
    302 redirect chain to get the real destination URL.
    For direct URLs, returns the URL unchanged.
    Returns (resolved_url, is_redirect, error_or_None).
    """
    if url in _redirect_cache:
        return _redirect_cache[url]

    parsed = urlparse(url)
    is_redirect = (
        parsed.hostname in ("www.google.com", "google.com")
        and parsed.path.startswith("/goto")
    )

    if not is_redirect:
        result = (url, False, None)
        _redirect_cache[url] = result
        return result

    # Follow the redirect to get the real destination
    try:
        resp = requests.get(
            url, timeout=15, allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        final_url = resp.url
        if final_url and final_url != url:
            logger.info("  Resolved redirect: %s -> %s", url[:60], final_url[:80])
            result = (final_url, True, None)
        else:
            logger.warning("  Redirect did not resolve to a new URL: %s", url[:80])
            result = (url, True, "redirect did not resolve")
    except requests.Timeout:
        logger.warning("  Redirect timeout: %s", url[:80])
        result = (url, True, "timeout")
    except requests.RequestException as e:
        logger.warning("  Redirect resolution failed: %s — %s", url[:60], str(e)[:60])
        result = (url, True, str(e))

    _redirect_cache[url] = result
    return result


def _extract_url_from_item(item):
    """Extract the result URL from an Apify dataset item based on its searchType.

    Handles both successful results (with link/href) and error entries
    (with error/message keys but no URL).
    """
    search_type = item.get("searchType", "")
    if search_type == "exact-match":
        results = item.get("exact-match", {}).get("results", [])
        for r in results:
            # Skip error entries (e.g. "No results found")
            if "error" in r:
                continue
            link = r.get("link", "")
            if link:
                return link, r.get("title", ""), "exact_match"
    elif search_type == "all":
        results = item.get("all", {}).get("results", [])
        for r in results:
            if "error" in r:
                continue
            search_data = r.get("search", {})
            href = search_data.get("href", "")
            if href:
                return href, search_data.get("title", ""), "web_result"
    return None, None, None


def _identify_platform(url):
    """Map a URL's hostname to a social media platform name, or 'Unknown'.

    Handles country-specific subdomains (e.g. in.linkedin.com, fr.facebook.com)
    by stripping the first subdomain and re-checking.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    # Direct match
    if host in SOCIAL_DOMAINS:
        return SOCIAL_DOMAINS[host]
    # Strip country prefix (e.g. in.linkedin.com -> linkedin.com)
    parts = host.split(".")
    if len(parts) > 2:
        stripped = ".".join(parts[-2:])
        if stripped in SOCIAL_DOMAINS:
            return SOCIAL_DOMAINS[stripped]
    return "Unknown"


def _print_raw_items(dataset_items):
    """Print every raw Apify dataset item, resolving redirects inline.

    Shows searchType, raw URL, resolved URL (if redirect), title, and platform.
    Handles error entries (no URL) and Google redirect URLs.
    """
    print("\n" + "=" * 70)
    print("RAW API ITEMS (before social-media filtering)")
    print("=" * 70)
    for i, item in enumerate(dataset_items):
        search_type = item.get("searchType", "unknown")
        url, title, match_type = _extract_url_from_item(item)
        if url:
            resolved, is_redirect, err = resolve_url(url)
            platform = _identify_platform(resolved)
            print(f"  [{i+1}] searchType={search_type}  match_type={match_type}")
            if is_redirect:
                print(f"       raw_url={url}")
                print(f"       resolved={resolved}  error={err}")
            else:
                print(f"       url={url}")
            print(f"       platform={platform}  title={title}")
        else:
            # Error entry or unextractable structure
            nested = item.get(search_type, {})
            err_msg = "(no extractable URL)"
            if isinstance(nested, dict):
                results = nested.get("results", [])
                if results and isinstance(results[0], dict):
                    err_msg = results[0].get("error", results[0].get("message", err_msg))
            print(f"  [{i+1}] searchType={search_type}  match_type=N/A")
            print(f"       {err_msg}")
    print("=" * 70 + "\n")


def filter_social_media(dataset_items):
    """Filter Apify dataset items to social media URLs, ranked by match type.

    Returns a list of dicts sorted by relevance_score (lower = better).
    """
    all_results = []
    seen_urls = set()
    priority = {"exact_match": 0, "web_result": 1}

    exact_count = 0
    web_count = 0

    for item in dataset_items:
        search_type = item.get("searchType", "")
        if search_type == "exact-match":
            exact_count += 1
        elif search_type == "all":
            web_count += 1

        url, title, match_type = _extract_url_from_item(item)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        # Resolve Google redirect URLs to their real destination
        resolved, is_redirect, resolve_err = resolve_url(url)
        if resolve_err:
            logger.warning("  Skipping item — redirect resolution failed: %s", resolve_err)
            continue

        # Use the resolved URL for platform detection and output
        platform = _identify_platform(resolved)
        if platform == "Unknown":
            continue

        all_results.append({
            "url": resolved,
            "raw_url": url if is_redirect else None,
            "page_title": title,
            "platform": platform,
            "match_type": match_type,
            "relevance_score": priority.get(match_type, 9),
        })

    all_results.sort(key=lambda r: r["relevance_score"])
    logger.info(
        "Apify: %d exact-match, %d web-result -> %d social-media results",
        exact_count, web_count, len(all_results),
    )
    return all_results


def fetch_url_accessibility(url):
    """Check if a URL is reachable. Returns status dict."""
    try:
        resp = requests.get(url, timeout=10, allow_redirects=True)
        return {
            "url": url,
            "http_status": resp.status_code,
            "accessible": 200 <= resp.status_code < 400,
            "final_url": resp.url,
        }
    except requests.RequestException as e:
        return {
            "url": url,
            "http_status": None,
            "accessible": False,
            "error": str(e),
        }


def fetch_content_hash(url):
    """Fetch a URL and return its SHA-256 content hash. Returns None on failure."""
    try:
        resp = requests.get(url, timeout=10, allow_redirects=True)
        if 200 <= resp.status_code < 400:
            h = hashlib.sha256(resp.content).hexdigest()
            return f"sha256:{h}"
    except requests.RequestException as e:
        logger.warning("Failed to fetch content for hash: %s", e)
    return None


def run_search(subject, debug_raw=False):
    """End-to-end search for a consented subject.

    Returns the output dict and saves to web_search/results/<subject>.json.
    If debug_raw=True, prints all raw API items before filtering.
    """
    subject_dir = verify_consent(subject)
    image_path = select_image(subject_dir)
    logger.info("Searching with image: %s", image_path)

    # Encode the image as base64 for Apify
    image_b64 = encode_image_base64(image_path)

    # Call the Apify actor
    dataset_items = call_apify_actor(image_b64)

    # Debug: dump all raw items before filtering
    if debug_raw:
        _print_raw_items(dataset_items)

    # Filter to social media results
    social = filter_social_media(dataset_items)
    total = len(dataset_items)

    # Build output
    best = None
    if social:
        best = social[0]
        logger.info(
            "Best match: %s [%s] (%s)",
            best["platform"], best["url"], best["match_type"],
        )

        # URL accessibility check
        ac = fetch_url_accessibility(best["url"])
        logger.info("URL check: status=%s accessible=%s", ac["http_status"], ac["accessible"])

        # Content hash for Phase 3
        logger.info("Fetching page for content_hash...")
        content_hash = fetch_content_hash(best["url"])
        if content_hash:
            best["content_hash"] = content_hash
            logger.info("content_hash: %s", content_hash[:60] + "...")
        else:
            best["content_hash"] = None
            logger.warning("Could not compute content_hash (URL may be inaccessible)")
    else:
        logger.warning("No social media matches for '%s'", subject)

    output = {
        "subject": subject,
        "image_file": str(image_path.name),
        "search_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_api_hits": total,
        "social_media_matches": social,
        "best_match": best,
    }

    # Save results
    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(exist_ok=True)
    output_path = results_dir / f"{subject}.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    logger.info("Results saved to %s", output_path)

    return output


def main():
    """CLI entry point for web search module."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Reverse image search for consented subjects via Apify Google Lens"
    )
    parser.add_argument(
        "--subject", required=True,
        help="Subject name (must have consent.txt in data/subjects/<name>/)"
    )
    parser.add_argument(
        "--debug-raw", action="store_true",
        help="Print all raw API items before social-media filtering"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    try:
        result = run_search(args.subject, debug_raw=args.debug_raw)
        matches = result["social_media_matches"]
        print(f"\n=== Search Results for '{args.subject}' ===")
        print(f"Image: {result['image_file']}")
        print(f"Total API hits: {result['total_api_hits']}")
        print(f"Social media matches: {len(matches)}")
        if matches:
            for i, m in enumerate(matches[:5]):
                print(f"  [{i+1}] {m['platform']}: {m['url']}")
                print(f"      match_type={m['match_type']}, title={m['page_title'][:80]}")
            best = result["best_match"]
            if best and best.get("content_hash"):
                print(f"  content_hash: {best['content_hash'][:60]}...")
        else:
            print("  No social media matches found.")
        print(f"\nResults saved to: web_search/results/{args.subject}.json")
    except (FileNotFoundError, PermissionError) as e:
        logger.error("%s", e)
        sys.exit(1)
    except RuntimeError as e:
        logger.error("API error: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
