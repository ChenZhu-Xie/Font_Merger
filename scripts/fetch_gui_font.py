#!/usr/bin/env python3
"""Download the pinned GUI font and verify it before packaging."""

from __future__ import annotations

import argparse
import hashlib
import http.client
import time
import urllib.request
from pathlib import Path
from typing import BinaryIO, Callable


FONT_VERSION = "v1.3"
FONT_FILENAME = "JetBrainsLxgwNerdMono-Regular.ttf"
FONT_URL = (
    "https://github.com/lvbibir/JetBrainsLxgwNerdMono/releases/download/"
    f"{FONT_VERSION}/{FONT_FILENAME}"
)
FONT_SHA256 = "6e9e3bc2201311c09196f4e2682f496ad772ecd90e48fb4799629df21bc0d5f1"
LICENSE_ASSETS = (
    (
        "Nerd-Fonts-LICENSE.txt",
        "https://raw.githubusercontent.com/ryanoasis/nerd-fonts/v3.4.0/LICENSE",
        "1f6ad4edae6479aaace3112ede5279a23284ae54b2a34db66357aef5f64df160",
    ),
    (
        "Nerd-Fonts-license-audit.md",
        "https://raw.githubusercontent.com/ryanoasis/nerd-fonts/"
        "v3.4.0/license-audit.md",
        "22c490a48e08adcabab0b06d317fe6c6310a420e081d8ebff7f44d0210096cd1",
    ),
    (
        "JetBrains-Mono-OFL.txt",
        "https://raw.githubusercontent.com/JetBrains/JetBrainsMono/v2.304/OFL.txt",
        "30f0c136e3c88e422d0791acd97238870f9054a9729bc34cf2ff0d4ed8cac4ad",
    ),
    (
        "LXGW-WenKai-Screen-OFL.txt",
        "https://raw.githubusercontent.com/lxgw/LxgwWenKai-Screen/v1.521/OFL.txt",
        "4d72e3080cdb3be63638bb7197c7caae55b6e4cbe1bab1ded2830bdff0c9b438",
    ),
)


class AssetChecksumError(RuntimeError):
    pass


def download_verified_asset(
    url: str,
    destination: Path,
    expected_sha256: str,
    *,
    attempts: int = 3,
    open_url: Callable[..., BinaryIO] = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Download and verify an asset, retrying without replacing valid files."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    try:
        for attempt in range(attempts):
            digest = hashlib.sha256()
            try:
                with open_url(url, timeout=120) as response:
                    with temporary.open("wb") as output:
                        while chunk := response.read(1024 * 1024):
                            digest.update(chunk)
                            output.write(chunk)
                actual = digest.hexdigest()
                if actual != expected_sha256:
                    raise AssetChecksumError(
                        f"Asset checksum mismatch: expected {expected_sha256}, "
                        f"got {actual}"
                    )
                temporary.replace(destination)
                return
            except (OSError, http.client.IncompleteRead, AssetChecksumError):
                temporary.unlink(missing_ok=True)
                if attempt + 1 == attempts:
                    raise
                sleep(2**attempt)
    finally:
        temporary.unlink(missing_ok=True)


def fetch_font(destination: Path) -> None:
    download_verified_asset(FONT_URL, destination, FONT_SHA256)


def fetch_release_assets(repo_root: Path) -> None:
    fetch_font(repo_root / "assets" / "fonts" / FONT_FILENAME)
    license_dir = repo_root / "release-licenses"
    for filename, url, sha256 in LICENSE_ASSETS:
        download_verified_asset(url, license_dir / filename, sha256)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "destination",
        nargs="?",
        type=Path,
        default=Path("assets/fonts") / FONT_FILENAME,
    )
    parser.add_argument(
        "--release-assets",
        action="store_true",
        help="download the pinned font and its release license files",
    )
    args = parser.parse_args()
    if args.release_assets:
        fetch_release_assets(Path.cwd())
    else:
        fetch_font(args.destination)


if __name__ == "__main__":
    main()
