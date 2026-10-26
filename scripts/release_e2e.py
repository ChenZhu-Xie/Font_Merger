#!/usr/bin/env python3
"""Exercise a packaged Font_Merger executable with synthetic MATH and UVS fonts."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import traceback
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.roundTools import otRound
from fontTools.otlLib.builder import buildMathTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable


def rectangle_glyph(width: int, height: int):
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((width - 50, 0))
    pen.lineTo((width - 50, height))
    pen.lineTo((50, height))
    pen.closePath()
    return pen.glyph()


def build_font(
    path: Path,
    *,
    family: str,
    upm: int,
    glyph_widths: dict[str, int],
    cmap: dict[int, str],
) -> TTFont:
    glyph_order = list(glyph_widths)
    builder = FontBuilder(upm, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(cmap)
    builder.setupGlyf(
        {
            glyph_name: rectangle_glyph(max(width, 200), otRound(upm * 0.7))
            for glyph_name, width in glyph_widths.items()
        }
    )
    builder.setupHorizontalMetrics(
        {glyph_name: (width, 0) for glyph_name, width in glyph_widths.items()}
    )
    builder.setupHorizontalHeader(
        ascent=otRound(upm * 0.8), descent=-otRound(upm * 0.2)
    )
    builder.setupOS2(
        sTypoAscender=otRound(upm * 0.8),
        sTypoDescender=-otRound(upm * 0.2),
        usWinAscent=otRound(upm * 0.8),
        usWinDescent=otRound(upm * 0.2),
    )
    builder.setupNameTable(
        {
            "familyName": family,
            "styleName": "Regular",
            "uniqueFontIdentifier": f"ReleaseE2E-{family}",
            "fullName": f"{family} Regular",
            "psName": family.replace(" ", "") + "-Regular",
        }
    )
    builder.setupPost()
    builder.setupMaxp()
    builder.font.save(path)
    return builder.font


def add_uvs(font: TTFont, entries: list[tuple[int, int, str | None]]) -> None:
    by_selector: dict[int, list[tuple[int, str | None]]] = {}
    for base, selector, glyph_name in entries:
        by_selector.setdefault(selector, []).append((base, glyph_name))
    table = CmapSubtable.newSubtable(14)
    table.platformID = 0
    table.platEncID = 5
    table.language = 0
    table.cmap = {}
    table.uvsDict = by_selector
    font["cmap"].tables.append(table)


def create_inputs(work_dir: Path) -> tuple[Path, Path]:
    latin_path = work_dir / "e2e-latin.ttf"
    cjk_path = work_dir / "e2e-cjk-math-uvs.ttf"

    latin = build_font(
        latin_path,
        family="Release E2E Latin",
        upm=1000,
        glyph_widths={
            ".notdef": 500,
            "A": 600,
            "f": 400,
            "i": 300,
            "f_i": 650,
            "acutecomb": 0,
            "beh": 600,
            "beh.init": 600,
            "beh.medi": 600,
            "beh.fina": 600,
            "ka": 600,
            "virama": 0,
            "ssa": 600,
            "kssa": 700,
        },
        cmap={
            0x0041: "A",
            0x0066: "f",
            0x0069: "i",
            0x0301: "acutecomb",
            0x0628: "beh",
            0x0915: "ka",
            0x0937: "ssa",
            0x094D: "virama",
        },
    )
    addOpenTypeFeaturesFromString(
        latin,
        """
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        languagesystem arab dflt;
        languagesystem deva dflt;

        markClass acutecomb <anchor 100 500> @TOP_MARKS;

        feature liga {
            script latn;
            sub f i by f_i;
        } liga;

        feature mark {
            script latn;
            pos base A <anchor 300 700> mark @TOP_MARKS;
        } mark;

        feature init {
            script arab;
            sub beh by beh.init;
        } init;

        feature medi {
            script arab;
            sub beh by beh.medi;
        } medi;

        feature fina {
            script arab;
            sub beh by beh.fina;
        } fina;

        feature rlig {
            script deva;
            sub ka virama ssa by kssa;
        } rlig;
        """,
    )
    latin.save(latin_path)
    latin.close()

    cjk = build_font(
        cjk_path,
        family="Release E2E CJK",
        upm=2048,
        glyph_widths={".notdef": 1024, "han": 2048, "han.alt": 1500},
        cmap={0x0041: "han", 0x4E00: "han"},
    )
    add_uvs(
        cjk,
        [
            (0x0041, 0xFE00, "han.alt"),
            (0x0041, 0xFE01, None),
        ],
    )
    buildMathTable(
        cjk,
        constants={"AxisHeight": 256},
        topAccentAttachments={"han": 1024},
        extendedShapes={"han"},
        minConnectorOverlap=100,
        vertGlyphVariants={"han": [("han", 2048)]},
    )
    cjk.save(cjk_path)
    cjk.close()
    return latin_path, cjk_path


def resolve_executable(value: Path) -> Path:
    candidate = value.expanduser().resolve()
    if candidate.is_file():
        return candidate
    if os.name == "nt" and candidate.suffix.casefold() != ".exe":
        windows_candidate = candidate.with_suffix(".exe")
        if windows_candidate.is_file():
            return windows_candidate
    raise FileNotFoundError(f"packaged executable not found: {candidate}")


def run_and_record(
    command: list[str], log_path: Path
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
    )
    log_path.write_text(
        "command: "
        + subprocess.list2cmdline(command)
        + f"\nexit_code: {result.returncode}\n\nstdout:\n{result.stdout}"
        + f"\nstderr:\n{result.stderr}",
        encoding="utf-8",
    )
    if result.returncode:
        print(log_path.read_text(encoding="utf-8"), file=sys.stderr)
        raise RuntimeError(
            f"command exited with {result.returncode}; see {log_path.name}"
        )
    return result


def parse_diagnostics(output: str) -> dict[str, str]:
    diagnostics = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            diagnostics[key] = value
    required = {
        "font_merger",
        "python",
        "python_implementation",
        "fonttools",
        "platform",
        "machine",
        "pointer_bits",
        "frozen",
    }
    missing = required - set(diagnostics)
    if missing:
        raise AssertionError(f"diagnostics missing keys: {sorted(missing)}")
    if diagnostics["frozen"] != "true":
        raise AssertionError("packaged executable did not report frozen=true")
    return diagnostics


def read_uvs(font: TTFont) -> dict[tuple[int, int], str | None]:
    mappings = {}
    for table in font["cmap"].tables:
        if table.format == 14:
            for selector, entries in table.uvsDict.items():
                for base, glyph_name in entries:
                    mappings[(base, selector)] = glyph_name
    return mappings


def validate_output(path: Path) -> None:
    with TTFont(path, lazy=False) as font:
        cmap = font.getBestCmap() or {}
        if not {0x0041, 0x4E00}.issubset(cmap):
            raise AssertionError("output scalar cmap coverage is incomplete")
        mappings = read_uvs(font)
        expected_sequences = {(0x0041, 0xFE00), (0x0041, 0xFE01)}
        if set(mappings) != expected_sequences:
            raise AssertionError(f"unexpected UVS mappings: {mappings}")
        alternate = mappings[(0x0041, 0xFE00)]
        if alternate is None:
            raise AssertionError("non-default UVS lost its alternate glyph")
        if mappings[(0x0041, 0xFE01)] is not None:
            raise AssertionError("default UVS became non-default")
        expected_width = otRound(1500 * 1000 / 2048)
        if font["hmtx"][alternate][0] != expected_width:
            raise AssertionError("non-default UVS points to the wrong glyph")
        if font["head"].unitsPerEm != 1000:
            raise AssertionError("output UPM was not normalized to the first font")
        if "fvar" in font:
            raise AssertionError("output unexpectedly remains variable")
        if "MATH" not in font:
            raise AssertionError("output lost the MATH table")
        math = font["MATH"].table
        if math.MathConstants.AxisHeight.Value != otRound(256 * 1000 / 2048):
            raise AssertionError("MATH constants were not scaled with the UPM")
        han = cmap[0x4E00]
        if han not in math.MathGlyphInfo.ExtendedShapeCoverage.glyphs:
            raise AssertionError("MATH glyph coverage was not preserved")


def run(executable: Path, work_dir: Path) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    executable = resolve_executable(executable)
    latin, cjk = create_inputs(work_dir)
    output = work_dir / "e2e-merged.ttf"

    diagnostics_result = run_and_record(
        [str(executable), "--diagnostics"], work_dir / "diagnostics.log"
    )
    diagnostics = parse_diagnostics(diagnostics_result.stdout)

    merge_result = run_and_record(
        [
            str(executable),
            str(latin),
            str(cjk),
            "--priority",
            "input",
            "--hinting-source",
            "1",
            "--family",
            "Release E2E Merged",
            "--style",
            "Regular",
            "--table-policy",
            "strict",
            "--output",
            str(output),
        ],
        work_dir / "merge.log",
    )
    if "表处理摘要：" not in merge_result.stderr:
        raise AssertionError("packaged merge did not report the table policy summary")
    validate_output(output)
    (work_dir / "success.txt").write_text(
        "release executable end-to-end validation passed\n"
        f"font_merger={diagnostics['font_merger']}\n"
        f"fonttools={diagnostics['fonttools']}\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.executable, args.work_dir.expanduser().resolve())
    except Exception:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        failure = traceback.format_exc()
        (args.work_dir / "failure.txt").write_text(failure, encoding="utf-8")
        print(failure, file=sys.stderr)
        return 1
    print(f"Release E2E passed; report: {args.work_dir / 'success.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
