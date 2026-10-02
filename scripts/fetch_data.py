"""Fetch the dataset and prove it is the right one.

The two CSVs are a CC0 (public domain) Kaggle download and are deliberately
not committed to this repository. That means a fresh clone has no data and
the app cannot start, which is exactly the gap this script closes.

It downloads the files from this project's GitHub Release, verifies each one
against the checksum recorded in backend/dataset.py, and refuses to leave a
file that does not match behind.

    python scripts/fetch_data.py             # download anything missing
    python scripts/fetch_data.py --check     # verify only, download nothing
    python scripts/fetch_data.py --force     # re-download even if present

Source: https://www.kaggle.com/datasets/chaitu20/ipl-dataset2008-2025
Licence: CC0 / public domain, so redistribution is permitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "backend"))

import dataset  # noqa: E402  (sys.path must be set first)

REPOSITORY = "Aadarsh2807/IPL-Tactical-Intelligence"
API_LATEST = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
KAGGLE = "https://www.kaggle.com/datasets/chaitu20/ipl-dataset2008-2025"

_ASSET_URLS: dict[str, str] | None = None


def release_assets() -> dict[str, str]:
    """Map each dataset filename to its download URL on the latest release.

    Assets are resolved by name through the API rather than by guessing a
    tag, so retagging or renaming the release cannot break this. Set
    IPL_DATA_URL to point at any mirror serving the same two filenames.
    """
    global _ASSET_URLS
    if _ASSET_URLS is not None:
        return _ASSET_URLS

    override = os.environ.get("IPL_DATA_URL")
    if override:
        base = override.rstrip("/")
        _ASSET_URLS = {name: f"{base}/{name}"
                       for name in dataset.DATASET_FINGERPRINTS}
        return _ASSET_URLS

    request = urllib.request.Request(
        API_LATEST,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "ipl-fetch-data"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.load(response)
        available = {asset["name"]: asset["browser_download_url"]
                     for asset in release.get("assets", [])}
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        available = {}

    missing = [name for name in dataset.DATASET_FINGERPRINTS if name not in available]
    if missing:
        raise SystemExit(
            f"\nThe latest release of {REPOSITORY} is missing {len(missing)} "
            f"required file(s): {', '.join(missing)}\n"
            f"  Attach them at https://github.com/{REPOSITORY}/releases\n"
            f"  or download them from Kaggle and save them into "
            f"{dataset.data_dir()}\n  {KAGGLE}"
        )

    _ASSET_URLS = {name: available[name] for name in dataset.DATASET_FINGERPRINTS}
    return _ASSET_URLS


def md5_of(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    print(f"     downloading {target.name}")
    request = urllib.request.Request(url, headers={"User-Agent": "ipl-fetch-data"})
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            with temporary.open("wb") as handle:
                while chunk := response.read(1 << 20):
                    handle.write(chunk)
    except urllib.error.HTTPError as error:
        temporary.unlink(missing_ok=True)
        raise SystemExit(
            f"\nCould not download {target.name} (HTTP {error.code}) from\n  {url}\n"
            f"Get the two CSVs from Kaggle instead:\n  {KAGGLE}\n"
            f"and save them into {dataset.data_dir()}"
        ) from error
    temporary.replace(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the checksums without downloading")
    parser.add_argument("--force", action="store_true",
                        help="re-download even if the file is already correct")
    args = parser.parse_args()

    directory = dataset.data_dir()
    directory.mkdir(parents=True, exist_ok=True)

    print(f"Dataset -> {directory}")
    print(f"Source  -> {os.environ.get('IPL_DATA_URL') or API_LATEST}\n")

    assets = release_assets()
    failures = 0

    for filename, expected in dataset.DATASET_FINGERPRINTS.items():
        target = directory / filename
        exists = target.is_file()
        actual = md5_of(target) if exists else None

        if exists and actual == expected and not args.force:
            print(f"[ok] {filename} already present and matches")
            continue

        if args.check:
            print(f"[!!] {filename} "
                  f"{'does not match its checksum' if exists else 'is missing'}")
            failures += 1
            continue

        if not exists or args.force:
            download(assets[filename], target)
            actual = md5_of(target)

        if actual == expected:
            print(f"[ok] {filename} downloaded and verified")
        else:
            print(f"[!!] {filename} checksum mismatch\n"
                  f"     expected {expected}\n"
                  f"     got      {actual}\n"
                  f"     This is not the dataset the documented row counts and\n"
                  f"     quirks describe. Delete it and fetch again.")
            failures += 1

    print()
    if failures:
        print(f"NOT READY: {failures} file(s) did not verify.")
        return 1
    print("READY. Next: python scripts/preflight.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
