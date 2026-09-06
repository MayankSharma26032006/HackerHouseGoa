# Phase 2: Web / Social Media Search

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

> **Note:** This constraints block must be copy-pasted at the top of every
> future phase's design.md.

---

## 1. API Choice: Google Cloud Vision API (WEB_DETECTION)

### Why Google Cloud Vision

| Candidate | Verdict | Reason |
|-----------|---------|--------|
| **Google Cloud Vision (WEB_DETECTION)** | **Selected** | Returns `pagesWithMatchingImages`, `partialMatchingImages`, and `visuallySimilarImages` — exactly the reverse-image-search feature we need. Accepts raw image bytes (no public URL required). Free tier: 1,000 units/month (1 unit = 1 image request), then $1.50/1k — generous for hackathon. Well-documented Python client. |
| Bing Visual Search | Rejected | Less generous free tier; API requires URL upload or subscription key management; fewer results for face-matching use cases. |
| SerpApi Google Reverse Image | Rejected | Third-party wrapper; requires paid plan ($50/mo) for meaningful usage; adds a dependency on a proxy service. |
| PimEyes | Rejected | Paid-only (starts at ~$30/mo); designed for face identification which conflicts with our consent-only constraint. |

### Required API key

Added to `.env.example`:
```
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your-service-account.json
```

The `google-cloud-vision` SDK reads this environment variable automatically.
The service account JSON file itself is `.gitignore`d (never committed).

---

## 2. Input Contract

```
web_search/searcher.py --subject <name>
```

- **Subject directory:** `data/subjects/<name>/`
- **Consent gate:** Before any external API call, `verify_consent()` checks for
  `data/subjects/<name>/consent.txt`. If absent → raises `PermissionError` with
  a clear message and exits. This runs **independently** of Phase 1 — even if
  Phase 1 already validated consent in a separate invocation, this stage
  re-verifies before making any outbound request.
- **Image selection:** The script picks one representative image from the
  subject directory (first alphabetically among supported formats). Supported:
  `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.gif`, `.tiff`.

---

## 3. API Call Mechanics

### Image submission

Google Cloud Vision API accepts **raw image bytes** directly — no public URL needed.

```python
client = vision.ImageAnnotatorClient()
with open(image_path, "rb") as f:
    image_content = f.read()
image = vision.Image(content=image_content)
response = client.web_detection(image=image)
```

This is the cleanest path for a hackathon: no image hosting, no tunnels, no temporary servers. The SDK handles authentication via `GOOGLE_APPLICATION_CREDENTIALS`.

### Response structure

The `WebDetection` response contains:
- `pages_with_matching_images` — pages that contain the exact same image
- `partial_matching_images` — pages with a crop/partial match
- `visually_similar_images` — pages with similar (but not identical) images

Each entry has a `url` and `page_title`.

---

## 4. Result Filtering

### Social media domain allowlist

```python
SOCIAL_DOMAINS = {
    "instagram.com": "Instagram",
    "x.com": "Twitter/X",
    "twitter.com": "Twitter/X",
    "facebook.com": "Facebook",
    "linkedin.com": "LinkedIn",
    "reddit.com": "Reddit",
    "pinterest.com": "Pinterest",
    "tumblr.com": "Tumblr",
    "threads.net": "Threads",
    "bsky.app": "Bluesky",
    # + www/mobile subdomains
}
```

### Selection logic

1. All three match categories are merged, deduplicated by URL.
2. Each match is assigned a `relevance_score`:
   - `full` match → 0 (highest)
   - `partial` match → 1
   - `visually_similar` → 2 (lowest)
3. Results are sorted by `relevance_score` ascending.
4. Non-social-media URLs are discarded entirely.
5. The `best_match` field in the output is the first result after sorting.
6. The top result's URL is accessibility-checked (`HEAD`-like `GET` with timeout)
   to confirm it's still live — this status is logged and included in the output.

This is **not** "first result wins" — it's a ranked-by-match-type approach where
full matches always outrank partial, which outrank visually similar, and only
social-media platforms are considered.

---

## 5. Output Contract

### File location

```
web_search/results/<subject>.json
```

### Schema

```json
{
  "subject": "alice",
  "image_file": "photo.jpg",
  "search_timestamp": "2026-09-02T22:00:00+00:00",
  "total_api_hits": 47,
  "social_media_matches": [
    {
      "url": "https://www.instagram.com/p/ABC123/",
      "page_title": "Alice at the meetup",
      "platform": "Instagram",
      "match_type": "full",
      "relevance_score": 0
    }
  ],
  "best_match": {
    "url": "https://www.instagram.com/p/ABC123/",
    "page_title": "Alice at the meetup",
    "platform": "Instagram",
    "match_type": "full",
    "relevance_score": 0
  }
}
```

