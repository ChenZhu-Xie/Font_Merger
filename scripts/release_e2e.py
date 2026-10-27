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
from fontTools.misc.psCharStrings import T2CharString
from fontTools.misc.roundTools import otRound
from fontTools.otlLib.builder import buildMathTable
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable


def rectangle_glyph(width: int, height: int):
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((width - 50, 0))
    pen.lineTo((width - 50, height))
    pen.lineTo((50, height))
    pen.closePath()
    return pen.glyph()


def rectangle_charstring(width: int, height: int, *, cff2: bool = False):
    pen = T2CharStringPen(None if cff2 else width, None, CFF2=cff2)
    pen.moveTo((50, 0))
    pen.lineTo((width - 50, 0))
    pen.lineTo((width - 50, height))
    pen.lineTo((50, height))
    pen.closePath()
    return pen.getCharString()


def build_font(
    path: Path,
    *,
    family: str,
    upm: int,
    glyph_widths: dict[str, int],
    cmap: dict[int, str],
    is_ttf: bool = True,
    vertical_metrics: dict[str, tuple[int, int]] | None = None,
    vorg_default: int | None = None,
    vorg_records: dict[str, int] | None = None,
    cff2_variable: bool = False,
) -> TTFont:
    glyph_order = list(glyph_widths)
    builder = FontBuilder(upm, isTTF=is_ttf)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(cmap)
    builder.setupNameTable(
        {
            "familyName": family,
            "styleName": "Regular",
            "uniqueFontIdentifier": f"ReleaseE2E-{family}",
            "fullName": f"{family} Regular",
            "psName": family.replace(" ", "") + "-Regular",
        }
    )
    if is_ttf:
        builder.setupGlyf(
            {
                glyph_name: rectangle_glyph(max(width, 200), otRound(upm * 0.7))
                for glyph_name, width in glyph_widths.items()
            }
        )
    elif cff2_variable:
        builder.setupFvar(
            [("wght", 100, 400, 900, "Weight")],
            [
                {"location": {"wght": 400}, "stylename": "Regular"},
                {"location": {"wght": 900}, "stylename": "Black"},
            ],
        )
        charstrings = {
            glyph_name: rectangle_charstring(
                max(width, 200), otRound(upm * 0.7), cff2=True
            )
            for glyph_name, width in glyph_widths.items()
        }
        charstrings["A"] = T2CharString(
            program=[
                200,
                100,
                -100,
                0,
                2,
                "blend",
                "rmoveto",
                400,
                200,
                1,
                "blend",
                "hlineto",
                500,
                0,
                1,
                "blend",
                "vlineto",
                -400,
                -200,
                1,
                "blend",
                "hlineto",
            ]
        )
        builder.setupCFF2(charstrings, regions=[{"wght": (0, 1, 1)}])
    else:
        builder.setupCFF(
            family.replace(" ", "") + "-Regular",
            {"FullName": f"{family} Regular"},
            {
                glyph_name: rectangle_charstring(
                    max(width, 200), otRound(upm * 0.7)
                )
                for glyph_name, width in glyph_widths.items()
            },
            {},
        )
    builder.setupHorizontalMetrics(
        {glyph_name: (width, 0) for glyph_name, width in glyph_widths.items()}
    )
    builder.setupHorizontalHeader(
        ascent=otRound(upm * 0.8), descent=-otRound(upm * 0.2)
    )
    if vertical_metrics is not None:
        builder.setupVerticalMetrics(vertical_metrics)
        builder.setupVerticalHeader(
            ascent=otRound(upm / 2), descent=-otRound(upm / 2)
        )
    builder.setupOS2(
        sTypoAscender=otRound(upm * 0.8),
        sTypoDescender=-otRound(upm * 0.2),
        usWinAscent=otRound(upm * 0.8),
        usWinDescent=otRound(upm * 0.2),
    )
    builder.setupPost()
    builder.setupMaxp()
    if vorg_default is not None:
        vorg = newTable("VORG")
        vorg.majorVersion = 1
        vorg.minorVersion = 0
        vorg.defaultVertOriginY = vorg_default
        vorg.VOriginRecords = dict(vorg_records or {})
        builder.font["VORG"] = vorg
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
    latin_path = work_dir / "e2e-latin-cff2-vf.otf"
    cjk_path = work_dir / "e2e-cjk-math-uvs.otf"

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
        is_ttf=False,
        cff2_variable=True,
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
        glyph_widths={
            ".notdef": 1024,
            "han": 2048,
            "han.alt": 1500,
            "han.vert": 2048,
        },
        cmap={0x0041: "han", 0x4E00: "han"},
        is_ttf=False,
        vertical_metrics={
            ".notdef": (2048, 360),
            "han": (2048, 360),
            "han.alt": (2048, 360),
            "han.vert": (2048, 400),
        },
        vorg_default=1800,
        vorg_records={"han.vert": 1850},
    )
    add_uvs(
        cjk,
        [
            (0x0041, 0xFE00, "han.alt"),
            (0x0041, 0xFE01, None),
        ],
    )
    addOpenTypeFeaturesFromString(
        cjk,
        """
        languagesystem DFLT dflt;
        languagesystem hani dflt;
        feature vert { sub han by han.vert; } vert;
        feature vrt2 { sub han by han.vert; } vrt2;
        """,
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


def parse_diagnostics(
    output: str, *, expected_frozen: bool = True
) -> dict[str, str]:
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
    expected = str(expected_frozen).lower()
    if diagnostics["frozen"] != expected:
        raise AssertionError(
            f"merge command reported frozen={diagnostics['frozen']}; "
            f"expected {expected}"
        )
    return diagnostics


def read_uvs(font: TTFont) -> dict[tuple[int, int], str | None]:
    mappings = {}
    for table in font["cmap"].tables:
        if table.format == 14:
            for selector, entries in table.uvsDict.items():
                for base, glyph_name in entries:
                    mappings[(base, selector)] = glyph_name
    return mappings


def single_substitution(font: TTFont, feature_tag: str, glyph_name: str) -> str:
    feature_list = font["GSUB"].table.FeatureList.FeatureRecord
    lookup_list = font["GSUB"].table.LookupList.Lookup
    for feature_record in feature_list:
        if feature_record.FeatureTag != feature_tag:
            continue
        for lookup_index in feature_record.Feature.LookupListIndex:
            for subtable in lookup_list[lookup_index].SubTable:
                if glyph_name in subtable.mapping:
                    return subtable.mapping[glyph_name]
    raise AssertionError(f"missing {feature_tag} substitution for {glyph_name}")


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
        if "CFF2" in font or "CFF " in font:
            raise AssertionError("output retained PostScript outlines")
        latin_a = font["glyf"][cmap[0x0041]]
        latin_a.recalcBounds(font["glyf"])
        if (latin_a.xMin, latin_a.yMin, latin_a.xMax, latin_a.yMax) != (
            100,
            100,
            700,
            600,
        ):
            raise AssertionError("CFF2 custom-axis outline was not selected")
        if "MATH" not in font:
            raise AssertionError("output lost the MATH table")
        math = font["MATH"].table
        if math.MathConstants.AxisHeight.Value != otRound(256 * 1000 / 2048):
            raise AssertionError("MATH constants were not scaled with the UPM")
        han = cmap[0x4E00]
        if han not in math.MathGlyphInfo.ExtendedShapeCoverage.glyphs:
            raise AssertionError("MATH glyph coverage was not preserved")
        if "CFF " in font or "VORG" in font:
            raise AssertionError("CFF/VORG input was not fully converted to glyf/vmtx")
        vertical = single_substitution(font, "vert", han)
        if single_substitution(font, "vrt2", han) != vertical:
            raise AssertionError("vert and vrt2 substitutions disagree")
        glyf = font["glyf"]
        expected_origins = {
            han: otRound(1800 * 1000 / 2048),
            vertical: otRound(1850 * 1000 / 2048),
        }
        for glyph_name, expected_origin in expected_origins.items():
            glyph = glyf[glyph_name]
            glyph.recalcBounds(glyf)
            actual_origin = glyph.yMax + font["vmtx"][glyph_name][1]
            if actual_origin != expected_origin:
                raise AssertionError(
                    f"vertical origin changed for {glyph_name}: "
                    f"expected {expected_origin}, got {actual_origin}"
                )
            if font["vmtx"][glyph_name][0] != 1000:
                raise AssertionError("vertical advance was not scaled with the UPM")


def _run_command(
    command_prefix: list[str], work_dir: Path, *, expected_frozen: bool
) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    latin, cjk = create_inputs(work_dir)
    output = work_dir / "e2e-merged.ttf"

    diagnostics_result = run_and_record(
        [*command_prefix, "--diagnostics"], work_dir / "diagnostics.log"
    )
    diagnostics = parse_diagnostics(
        diagnostics_result.stdout, expected_frozen=expected_frozen
    )

    merge_result = run_and_record(
        [
            *command_prefix,
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
            "--axis",
            "wght=900",
            "--experimental-cff2-staticize",
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
        "merge command end-to-end validation passed\n"
        f"font_merger={diagnostics['font_merger']}\n"
        f"fonttools={diagnostics['fonttools']}\n"
        f"frozen={diagnostics['frozen']}\n",
        encoding="utf-8",
    )


def run(executable: Path, work_dir: Path) -> None:
    executable = resolve_executable(executable)
    _run_command([str(executable)], work_dir, expected_frozen=True)


def run_source(source_script: Path, work_dir: Path) -> None:
    source_script = source_script.expanduser().resolve()
    if not source_script.is_file():
        raise FileNotFoundError(f"Font_Merger source script not found: {source_script}")
    _run_command(
        [sys.executable, str(source_script)], work_dir, expected_frozen=False
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--executable", type=Path)
    command.add_argument("--source-script", type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.executable is not None:
            run(args.executable, args.work_dir.expanduser().resolve())
        else:
            run_source(args.source_script, args.work_dir.expanduser().resolve())
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
