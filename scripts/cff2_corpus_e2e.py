#!/usr/bin/env python3
"""Validate experimental CFF2 staticization against a pinned Adobe VF."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import traceback
import urllib.request
from pathlib import Path

from fontTools.ttLib import TTFont

if __package__:
    from scripts.font_qa import find_tool, run_external
    from scripts.release_e2e import build_font, run_and_record
else:
    from font_qa import find_tool, run_external
    from release_e2e import build_font, run_and_record


SOURCE_SERIF_URL = (
    "https://raw.githubusercontent.com/adobe-fonts/source-serif/"
    "80d3f8894c09c937bebfa9011247d2e1c79fd6f4/"
    "VAR/SourceSerif4Variable-Roman.otf"
)
SOURCE_SERIF_SHA256 = (
    "867b73c6a954a4a64616906d179f94572a748790a1d022ebeeff07f56ea0221a"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_verified(url: str, destination: Path, expected_sha256: str) -> Path:
    """Download atomically and accept only the pinned SHA-256 payload."""
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = expected_sha256.casefold()
    if destination.is_file() and _sha256(destination) == expected:
        return destination

    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "Font-Merger-CFF2-Corpus/1"}
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            with partial.open("wb") as output:
                shutil.copyfileobj(response, output)
        actual = _sha256(partial)
        if actual != expected:
            raise ValueError(
                f"CFF2 corpus SHA-256 mismatch: expected {expected}, got {actual}"
            )
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    return destination


def validate_cff2_source(path: Path) -> dict[str, tuple[float, float, float]]:
    """Require a genuine CFF2 variable font and return its axis ranges."""
    with TTFont(path, lazy=False) as font:
        if "CFF2" not in font or "fvar" not in font:
            raise AssertionError("CFF2 corpus source must contain CFF2 and fvar")
        axes = {
            axis.axisTag: (
                float(axis.minValue),
                float(axis.defaultValue),
                float(axis.maxValue),
            )
            for axis in font["fvar"].axes
        }
        if "wght" not in axes:
            raise AssertionError("CFF2 corpus source must expose a wght axis")
        if 0x0041 not in (font.getBestCmap() or {}):
            raise AssertionError("CFF2 corpus source must contain U+0041")
        return axes


def validate_static_output(path: Path) -> None:
    """Check the corpus merge has become a usable static glyf font."""
    with TTFont(path, lazy=False) as font:
        if "glyf" not in font:
            raise AssertionError("CFF2 corpus output has no glyf table")
        unexpected = {"CFF2", "CFF ", "fvar"}.intersection(font.keys())
        if unexpected:
            raise AssertionError(
                f"CFF2 corpus output retained staticization tables: {sorted(unexpected)}"
            )
        cmap = font.getBestCmap() or {}
        if not {0x0041, 0x4E00}.issubset(cmap):
            raise AssertionError("CFF2 corpus output lost source or companion coverage")
        glyph = font["glyf"][cmap[0x0041]]
        glyph.recalcBounds(font["glyf"])
        if not hasattr(glyph, "xMin") or glyph.xMin == glyph.xMax:
            raise AssertionError("CFF2 corpus output has an empty U+0041 outline")
        if font["OS/2"].usWeightClass != 700:
            raise AssertionError("CFF2 corpus output did not retain wght=700 metadata")


def _build_companion(path: Path) -> None:
    font = build_font(
        path,
        family="CFF2 Corpus Companion",
        upm=1000,
        glyph_widths={".notdef": 500, "han": 1000},
        cmap={0x4E00: "han"},
    )
    font.close()


def _run_external_qa(output: Path, work_dir: Path) -> None:
    ots = find_tool("ots-sanitize")
    hb_shape = find_tool("hb-shape")
    run_external(
        [ots, str(output), str(work_dir / "ots-sanitized.ttf")],
        work_dir / "ots.log",
    )
    shaped = run_external(
        [hb_shape, "--output-format=json", str(output), "office"],
        work_dir / "harfbuzz.log",
    )
    payload = json.loads(shaped.stdout)
    if not isinstance(payload, list) or not payload:
        raise AssertionError("HarfBuzz returned no glyphs for CFF2 corpus output")
    glyphs = [item.get("g") for item in payload if isinstance(item, dict)]
    if len(glyphs) != len(payload) or any(
        glyph in {".notdef", "gid0"} for glyph in glyphs
    ):
        raise AssertionError(f"HarfBuzz returned missing glyphs: {glyphs}")


def run_corpus(
    source_script: Path,
    work_dir: Path,
    *,
    source_url: str = SOURCE_SERIF_URL,
    source_sha256: str = SOURCE_SERIF_SHA256,
    external_qa: bool = True,
) -> Path:
    """Download, merge, and validate the pinned CFF2 corpus font."""
    source_script = source_script.expanduser().resolve()
    work_dir = work_dir.expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    source = download_verified(
        source_url, work_dir / "SourceSerif4Variable-Roman.otf", source_sha256
    )
    axes = validate_cff2_source(source)
    companion = work_dir / "companion.ttf"
    output = work_dir / "cff2-corpus-merged.ttf"
    _build_companion(companion)

    command = [
        sys.executable,
        str(source_script),
        str(source),
        str(companion),
        "--experimental-cff2-staticize",
        "--axis",
        "wght=700",
    ]
    if "opsz" in axes:
        command.extend(["--axis", "opsz=20"])
    command.extend(
        [
            "--style",
            "Bold",
            "--priority",
            "input",
            "--hinting-source",
            "none",
            "--output",
            str(output),
        ]
    )
    run_and_record(command, work_dir / "merge.log")
    validate_static_output(output)
    if external_qa:
        _run_external_qa(output, work_dir)
    (work_dir / "report.txt").write_text(
        "CFF2 corpus validation passed\n"
        f"source_url={source_url}\n"
        f"source_sha256={source_sha256}\n"
        f"axes={','.join(sorted(axes))}\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-script",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "Font_Merger.py",
    )
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = run_corpus(args.source_script, args.work_dir)
    except Exception:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        failure = traceback.format_exc()
        (args.work_dir / "failure.txt").write_text(failure, encoding="utf-8")
        print(failure, file=sys.stderr)
        return 1
    print(f"CFF2 corpus validation passed: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
