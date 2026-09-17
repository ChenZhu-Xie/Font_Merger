#!/usr/bin/env python3
"""Remove bundled icon glyphs that the Font Merger GUI does not use."""

from __future__ import annotations

import argparse
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont


NERD_SYMBOL_RANGES = (
    (0xE000, 0xF8FF),
    (0xF0000, 0xFFFFD),
    (0x100000, 0x10FFFD),
    (0x23FB, 0x23FE),
    (0x2665, 0x2665),
    (0x26A1, 0x26A1),
    (0x276C, 0x276D),
    (0x2B58, 0x2B58),
)
LICENSE_SUMMARY = (
    "This derivative font contains text glyphs from JetBrains Mono and LXGW "
    "WenKai under the SIL Open Font License 1.1. Nerd Fonts symbol glyphs were "
    "removed before redistribution."
)


def is_nerd_symbol_codepoint(codepoint: int) -> bool:
    return any(start <= codepoint <= end for start, end in NERD_SYMBOL_RANGES)


def _set_license_metadata(font: TTFont) -> None:
    name = font["name"]
    for platform_id, encoding_id, language_id in (
        (3, 1, 0x409),
        (1, 0, 0),
    ):
        name.setName(LICENSE_SUMMARY, 13, platform_id, encoding_id, language_id)
        name.setName(
            "https://openfontlicense.org",
            14,
            platform_id,
            encoding_id,
            language_id,
        )


def prepare_gui_font(path: Path) -> int:
    """Strip Nerd Font icon ranges while preserving all ordinary text glyphs."""
    temporary = path.with_suffix(path.suffix + ".prepared")
    try:
        with TTFont(path) as font:
            cmap = font.getBestCmap()
            kept = {
                codepoint
                for codepoint in cmap
                if not is_nerd_symbol_codepoint(codepoint)
            }
            removed = len(cmap) - len(kept)

            options = subset.Options()
            options.name_IDs = ["*"]
            options.name_legacy = True
            options.name_languages = ["*"]
            options.layout_features = ["*"]
            options.notdef_glyph = True
            options.notdef_outline = True
            subsetter = subset.Subsetter(options=options)
            subsetter.populate(unicodes=kept)
            subsetter.subset(font)
            _set_license_metadata(font)
            font.save(temporary)

        with TTFont(temporary, lazy=True) as prepared:
            remaining = prepared.getBestCmap()
            if any(is_nerd_symbol_codepoint(codepoint) for codepoint in remaining):
                raise RuntimeError(
                    "Prepared GUI font still contains Nerd symbol ranges"
                )
        temporary.replace(path)
        return removed
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "font",
        nargs="?",
        type=Path,
        default=Path("assets/fonts/JetBrainsLxgwNerdMono-Regular.ttf"),
    )
    path = parser.parse_args().font
    print(f"Removed {prepare_gui_font(path)} bundled symbol glyphs from {path}")


if __name__ == "__main__":
    main()