### Fields consumed by Phase 3

- `best_match.url` — the URL to hash and upload to blockchain
- `best_match.platform` — metadata for the blockchain record
- `image_file` — for traceability back to the source image

---

## 6. Failure Handling

| Failure | Behavior |
|---------|----------|
| **No consent.txt found** | `PermissionError` raised, logged, `sys.exit(1)` — no API call made |
| **No image files in subject dir** | `FileNotFoundError` raised, logged, `sys.exit(1)` |
| **No social media matches** | Warning logged; output JSON saved with empty `social_media_matches` and `best_match: null` — not a crash |
| **API key missing/invalid** | `google.auth` raises `DefaultCredentialsError` / API returns error message → `RuntimeError` raised, logged, `sys.exit(1)` |
| **API rate limit (429)** | Google SDK raises `google.api_core.exceptions.TooManyRequests` → caught as generic `Exception`, logged with full error, `sys.exit(1)` |
| **Network failure** | `requests.ConnectionError` during URL accessibility check → logged with error details, result still saved (URL access check is advisory) |
| **Dead/inaccessible URL** | `fetch_url_accessibility()` returns `accessible: false` with the HTTP status — logged as a warning, result still saved (the URL is still the best evidence we have) |
| **Vision API error in response** | `response.error.message` is non-empty → `RuntimeError` raised with the error message |

---

## 7. Verifiability Requirement

This stage is the most scrutinized for authenticity. The design ensures:

1. **Real API call evidence:** The script logs:
   - The image filename being sent
   - The raw API hit counts: `"API: N full, M partial, K visually similar"`
   - The total hit count before filtering
   - The filtered social media count

2. **Real URL output:** The `best_match.url` is a live URL produced by the API,
   logged in the terminal output, and clickable by a human reviewer. It is
   **impossible** for this URL to be hardcoded because:
   - There are no URL string literals in `searcher.py` (grep-verifiable)
   - The URL comes directly from `response.web_detection.pages_with_matching_images[i].url`
   - The social media filter only checks the domain — it doesn't fabricate URLs

3. **URL accessibility proof:** The top result's URL is fetched with a real HTTP
   request, and the status code is logged — proving the URL is real and live.

4. **Timestamp evidence:** The output JSON includes a UTC ISO timestamp of when
   the search was performed, verifiable against the system clock.

5. **Full pipeline traceability:** The output JSON contains
 both `subject` and
  `image_file`, creating a clear chain from consented image → API call → result.

---

## 8. Testability

### CLI entry point

```bash
python -m web_search.run --subject alice
```

### What the reviewer sees

```
2026-09-02 22:00:00 [INFO] Consent verified for subject 'alice'
2026-09-02 22:00:00 [INFO] Searching with image: data/subjects/alice/photo.jpg
2026-09-02 22:00:01 [INFO] Calling Vision API WEB_DETECTION on photo.jpg ...
2026-09-02 22:00:02 [INFO] API: 12 full, 5 partial, 30 visually similar
2026-09-02 22:00:02 [INFO] Filtered to 8 social-media results from 47 total
2026-09-02 22:00:02 [INFO] Best match: Instagram [https://www.instagram.com/p/ABC123/] (full)
2026-09-02 22:00:02 [INFO] URL check: status=200 accessible=True

=== Search Results for 'alice' ===
Image: photo.jpg
Total API hits: 47
Social media matches: 8
  [1] Instagram: https://www.instagram.com/p/ABC123/
      match_type=full, title=Alice at the meetup

Results saved to: web_search/results/alice.json
```

---

## 9. Definition of Done

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | `pip install` installs `google-cloud-vision` | Exit code 0, import works |
| 2 | Consent check blocks unconsented subject | `--subject fake` raises PermissionError |
| 3 | Consent check passes for consented subject | Runs without PermissionError when consent.txt exists |
| 4 | Real Google Cloud Vision API call is made | Logs show actual API response counts |
| 5 | Social media filtering works | Output JSON contains only allowlisted domains |
| 6 | Best match is ranked, not random | Full matches ranked above partial above visually_similar |
| 7 | URL accessibility check runs | Log shows real HTTP status code |
| 8 | Output JSON saved at expected path | `web_search/results/<subject>.json` is valid JSON |
| 9 | No hardcoded URLs in code | `grep` shows no URL string literals in searcher.py |
| 10 | API failure produces clear error | Invalid credentials raises RuntimeError |
| 11 | `results/*.json` gitignored | `.gitignore` contains the pattern |
| 12 | Constraints block in design document | Present at top of design_phase2.md |
