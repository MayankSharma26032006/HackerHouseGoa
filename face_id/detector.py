"""face_id.detector - Consent-checked face detection + embedding extraction."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

logger = logging.getLogger("face_id")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECTS_DIR = PROJECT_ROOT / "data" / "subjects"
EMBEDDINGS_DIR = PROJECT_ROOT / "face_id" / "embeddings"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

_model = None


def _get_model():
    global _model
    if _model is None:
        try:
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise RuntimeError("InsightFace not installed. Run: pip install insightface onnxruntime") from exc
        logger.info("[face_id] Loading InsightFace model...")
        try:
            _model = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
            _model.prepare(ctx_id=0, det_size=(640, 640))
        except Exception as exc:
            raise RuntimeError("Failed to load InsightFace model: " + str(exc)) from exc
        logger.info("[face_id] Model loaded.")
    return _model


def verify_consent(subject_name):
    subject_dir = SUBJECTS_DIR / subject_name
    if not subject_dir.exists():
        avail = [d.name for d in SUBJECTS_DIR.iterdir() if d.is_dir()] if SUBJECTS_DIR.exists() else []
        raise FileNotFoundError("Subject not found: " + str(subject_dir) + chr(10) + "Available: " + str(avail))
    consent_file = subject_dir / "consent.txt"
    if not consent_file.exists():
        raise PermissionError("Consent FAILED: " + str(consent_file) + " not found." + chr(10) + "Cannot process without consent. See data/CONSENT.md")
    logger.info("[face_id]   Consent verified: " + str(consent_file))
    return consent_file


def discover_images(subject_name):
    subject_dir = SUBJECTS_DIR / subject_name
    images = sorted(p for p in subject_dir.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith("."))
    if not images:
        all_files = [f.name for f in subject_dir.iterdir() if f.is_file()]
        raise ValueError("No images in " + str(subject_dir) + ". Files: " + str(all_files))
    return images


def detect_and_embed(image_path):
    try:
        img = Image.open(image_path)
        img.verify()
        img = Image.open(image_path)
    except Exception as exc:
        raise ValueError("Cannot open " + str(image_path) + ": " + str(exc)) from exc
    img_array = np.array(img)
    if img_array.ndim == 2:
        img_array = np.stack([img_array] * 3, axis=-1)
    elif img_array.shape[2] == 4:
        img_array = img_array[:, :, :3]
    model = _get_model()
    faces = model.get(img_array)
    if not faces:
        raise ValueError("No face in " + image_path.name)
    if len(faces) > 1:
        best_idx = int(np.argmax([f.det_score for f in faces]))
        logger.warning("[face_id]   Multiple faces (" + str(len(faces)) + "), using best")
        face = faces[best_idx]
    else:
        face = faces[0]
    confidence = float(face.det_score)
    bbox = face.bbox.astype(int).tolist()
    embedding = face.normed_embedding.tolist()
    result = {"filename": image_path.name, "face_detected": True, "bbox": bbox,
              "confidence": round(confidence, 6), "embedding": embedding, "embedding_dim": len(embedding)}
    logger.info("[face_id]   Face: bbox=" + str(tuple(bbox)) + ", conf=" + str(round(confidence, 3)))
    preview = ", ".join(str(round(v, 3)) for v in embedding[:5])
    logger.info("[face_id]   Embedding (512-d): [" + preview + ", ...]")
    return result


def process_subject(subject_name, specific_images=None):
    verify_consent(subject_name)
    if specific_images:
        images = [Path(p) for p in specific_images]
        for p in images:
            if not p.exists():
                raise FileNotFoundError("Not found: " + str(p))
    else:
        images = discover_images(subject_name)
    logger.info("[face_id] Processing " + str(len(images)) + " image(s)...")
    results = []
    skipped_no_face = []
    for img_path in images:
        logger.info("[face_id] Processing: " + str(img_path))
        verify_consent(subject_name)
        try:
            face_data = detect_and_embed(img_path)
            results.append(face_data)
        except ValueError as exc:
            skipped_no_face.append(img_path.name)
            logger.warning("[face_id]   Skipped " + img_path.name + ": " + str(exc))
    output = {"subject": subject_name, "processed_at": datetime.now(timezone.utc).isoformat(),
              "consent_verified": True, "images": results,
              "summary": {"total_images": len(images), "faces_detected": len(results),
                           "avg_confidence": round(sum(r["confidence"] for r in results) / len(results), 6) if results else 0,
                           "skipped_no_face": skipped_no_face}}
    output_path = EMBEDDINGS_DIR / (subject_name + ".json")
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    logger.info("[face_id]   Saved to " + str(output_path))
    avg_conf = output["summary"]["avg_confidence"]
    logger.info("[face_id] === SUMMARY ===")
    logger.info("[face_id] Subject: " + subject_name)
    logger.info("[face_id] Images: " + str(len(images)) + ", Faces: " + str(len(results)) + " (avg conf: " + str(round(avg_conf, 3)) + ")")
    logger.info("[face_id] Skipped: " + str(len(skipped_no_face)))
    logger.info("[face_id] Output: " + str(output_path))
    return output
