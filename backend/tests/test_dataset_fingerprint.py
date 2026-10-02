"""Prove the dataset is pinned by content, not by hope.

The two CSVs are a Kaggle download and are not committed, so the only thing
tying a published figure to a specific set of rows is the checksum recorded
in `dataset.DATASET_FINGERPRINTS`. These tests check that the real files
match, and — just as important — that a tampered file is actually caught
rather than the check passing vacuously.
"""
from __future__ import annotations

import dataset


def test_the_real_dataset_matches_its_recorded_fingerprints():
    results = dataset.verify_fingerprints()
    assert results, "expected a result for each dataset file"
    mismatched = [r for r in results if not r["matches"]]
    assert not mismatched, (
        "dataset does not match the checksums in docs/DATA.md: "
        + "; ".join(f"{r['file']}: expected {r['expected']}, got {r['actual']}"
                    for r in mismatched)
    )


def test_every_recorded_fingerprint_is_a_plausible_md5():
    for filename, digest in dataset.DATASET_FINGERPRINTS.items():
        assert len(digest) == 32, f"{filename}: not an MD5 digest"
        assert all(char in "0123456789abcdef" for char in digest), \
            f"{filename}: digest is not lowercase hex"


def test_a_tampered_file_is_detected(tmp_path, monkeypatch):
    """A check that cannot fail is worse than no check."""
    monkeypatch.setenv("IPL_DATA_DIR", str(tmp_path))

    for filename in dataset.DATASET_FINGERPRINTS:
        (tmp_path / filename).write_text("corrupted\n", encoding="utf-8")

    results = dataset.verify_fingerprints()
    assert results
    assert all(not result["matches"] for result in results), \
        "a corrupted dataset was not detected"
    assert all(result["actual"] != result["expected"] for result in results)


def test_a_missing_file_is_reported_rather_than_crashing(tmp_path, monkeypatch):
    monkeypatch.setenv("IPL_DATA_DIR", str(tmp_path))
    results = dataset.verify_fingerprints()
    assert results
    assert all(not result["matches"] for result in results)
    assert all(result["actual"] is None for result in results)
    assert all("not found" in result["detail"] for result in results)


def test_the_md5_helper_agrees_with_hashlib(tmp_path):
    path = tmp_path / "sample.bin"
    payload = b"ipl" * 50_000
    path.write_bytes(payload)

    import hashlib
    assert dataset.file_md5(path) == hashlib.md5(payload).hexdigest()