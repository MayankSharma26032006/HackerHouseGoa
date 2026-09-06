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

## 1. API Choice: Apify Actor `borderline/google-lens`

### Why Apify borderline/google-lens

| Candidate | Verdict | Reason |
|-----------|---------|--------|
| **Apify `borderline/google-lens`** | **Selected** | Reverse image search via Google Lens; accepts **base64 image data directly** (no public URL needed); pay-per-event pricing with **free trial credits** (no credit card required for signup); 3.9 rating with real usage history; community-maintained; supports `exact-match` and `all` (web search) modes. |
| Google Cloud Vision (WEB_DETECTION) | Rejected | Requires GCP billing account / credit card; service account JSON setup is heavyweight for a hackathon. |
| Bing Visual Search | Rejected | Less generous free tier; API requires URL upload or subscription key management; fewer results for face-matching use cases. |
| SerpApi Google Reverse Image | Rejected | Third-party wrapper; requires paid plan ($50/mo) for meaningful usage; adds a dependency on a proxy service. |
| PimEyes | Rejected | Paid-only (starts at ~$30/mo); designed for face identification which conflicts with our consent-only constraint. |

### About this actor

- **Actor ID:** `borderline~google-lens` (full path: `borderline/google-lens`)
- **Listing:** <https://apify.com/borderline/google-lens>
- **Pricing:** Pay per event; free trial credits available on new Apify accounts.
- **Maintenance:** Community-maintained (see Section 10 for caveats).

### Required API key

Added to `.env.example`:
```
APIFY_API_TOKEN=your_apify_token_here
```

Obtained from: Apify Console → Settings → API & Integrations → Personal API token.
The token is `.env`-only (never committed).

---

## 2. Input Contract

```
python -m web_search.run --subject <name>
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
- **Image encoding:** The selected image file is read as raw bytes and
  base64-encoded for inclusion in the Apify actor input payload. No public URL
  or image hosting is needed.

---

## 3. API Call Mechanics

### Input schema (verified)

The following field names and types are confirmed from the actor's **Input tab**
(<https://apify.com/borderline/google-lens/input-schema>) and the README:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `searchTypes` | array (1–10 items) | Yes | Values: `all`, `ai-mode`, `ocr`, `translate-ocr`, `exact-match`, `visual-match`, `products`, `homework` |
| `imagesBase64` | array of strings | Conditional | Raw base64 or `data:image/...;base64,...` URI. At least one of `imagesBase64`, `imageUrls`, or `imageKvsRecords` required. |
| `imageUrls` | array of `{"url": ...}` | Conditional | Alternative to base64; for publicly-hosted images. |
| `imageKvsRecords` | array of `{"storeId": ...}` | Conditional | Alternative; images stored in Apify KVS. |
| `language` | string | No | Language for results (default `"en"`). |

Base64 input is **confirmed supported** — the actor decodes each string and
sends it directly to Google Lens. Both raw base64 and data URI formats work.

### Image submission

The Apify `borderline/google-lens` actor accepts **base64-encoded image data**
directly in the input payload — no public URL or image hosting required.

**Endpoint (synchronous run):**
```
POST https://api.apify.com/v2/acts/borderline~google-lens/run-sync-get-dataset-items?token={APIFY_API_TOKEN}
```

**Request body (JSON):**
```json
{
  "searchTypes": ["exact-match", "all"],
  "imagesBase64": ["<base64-encoded image bytes>"]
}
```

- `imagesBase64`: Accepts raw base64 strings or data URIs
  (`data:image/jpeg;base64,...`). Each image is sent to Google Lens directly.
- `searchTypes`: We request **only** `exact-match` (pages republishing the
  same image) and `all` (general web search results). We explicitly exclude
  `ai-mode`, `ocr`, `translate-ocr`, `products`, and `homework` — none are
  relevant and they would incur unnecessary cost.

**Python call:**
```python
import base64, os, requests

