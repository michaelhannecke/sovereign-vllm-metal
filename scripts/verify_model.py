#!/usr/bin/env python3
"""
verify_model.py
Verify local model files against CHECKSUMS.sha256 in the model directory.
Checks file existence, sizes, and SHA256 hashes.

Usage:
    python verify_model.py ~/models/llama-3.2-3b
    python verify_model.py ~/models/gpt-oss-20b
"""

import os
import sys
import hashlib


def sha256_file(filepath: str, chunk_size: int = 1024 * 1024) -> str:
    """SHA256 hash of a file. Uses 1MB chunks for speed on large files."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def verify_checksums(model_dir: str) -> bool:
    """Verify all files against CHECKSUMS.sha256 in the model directory."""
    checksum_file = os.path.join(model_dir, "CHECKSUMS.sha256")

    if not os.path.exists(checksum_file):
        print(f"  No CHECKSUMS.sha256 found in {model_dir}")
        print(f"  Generate one first:")
        print(f"  cd {model_dir}")
        print(f"  find . -type f \\( -name '*.safetensors' -o -name '*.json' \\) "
              f"-exec shasum -a 256 {{}} \\; | sort > CHECKSUMS.sha256")
        return False

    passed = 0
    failed = 0
    missing = 0

    with open(checksum_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split("  ", 1)
            if len(parts) != 2:
                continue

            expected_hash, filepath = parts
            full_path = os.path.realpath(os.path.join(model_dir, filepath))

            if not full_path.startswith(os.path.realpath(model_dir) + os.sep):
                print(f"  SKIPPED  : {filepath} (path escapes model directory)")
                failed += 1
                continue

            if not os.path.exists(full_path):
                print(f"  MISSING  : {filepath}")
                missing += 1
                continue

            print(f"  Checking : {filepath}...", end="", flush=True)
            actual_hash = sha256_file(full_path)

            if actual_hash == expected_hash:
                file_size = os.path.getsize(full_path)
                print(f" OK ({file_size / (1024**3):.2f} GB)")
                passed += 1
            else:
                print(f" FAILED!")
                print(f"    Expected : {expected_hash}")
                print(f"    Got      : {actual_hash}")
                failed += 1

    print()
    print(f"  Passed: {passed}  Failed: {failed}  Missing: {missing}")
    return failed == 0 and missing == 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_model.py <model_dir>")
        print("  e.g.: python verify_model.py ~/models/llama-3.2-3b")
        sys.exit(1)

    model_dir = os.path.expanduser(sys.argv[1])

    if not os.path.isdir(model_dir):
        print(f"Not found: {model_dir}")
        sys.exit(1)

    total_size = sum(
        os.path.getsize(os.path.join(r, f))
        for r, _, files in os.walk(model_dir)
        for f in files
    )

    print()
    print(f"  Model directory : {model_dir}")
    print(f"  Total size      : {total_size / (1024**3):.2f} GB")
    print()

    ok = verify_checksums(model_dir)

    if ok:
        print("  All files verified. Safe to serve.")
    else:
        print("  Verification FAILED. Do NOT serve this model.")
        print("     Re-download and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
