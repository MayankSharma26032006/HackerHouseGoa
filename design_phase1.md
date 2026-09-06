# Phase 1: Face Detection & Embedding Extraction

> **This file specifies Phase 1 only. The constraints block below must be
> copy-pasted verbatim to the top of every future phase's `design.md`.**

---

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

---

## 1. Library Choice

**InsightFace** (via `insightface` + `onnxruntime`).

**Justification:**
- Runs fully locally — no API key, no cloud dependency.
- High accuracy face detection (RetinaFace) + 512-d embeddings (ArcFace).
- Single `pip install` — no CMake/dlib build step required.
- Pre-trained models auto-downloaded on first run; once cached, fully offline.
- Well-maintained, widely used in production face verification systems.

**Additional dependency:** `Pillow` for image loading/validation.

---

## 2. Input Contract

### Consent Check (MUST run first, before any processing)

```python
CONSENT_DIR = Path("data/subjects") / subject_name
CONSENT_FILE = CONSENT_DIR / "consent.txt"

if not CONSENT_FILE.exists():
    raise PermissionError(
        f"⛔ Consent check FAILED: {CONSENT_FILE} not found.\n"
        f"Cannot process '{subject_name}' without explicit consent.\n"
        f"See data/CONSENT.md for the required format."
    )
```

This check runs:
- At the top of `process_subject()` — before any image is read.
- Before each image is processed — if consent.txt is deleted mid-run, processing halts.

### Image Discovery

After consent passes, scan `data/subjects/<name>/` for supported formats:
- `.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`
- Skip `.txt` files (consent.txt), hidden files, non-image extensions.
- If zero images found → raise `ValueError` with clear message.

---

## 3. Output Contract

### Per-Image Embedding Storage

Phase 1 stores **all embeddings per-image** — no averaging, ranking, or selection.
Phase 2 will decide how to combine or select from multiple embeddings per subject.

**Location:** `face_id/embeddings/<subject_name>.json`

**Format (JSON):**
```json
{
  "subject": "alice",
  "processed_at": "2026-09-02T14:30:00Z",
  "consent_verified": true,
  "images": [
    {
      "filename": "alice_front.jpg",
      "face_detected": true,
      "bbox": [120, 80, 350, 320],
      "confidence": 0.987,
      "embedding": [0.023, -0.145, 0.087, ..., -0.034],
      "embedding_dim": 512
    }
  ],
  "summary": {
    "total_images": 1,
    "faces_detected": 1,
    "avg_confidence": 0.987
  }
}
```

**Why JSON over `.npy`:**
- Human-readable — reviewer can open the file and see metadata.
- Embeds metadata alongside the vector — no separate index file needed.
- 512-d float32 vector is ~2KB in JSON — trivially small.

---

## 4. Failure Handling

| Failure Mode | Behavior | Exit Code |
|---|---|---|
| **Consent file missing** | `PermissionError` with clear message. Processing halts immediately. | 1 |
| **Subject directory doesn't exist** | `FileNotFoundError` listing expected path. | 1 |
| **Unsupported file format** | Log warning, skip file, continue. | 0 (if at least one image succeeded) |
| **No face detected in image** | Log warning, skip image, continue with others. | 0 (if at least one face found) |
| **Multiple faces detected** | Log warning, use highest-confidence face. | 0 |
| **Low quality / blurry** | If confidence < 0.5: log warning. Include in output but flag it. | 0 |
| **Zero images found** | `ValueError`: "No images found in data/subjects/<name>/". | 1 |
| **ONNX model download fails** | `RuntimeError` with model load failure message. | 1 |

---

## 5. Verifiability Requirement

The script **must print real evidence** it ran on the actual image.

### Required Console Output (per image)

```
[face_id] Processing: data/subjects/alice/alice_front.jpg
[face_id]   Consent verified: data/subjects/alice/consent.txt
[face_id]   Face: bbox=(120, 80, 350, 320), conf=0.987
[face_id]   Embedding (512-d): [0.023, -0.145, 0.087, -0.091, 0.156, ...]
[face_id]   Saved to face_id/embeddings/alice.json
```

### Required Summary Output (at end)

```
[face_id] === SUMMARY ===
[face_id] Subject: alice
[face_id] Images: 3, Faces: 3 (avg conf: 0.964)
[face_id] Skipped: 0
[face_id] Output: face_id/embeddings/alice.json
```

---

## 6. Testability — CLI Entry Point

**Command:** `python -m face_id.run --subject <name>`

**Reviewer can run:**
```bash
# With subject's images in data/subjects/alice/:
python -m face_id.run --subject alice

# Or point at a specific image:
python -m face_id.run --subject alice --images data/subjects/alice/photo.jpg
```

Both must produce the real output described in §5.

---

## 7. Definition of Done — Phase 1

| #  | Criterion | How to verify |
|----|-----------|---------------|
| 1  | `pip install` includes InsightFace | `pip list | grep insightface` shows package |
| 2  | Consent check blocks unconsented subject | `python -m face_id.run --subject nobody` → PermissionError |
| 3  | Consent check passes for consented subject | Place `consent.txt` + one image in `data/subjects/test/`, run → success |
| 4  | Real face detection on actual image | Output shows bbox coordinates and confidence from InsightFace |
| 5  | Embedding vector is 512-d float | JSON contains `"embedding_dim": 512` and array of ~512 floats |
| 6  | Output JSON at expected path | `face_id/embeddings/<subject>.json` exists after run |
| 7  | No-face case handled cleanly | Use image with no face → warning logged, not a crash |
| 8  | Multiple-faces uses highest confidence | Use image with 2+ faces → warning logged, best face used |
| 9  | Unsupported format skipped gracefully | Place `.txt` or `.xyz` in subject dir → skipped with warning |
| 10 | Console shows verifiable evidence | Run produces bbox, confidence, first embedding values on screen |
| 11 | No hardcoded/mock vectors in code | `grep -r "embedding.*=.*\[" face_id/ --include="*.py"` returns no literal arrays |
| 12 | `face_id/embeddings/` gitignored | Embedding files are generated artifacts, not tracked |
| 13 | `design_phase1.md` has constraints block | Ctrl+F finds "Constraints (non-negotiable)" |