with open(image_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

resp = requests.post(
    f"https://api.apify.com/v2/acts/borderline~google-lens/run-sync-get-dataset-items",
    params={"token": os.environ["APIFY_API_TOKEN"]},
    json={"searchTypes": ["exact-match", "all"], "imagesBase64": [b64]},
    timeout=120,
)
```

**Why sync endpoint:** For a single-image hackathon pipeline, the synchronous
`run-sync-get-dataset-items` endpoint is simplest — it blocks until the actor
finishes and returns the dataset items directly. No polling loop needed.

**Timeout caveat:** The sync endpoint has a platform-level timeout (typically
60–120s depending on Apify plan). For this actor, image search usually
completes in 5–15s. If it times out, the script catches the error and reports
it — see Section 6.

### Response structure

The response is a JSON array of dataset items. Each item has a `searchType`
field identifying which tab it belongs to, and nested results under a matching
key:

**`searchType: "all"` — Web search results:**
```json
{
  "searchType": "all",
  "all": {
    "inputUrl": "base64:0",
    "results": [
      {
        "search": {
          "title": "Alice at the meetup",
          "href": "https://www.instagram.com/p/ABC123/",
          "description": "Photo from the event"
        },
        "inputUrl": "base64:0"
      }
    ]
  }
}
```

**`searchType: "exact-match"` — Exact image matches:**
```json
{
  "searchType": "exact-match",
  "exact-match": {
    "inputUrl": "base64:0",
    "results": [
      {
        "position": 1,
        "title": "Alice at the meetup",
        "link": "https://www.instagram.com/p/ABC123/",
        "source": "Instagram",
        "size": "1200 × 800",
        "thumbnail": "data:image/jpeg;base64,..."
      }
    ]
  }
}
```

Note: `searchType: "visual-match"` items are also present in the full dataset
but are not used for social media post matching (they contain visually similar
images, not pages hosting the same image).

---

## 4. Result Filtering

### Social media domain allowlist

```python
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
```

### Selection logic

1. The raw dataset items are separated by `searchType`:
   - `exact-match` items → exact image matches (highest priority)
   - `all` items → general web search results (lower priority)
   - All other `searchType` values (`visual-match`, `ocr`, `ai-mode`, etc.)
     are discarded — not relevant for finding social media posts.
2. URLs are extracted from each item's nested result structure:
   - `all` results: `item["all"]["results"][i]["search"]["href"]`
   - `exact-match` results: `item["exact-match"]["results"][i]["link"]`
3. Each match is assigned a `relevance_score`:
   - `exact_match` → 0 (highest)
   - `web_result` → 1 (lower)
4. Results are deduplicated by URL (same URL from multiple tabs → keep highest
   priority).
5. Non-social-media URLs are discarded entirely (domain must be in allowlist).
6. Results are sorted by `relevance_score` ascending.
7. The `best_match` field in the output is the first result after sorting.
8. The top result's URL is accessibility-checked (`GET` with timeout) to confirm
   it's still live — this status is logged and included in the output.

This is **not** "first result wins" — it's a ranked-by-match-type approach where
exact matches always outrank web results, and only social-media platforms are
considered.

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
  "apify_run_id": "abc123xyz",
  "total_api_hits": 47,
  "social_media_matches": [
    {
      "url": "https://www.instagram.com/p/ABC123/",
      "page_title": "Alice at the meetup",
      "platform": "Instagram",
      "match_type": "exact_match",
      "relevance_score": 0
    }
  ],
  "best_match": {
    "url": "https://www.instagram.com/p/ABC123/",
    "page_title": "Alice at the meetup",
    "platform": "Instagram",
    "match_type": "exact_match",
    "relevance_score": 0,
    "content_hash": "sha256:e3b0c44298fc1c149..."
  }
}
```

### Fields consumed by Phase 3

- `best_match.url` — the URL to hash and upload to blockchain
- `best_match.content_hash` — SHA-256 hash of the fetched matched page content,
  ready for on-chain upload
- `best_match.platform` — metadata for the blockchain record
- `image_file` — for traceability back to the source image

### content_hash generation

After the best match URL is selected, the script fetches the page content and
computes `hashlib.sha256(content).hexdigest()`. This pre-computes the hash that
Phase 3 will upload to the blockchain, creating a verifiable link between the
discovered post and the on-chain record. If the URL is inaccessible (see Section
6), `content_hash` is set to `null` with a warning logged.

---

## 6. Failure Handling

| Failure | Behavior |
|---------|----------|
| **No consent.txt found** | `PermissionError` raised, logged, `sys.exit(1)` — no API call made |
| **No image files in subject dir** | `FileNotFoundError` raised, logged, `sys.exit(1)` |
| **No social media matches** | Warning logged; output JSON saved with empty `social_media_matches` and `best_match: null` — not a crash |
| **APIFY_API_TOKEN missing** | `KeyError` on `os.environ["APIFY_API_TOKEN"]` → caught, clear message logged: "Set APIFY_API_TOKEN in .env", `sys.exit(1)` |
| **APIFY_API_TOKEN invalid (401)** | HTTP 401 from Apify API → `RuntimeError` raised: "Invalid Apify API token", logged, `sys.exit(1)` |
| **Actor run failure/timeout** | Apify returns run status `FAILED` or `TIMED-OUT` → `RuntimeError` raised with status, logged, `sys.exit(1)` |
| **Actor returns empty dataset** | Distinct from "no social media matches": the actor ran and returned zero items. Warning logged: "Apify actor returned empty dataset (charged $0.00?)" — output saved with empty results |
| **Network failure** | `requests.ConnectionError` during API call or URL accessibility check → logged with error details; API failure halts (`sys.exit(1)`); URL check failure is advisory (result still saved) |
| **Dead/inaccessible URL** | `fetch_url_accessibility()` returns `accessible: false` with the HTTP status — logged as a warning, result still saved (the URL is still the best evidence we have); `content_hash` set to `null` |

---

## 7. Verifiability Requirement

This stage is the most scrutinized for authenticity. The design ensures:

1. **Real API call evidence:** The script logs:
   - The image filename being sent
   - The Apify run ID (returned in the sync response)
   - The raw hit count per search type: `"Apify: N exact-match, M web-result"`
   - The total hit count before filtering
   - The filtered social media count

2. **Real URL output:** The `best_match.url` is a live URL produced by the API,
   logged in the terminal output, and clickable by a human reviewer. It is
   **impossible** for this URL to be hardcoded because:
   - There are no URL string literals in `web_search/*.py` (grep-verifiable
     across all files in the module)
   - The URL comes directly from the Apify dataset response
   - The social media filter only checks the domain — it doesn't fabricate URLs

3. **URL accessibility proof:** The top result's URL is fetched with a real HTTP
   request, and the status code is logged — proving the URL is real and live.

4. **Timestamp evidence:** The output JSON includes a UTC ISO timestamp of when
   the search was performed, verifiable against the system clock.

5. **Full pipeline traceability:** The output JSON contains both `subject` and
   `image_file`, creating a clear chain from consented image → API call → result.

6. **content_hash as proof-of-fetch:** The SHA-256 hash of the matched page
   content demonstrates that the script actually fetched and read the remote
   content, not just produced a URL from static knowledge.

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
2026-09-02 22:00:00 [INFO] Encoded image as base64 (45,213 bytes)
2026-09-02 22:00:01 [INFO] Calling Apify actor borderline/google-lens (exact-match, all) ...
2026-09-02 22:00:08 [INFO] Apify run complete — run_id=abc123xyz, 47 items returned
2026-09-02 22:00:08 [INFO] Apify: 12 exact-match, 35 web-result
2026-09-02 22:00:08 [INFO] Filtered to 8 social-media results from 47 total
2026-09-02 22:00:08 [INFO] Best match: Instagram [https://www.instagram.com/p/ABC123/] (exact_match)
2026-09-02 22:00:08 [INFO] Fetching page for content_hash...
2026-09-02 22:00:09 [INFO] URL check: status=200 accessible=True
2026-09-02 22:00:09 [INFO] content_hash: sha256:e3b0c44298fc1c149afbf4c8996fb...

=== Search Results for 'alice' ===
Image: photo.jpg
Apify run ID: abc123xyz
Total API hits: 47
Social media matches: 8
  [1] Instagram: https://www.instagram.com/p/ABC123/
      match_type=exact_match, title=Alice at the meetup
      content_hash=sha256:e3b0c44298fc1c149afbf4c8996fb...

Results saved to: web_search/results/alice.json
```

---

## 9. Definition of Done

| # | Criterion | How to verify |
|---|-----------|---------------|
| 1 | `pip install` installs `requests` (used for Apify REST calls) | Exit code 0, `python -c "import requests; print(requests.__version__)"` works |
| 2 | Consent check blocks unconsented subject | `--subject fake` raises PermissionError |
| 3 | Consent check passes for consented subject | Runs without PermissionError when consent.txt exists |
| 4 | Real Apify API call is made | Logs show Apify run ID and actual item count |
| 5 | Base64 encoding works | No public URL needed; image sent as `imagesBase64` payload |
| 6 | Social media filtering works | Output JSON contains only allowlisted domains |
| 7 | Best match is ranked, not random | exact_match ranked above web_result |
| 8 | URL accessibility check runs | Log shows real HTTP status code |
| 9 | content_hash is computed | SHA-256 present in output JSON for best_match |
| 10 | Output JSON saved at expected path | `web_search/results/<subject>.json` is valid JSON |
| 11 | No hardcoded URLs in code | `grep` shows no URL string literals in `web_search/*.py` |
| 12 | API failure produces clear error | Invalid/missing token produces clear RuntimeError |
| 13 | `results/*.json` gitignored | `.gitignore` contains the pattern |
| 14 | Constraints block in design document | Present at top of design_phase2.md |

---

## 10. Limitations and Caveats

This stage relies on an **unofficial, community-maintained** Apify actor that
scrapes Google Lens — it is **not** an official Google product. Implications:

- **Results may be inconsistent:** Google Lens results vary by region, timing,
  and Google's own anti-scraping measures. The same image may return different
  results on different runs.
- **Actor could change or break without notice:** The actor maintainer may
  update the input schema, change pricing, or the actor could go offline. This
  is inherent to using community-maintained scraping tools.
- **Cost is per-event:** While free trial credits cover hackathon usage, this is
  not a free API. Repeated runs will eventually consume credits.
- **Data accuracy:** Google Lens results are best-effort. A "no match" result
  does not prove the image doesn't exist online — only that Lens didn't find it.

These caveats are acceptable for a hackathon demo. For production use, a
licensed reverse-image-search API (or direct partnership with a platform) would
be more appropriate.
