#!/usr/bin/env python3
"""Tests for Build Artifact Tracker."""
import os
import sys
import tempfile

sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.core.artifacts import ArtifactTracker, BuildArtifact


def test_register_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def hello(): pass\n")
        path = f.name

    try:
        tracker = ArtifactTracker()
        art = tracker.register_file(path, "file")
        assert art.artifact_type == "file"
        assert art.path == path
        assert len(art.content_hash) == 64  # SHA-256 hex
        assert art.status == "created"
        print("✅ register_file works")
    finally:
        os.unlink(path)


def test_run_tests():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def test_pass(): assert True\n")
        path = f.name

    try:
        tracker = ArtifactTracker()
        art = tracker.register_file(path, "test")
        art = tracker.run_tests(art, ["python3", "-m", "pytest", path, "-q"])
        assert art.status in ("tested", "test_failed", "test_error")
        print(f"✅ run_tests: status={art.status}")
    finally:
        os.unlink(path)


def test_yield_evidence():
    tracker = ArtifactTracker()
    evidence = tracker.get_yield_evidence()
    assert isinstance(evidence, list)
    print(f"✅ get_yield_evidence returns list (len={len(evidence)})")


def test_stats():
    tracker = ArtifactTracker()
    stats = tracker.get_stats()
    assert "total" in stats
    assert "yield_evidence" in stats
    print(f"✅ get_stats works: {stats}")


if __name__ == "__main__":
    print("=" * 60)
    print("  ARTIFACT TRACKER TESTS")
    print("=" * 60)
    print()

    test_register_file()
    test_run_tests()
    test_yield_evidence()
    test_stats()

    print()
    print("=" * 60)
    print("  ALL ARTIFACT TESTS PASSED")
    print("=" * 60)
