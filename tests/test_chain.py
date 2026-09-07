"""tests/test_chain.py - Pure-function tests for fingerprinting, gas math, calldata decode.

These tests verify the core deterministic logic without network calls,
blockchain connections, or external services. Run with: pytest tests/
"""

import hashlib
import json

import pytest

from chain.fingerprint import compute_record_hash
from chain.upload import intrinsic_gas, recommended_gas_limit
from chain.verify import decode_calldata


# ---------------------------------------------------------------------------
# Phase 3: Fingerprinting
# ---------------------------------------------------------------------------

class TestComputeRecordHash:
    """Tests for the deterministic fingerprint hashing function."""

    def test_deterministic_same_inputs(self):
        """Same inputs always produce the same record_hash."""
        canonical = {
            "content_hash": "sha256:abc123",
            "image_file": "photo.jpg",
            "matched_url": "https://example.com/post/1",
            "platform": "Twitter/X",
            "subject": "alice",
        }
        h1 = compute_record_hash(canonical)
        h2 = compute_record_hash(canonical)
        assert h1 == h2
        assert h1.startswith("sha256:")
        assert len(h1) == 71  # "sha256:" (7) + 64 hex chars

    def test_different_inputs_different_hash(self):
        """Changing any field changes the hash."""
        base = {
            "content_hash": "sha256:abc123",
            "image_file": "photo.jpg",
            "matched_url": "https://example.com/post/1",
            "platform": "Twitter/X",
            "subject": "alice",
        }
        h_base = compute_record_hash(base)

        # Change each field one at a time
        for field in base:
            modified = base.copy()
            modified[field] = modified[field] + "_changed"
            h_mod = compute_record_hash(modified)
            assert h_mod != h_base, f"Changing '{field}' did not change the hash"

    def test_key_order_irrelevant(self):
        """JSON key order doesn't affect the hash (sort_keys=True)."""
        canonical_v1 = {
            "subject": "alice",
            "image_file": "photo.jpg",
            "matched_url": "https://example.com/post/1",
            "content_hash": "sha256:abc123",
            "platform": "Twitter/X",
        }
        # Reverse the key order
        canonical_v2 = dict(reversed(canonical_v1.items()))
        assert compute_record_hash(canonical_v1) == compute_record_hash(canonical_v2)

    def test_known_hash_value(self):
        """Verify a known hash against manual SHA-256 computation."""
        canonical = {
            "content_hash": None,
            "image_file": "test.png",
            "matched_url": "https://example.com",
            "platform": "LinkedIn",
            "subject": "test_user",
        }
        record_hash = compute_record_hash(canonical)

        # Manually compute expected hash
        canonical_bytes = json.dumps(
            canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        expected = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()

        assert record_hash == expected


# ---------------------------------------------------------------------------
# Phase 4: Gas calculation
# ---------------------------------------------------------------------------

class TestIntrinsicGas:
    """Tests for EIP-2028 intrinsic gas calculation."""

    def test_empty_calldata(self):
        """Empty calldata costs exactly 21000 (base tx cost)."""
        assert intrinsic_gas("") == 21000

    def test_record_hash_gas(self):
        """A typical record_hash (~71 bytes) costs 21000 + 71*16 = 22136."""
        record_hash = "sha256:1e1b246b8e6248f1189d427d1ec7a3955ca56ee3ae959783d0c4fa5512f5c597"
        assert len(record_hash) == 71
        assert intrinsic_gas(record_hash) == 22136

    def test_all_zero_bytes(self):
        """Zero bytes cost 4 gas each (EIP-2028)."""
        # 10 zero bytes + 21000 base = 21040
        data = "\x00" * 10
        assert intrinsic_gas(data) == 21000 + 10 * 4

    def test_mixed_bytes(self):
        """Mixed non-zero and zero bytes use correct per-byte costs."""
        # 6 non-zero (16 gas each) + 3 zero (4 gas each) + 21000
        data = "abc\x00\x00\x00def"
        assert intrinsic_gas(data) == 21000 + 6 * 16 + 3 * 4

    def test_recommended_gas_limit_has_safety_margin(self):
        """recommended_gas_limit = 1.5x intrinsic gas."""
        record_hash = "sha256:1e1b246b8e6248f1189d427d1ec7a3955ca56ee3ae959783d0c4fa5512f5c597"
        intrinsic = intrinsic_gas(record_hash)  # 22136
        recommended = recommended_gas_limit(record_hash)
        assert recommended == intrinsic + intrinsic // 2  # 33204
        assert recommended > intrinsic


# ---------------------------------------------------------------------------
# Phase 5: Calldata decode
# ---------------------------------------------------------------------------

class TestDecodeCalldata:
    """Tests for transaction calldata decoding."""

    def test_roundtrip_string(self):
        """Encode a string to hex calldata, decode it back — must match."""
        original = "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        calldata_hex = original.encode("utf-8").hex()
        # Simulate what get_transaction returns (with 0x prefix)
        tx = {"input": bytes.fromhex(calldata_hex)}
        decoded, err = decode_calldata(tx)
        assert err is None
        assert decoded == original

    def test_roundtrip_with_0x_prefix_string(self):
        """Decode calldata that arrives as a 0x-prefixed hex string."""
        original = "sha256:abc123"
        calldata_hex = "0x" + original.encode("utf-8").hex()
        tx = {"input": calldata_hex}
        decoded, err = decode_calldata(tx)
        assert err is None
        assert decoded == original

    def test_empty_calldata(self):
        """Empty calldata returns None with an error message."""
        tx = {"input": "0x"}
        decoded, err = decode_calldata(tx)
        assert decoded is None
        assert "empty" in err

    def test_missing_calldata(self):
        """Missing input field returns None with an error message."""
        tx = {}
        decoded, err = decode_calldata(tx)
        assert decoded is None
        assert "no calldata" in err

    def test_non_utf8_calldata(self):
        """Non-UTF-8 bytes return None with an error message."""
        tx = {"input": bytes.fromhex("ffff")}
        decoded, err = decode_calldata(tx)
        assert decoded is None
        assert "not UTF-8" in err
