#!/usr/bin/env python3
"""
Example: File Corpus Mining

Scans a directory and estimates yield from file content.
Yield estimates are scenario projections, not guaranteed returns.

Usage:
    python3 examples/mine_files.py ~/Documents --max 30
"""
import argparse
import os
import sys

sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.core.yield_engine import YieldEngine


def main():
    parser = argparse.ArgumentParser(description="Mine files for yield estimates")
    parser.add_argument("path", help="Directory to scan")
    parser.add_argument("--max", type=int, default=30, help="Max files to analyze")
    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"Path not found: {args.path}")
        return 1

    print("=" * 60)
    print("  MEMBRA FILE MINER")
    print("  Yield estimates = scenario projections, NOT guaranteed returns")
    print("=" * 60)
    print()

    engine = YieldEngine()
    results = []
    count = 0

    for root, _, files in os.walk(args.path):
        for fname in files:
            if count >= args.max:
                break
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", errors="ignore") as f:
                    content = f.read()[:2000]
                y = engine.estimate(fpath, content)
                results.append((fpath, y))
                count += 1
            except Exception:
                pass

    for fpath, y in sorted(results, key=lambda x: x[1], reverse=True)[:20]:
        print(f"  {y:.6f}  {fpath[-50:]}")

    print()
    print(f"  Scanned: {count} files")
    print(f"  Total yield estimate: {sum(y for _, y in results):.4f}")
    print()
    print("  See docs/PROOF_OF_YIELD.md for what yield means.")


if __name__ == "__main__":
    sys.exit(main())
