#!/usr/bin/env python3
"""Merge OpenType fonts with deterministic fallback priority.

The first input wins for duplicate Unicode code points. Later inputs only fill
missing characters. TTF, OTF, TTC and OTC inputs are accepted; collection
faces are selected with ``path#INDEX``.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from fontTools.merge import Merger
from fontTools.merge.options import Options as MergeOptions
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.subset import Options as SubsetOptions
from fontTools.subset import Subsetter
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib.instancer import instantiateVariableFont

VERSION = "2.0.0"
LOG = logging.getLogger("font-merger")

COLLECTION_MAGIC = b"ttcf"
COLOR_TABLES = {"COLR", "CPAL", "CBDT", "CBLC", "sbix", "SVG "}
INVALIDATED_TABLES = {"DSIG"}
HINT_TABLES = {"cvt ", "cvar", "fpgm", "prep", "hdmx", "VDMX", "LTSH"}


class FontMergerError(RuntimeError):
    """A user-facing font merge error."""


@dataclass(frozen=True)
class FontSource:
    path: Path
    face_index: int = 0
    face_explicit: bool = False

    @property
    def label(self) -> str:
        suffix = f"#{self.face_index}" if self.face_explicit or is_collection(self.path) else ""
        return f"{self.path}{suffix}"


@dataclass(frozen=True)
class FaceInfo:
    index: int
    family: str
    style: str


def is_collection(path: Path) -> bool:
    """Detect a collection by file signature, not by its extension."""
    try:
        with path.open("rb") as stream:
            return stream.read(4) == COLLECTION_MAGIC
    except OSError as exc:
        raise FontMergerError(f"无法读取字体：{path}: {exc}") from exc


def parse_source(value: str) -> FontSource:
    """Parse PATH or PATH#INDEX while still allowing literal '#' in paths."""
    literal = Path(value).expanduser()
    if literal.is_file():
        return FontSource(literal.resolve())

    match = re.match(r"^(.*)#(\d+)$", value)
    if match:
        path = Path(match.group(1)).expanduser()
        if path.is_file():
            return FontSource(path.resolve(), int(match.group(2)), True)

    raise FontMergerError(f"字体文件不存在：{value}")


def collection_faces(path: Path) -> list[FaceInfo]:
    if not path.is_file():
        raise FontMergerError(f"字体文件不存在：{path}")
    if not is_collection(path):
        with TTFont(path, lazy=True) as font:
            return [FaceInfo(0, best_name(font, "family"), best_name(font, "style"))]

    collection = TTCollection(path, lazy=True)
    try:
        return [
            FaceInfo(index, best_name(font, "family"), best_name(font, "style"))
            for index, font in enumerate(collection.fonts)
        ]
    finally:
        collection.close()


def best_name(font: TTFont, kind: str) -> str:
    name = font["name"] if "name" in font else None
    if name is None:
        return "Unknown"
    if kind == "family":
        return name.getBestFamilyName() or name.getDebugName(1) or "Unknown"
    return name.getBestSubFamilyName() or name.getDebugName(2) or "Regular"


def open_source(source: FontSource) -> TTFont:
    collection = is_collection(source.path)
    if source.face_explicit and not collection and source.face_index != 0:
        raise FontMergerError(f"{source.path} 不是字体集合，不能选择 face #{source.face_index}")

    if collection:
        faces = collection_faces(source.path)
        if source.face_index >= len(faces):
            raise FontMergerError(
                f"{source.path} 只有 {len(faces)} 个 face，无法选择 #{source.face_index}"
            )
        if not source.face_explicit and len(faces) > 1:
            LOG.warning(
                "%s 含 %d 个 face；未指定时使用 #0（%s %s）",
                source.path,
                len(faces),
                faces[0].family,
                faces[0].style,
            )
        font = TTFont(source.path, fontNumber=source.face_index, lazy=False)
    else:
        font = TTFont(source.path, lazy=False)

    font.recalcTimestamp = False
    return font


def parse_axis(values: Iterable[str]) -> dict[str, float]:
    axes: dict[str, float] = {}
    for value in values:
        if "=" not in value:
            raise FontMergerError(f"轴参数应为 TAG=VALUE：{value}")
        tag, number = value.split("=", 1)
        tag = tag.strip()
        if len(tag) != 4:
            raise FontMergerError(f"OpenType 轴标签必须为 4 个字符：{tag}")
        try:
            axes[tag] = float(number)
        except ValueError as exc:
            raise FontMergerError(f"轴坐标不是数字：{value}") from exc
    return axes


def instantiate_if_variable(font: TTFont, requested_axes: dict[str, float]) -> set[str]:
    if "fvar" not in font:
        return set()
    if "CFF2" in font:
        raise FontMergerError("当前 fontTools 不能可靠地静态化 CFF2 可变字体；请先导出静态实例")

    available = {axis.axisTag: axis for axis in font["fvar"].axes}
    used = set(requested_axes).intersection(available)
    limits = {
        tag: requested_axes.get(tag, axis.defaultValue)
        for tag, axis in available.items()
    }
    LOG.info(
        "静态化可变字体：%s",
        ", ".join(f"{tag}={limits[tag]:g}" for tag in sorted(limits)),
    )
    instantiateVariableFont(font, limits, inplace=True, optimize=True)
    return used


def reject_color_font(font: TTFont, label: str) -> None:
    present = sorted(COLOR_TABLES.intersection(font.keys()))
    if present:
        raise FontMergerError(
            f"{label} 是彩色/位图字体（{', '.join(present)}）；"
            "当前版本拒绝生成可能损坏的输出"
        )


def subset_to_unicodes(font: TTFont, unicodes: set[int]) -> None:
    options = SubsetOptions()
    options.drop_tables.extend(["MERG", "meta"])
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recommended_glyphs = True
    options.recalc_timestamp = False
    subsetter = Subsetter(options=options)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(font)


def convert_cff_to_glyf(font: TTFont, max_err: float) -> None:
    if "CFF " not in font and "CFF2" not in font:
        return

    glyph_order = font.getGlyphOrder()
    glyph_set = font.getGlyphSet()
    glyphs = {}
    for glyph_name in glyph_order:
        tt_pen = TTGlyphPen(glyph_set)
        pen = Cu2QuPen(tt_pen, max_err=max_err, reverse_direction=True)
        glyph_set[glyph_name].draw(pen)
        glyphs[glyph_name] = tt_pen.glyph()

    glyf = newTable("glyf")
    glyf.glyphOrder = glyph_order
    glyf.glyphs = glyphs
    font["glyf"] = glyf
    font["loca"] = newTable("loca")

    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    for field, value in {
        "maxPoints": 0,
        "maxContours": 0,
        "maxCompositePoints": 0,
        "maxCompositeContours": 0,
        "maxZones": 1,
        "maxTwilightPoints": 0,
        "maxStorage": 0,
        "maxFunctionDefs": 0,
        "maxInstructionDefs": 0,
        "maxStackElements": 0,
        "maxSizeOfInstructions": 0,
        "maxComponentElements": 0,
        "maxComponentDepth": 0,
    }.items():
        setattr(maxp, field, value)

    for tag in ("CFF ", "CFF2", "VORG"):
        if tag in font:
            del font[tag]
    font.sfntVersion = "\x00\x01\x00\x00"


def remove_hinting(font: TTFont) -> None:
    if "glyf" in font:
        font["glyf"].removeHinting()
    for tag in HINT_TABLES:
        if tag in font:
            del font[tag]
    if "maxp" in font and font["maxp"].tableVersion == 0x00010000:
        for field in (
            "maxTwilightPoints",
            "maxStorage",
            "maxFunctionDefs",
            "maxInstructionDefs",
            "maxStackElements",
            "maxSizeOfInstructions",
        ):
            setattr(font["maxp"], field, 0)
        font["maxp"].maxZones = 1


def normalize_upm(font: TTFont, target_upm: int) -> None:
    current = font["head"].unitsPerEm
    if current == target_upm:
        return
    LOG.info("缩放 UPM：%d -> %d（并移除已失效的 TrueType hinting）", current, target_upm)
    scale_upem(font, target_upm)
    remove_hinting(font)


def ensure_vertical_metrics(font: TTFont) -> None:
    """Add neutral vertical metrics when a font lacks them.

    fontTools cannot merge a native vhea/vmtx table with a missing table.  A
    synthesized entry keeps native CJK vertical metrics intact instead of
    solving the mismatch by deleting vertical-layout support from every font.
    """
    has_vhea = "vhea" in font
    has_vmtx = "vmtx" in font
    if has_vhea and has_vmtx:
        return
    if has_vhea != has_vmtx:
        # A half-present pair is invalid and cannot be trusted.
        if "vhea" in font:
            del font["vhea"]
        if "vmtx" in font:
            del font["vmtx"]

    upm = font["head"].unitsPerEm
    vhea = newTable("vhea")
    vhea.tableVersion = 0x00010000
    vhea.ascent = font["hhea"].ascent
    vhea.descent = font["hhea"].descent
    vhea.lineGap = font["hhea"].lineGap
    vhea.advanceHeightMax = upm
    vhea.minTopSideBearing = 0
    vhea.minBottomSideBearing = 0
    vhea.yMaxExtent = upm
    vhea.caretSlopeRise = 0
    vhea.caretSlopeRun = 1
    vhea.caretOffset = 0
    vhea.reserved1 = 0
    vhea.reserved2 = 0
    vhea.reserved3 = 0
    vhea.reserved4 = 0
    vhea.metricDataFormat = 0
    vhea.numberOfVMetrics = len(font.getGlyphOrder())

    vmtx = newTable("vmtx")
    metrics: dict[str, tuple[int, int]] = {}
    glyf = font["glyf"]
    for glyph_name in font.getGlyphOrder():
        glyph = glyf[glyph_name]
        glyph.recalcBounds(glyf)
        height = glyph.yMax - glyph.yMin if hasattr(glyph, "yMax") else 0
        metrics[glyph_name] = (upm, round((upm - height) / 2))
    vmtx.metrics = metrics
    font["vhea"] = vhea
    font["vmtx"] = vmtx


def strip_invalidated_tables(font: TTFont) -> None:
    for tag in INVALIDATED_TABLES:
        if tag in font:
            del font[tag]


def postscript_name(family: str, style: str) -> str:
    value = f"{family}-{style}".replace(" ", "")
    value = re.sub(r"[^A-Za-z0-9._-]", "", value)
    return (value or "MergedFont-Regular")[:63]


def set_font_names(font: TTFont, family: str, style: str) -> None:
    if "name" not in font:
        return
    name = font["name"]
    full = family if style.casefold() == "regular" else f"{family} {style}"
    ps_name = postscript_name(family, style)
    unique = f"{VERSION};{ps_name}"
    values = {1: family, 2: style, 3: unique, 4: full, 6: ps_name, 16: family, 17: style}

    for name_id, value in values.items():
        name.removeNames(nameID=name_id)
        name.setName(value, name_id, 3, 1, 0x409)
        name.setName(value, name_id, 0, 4, 0)
        try:
            value.encode("mac_roman")
        except UnicodeEncodeError:
            continue
        name.setName(value, name_id, 1, 0, 0)


def refresh_metadata(font: TTFont) -> None:
    cmap = font.getBestCmap() or {}
    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.recalcUnicodeRanges(font)
        if os2.version >= 1:
            os2.recalcCodePageRanges(font)
        os2.recalcAvgCharWidth(font)
        bmp = [codepoint for codepoint in cmap if codepoint <= 0xFFFF]
        if bmp:
            os2.usFirstCharIndex = min(bmp)
            os2.usLastCharIndex = max(bmp)


def default_family(fonts: Sequence[tuple[str, str]]) -> str:
    families: list[str] = []
    for family, _style in fonts:
        if family not in families:
            families.append(family)
    return " + ".join(families)


def _save_prepared(font: TTFont, path: Path) -> None:
    font.recalcBBoxes = True
    font.recalcTimestamp = False
    font.save(path, reorderTables=False)
    font.close()


def validate_output(path: Path, expected_unicodes: set[int], target_upm: int) -> tuple[int, int]:
    with TTFont(path, lazy=False) as font:
        actual = set((font.getBestCmap() or {}).keys())
        missing = expected_unicodes - actual
        if missing:
            examples = ", ".join(f"U+{cp:04X}" for cp in sorted(missing)[:10])
            raise FontMergerError(f"输出自检失败：缺少 {len(missing)} 个字符（{examples}）")
        if font["head"].unitsPerEm != target_upm:
            raise FontMergerError("输出自检失败：UPM 不一致")
        if "fvar" in font:
            raise FontMergerError("输出自检失败：仍含未处理的可变字体表")
        return len(actual), len(font.getGlyphOrder())


def merge_fonts(
    sources: Sequence[FontSource],
    output: Path,
    family: str | None = None,
    style: str | None = None,
    axes: dict[str, float] | None = None,
    curve_error: float = 1.0,
) -> tuple[int, int]:
    if len(sources) < 2:
        raise FontMergerError("至少需要两个输入字体")
    if curve_error <= 0:
        raise FontMergerError("--curve-error 必须大于 0")

    axes = axes or {}
    used_axes: set[str] = set()
    claimed: set[int] = set()
    expected: set[int] = set()
    names: list[tuple[str, str]] = []
    target_upm: int | None = None

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="font-merger-") as temp_name:
        temp_dir = Path(temp_name)
        prepared_paths: list[Path] = []

        for index, source in enumerate(sources):
            LOG.info("读取 [%d/%d] %s", index + 1, len(sources), source.label)
            font = open_source(source)
            try:
                reject_color_font(font, source.label)
                names.append((best_name(font, "family"), best_name(font, "style")))
                used_axes.update(instantiate_if_variable(font, axes))

                cmap = font.getBestCmap() or {}
                available = set(cmap)
                selected = available if index == 0 else available - claimed
                expected.update(selected)
                claimed.update(available)

                if index > 0:
                    if not selected:
                        LOG.info("跳过 %s：没有可补充的 Unicode 字符", source.label)
                        font.close()
                        continue
                    LOG.info("采用 %d 个新字符，忽略 %d 个已由前序字体提供的字符", len(selected), len(available) - len(selected))
                    subset_to_unicodes(font, selected)

                if target_upm is None:
                    target_upm = font["head"].unitsPerEm
                if "CFF " in font or "CFF2" in font:
                    LOG.info("将 PostScript 三次曲线轮廓转换为 TrueType 二次曲线")
                    convert_cff_to_glyf(font, curve_error)
                normalize_upm(font, target_upm)
                ensure_vertical_metrics(font)
                strip_invalidated_tables(font)

                prepared = temp_dir / f"input-{len(prepared_paths):03d}.ttf"
                _save_prepared(font, prepared)
                prepared_paths.append(prepared)
            except Exception:
                font.close()
                raise

        unknown_axes = set(axes) - used_axes
        if unknown_axes:
            raise FontMergerError(f"输入字体均不包含这些轴：{', '.join(sorted(unknown_axes))}")
        if len(prepared_paths) < 2:
            raise FontMergerError("除首字体外，没有输入字体能补充新字符")
        assert target_upm is not None

        LOG.info("合并 %d 个字体（前者优先）", len(prepared_paths))
        options = MergeOptions(drop_tables=list(INVALIDATED_TABLES))
        merged = Merger(options=options).merge([str(path) for path in prepared_paths])
        merged.recalcTimestamp = False
        merged.recalcBBoxes = True

        chosen_family = family or default_family(names)
        chosen_style = style or names[0][1]
        set_font_names(merged, chosen_family, chosen_style)
        refresh_metadata(merged)

        temporary_output = output.with_name(f".{output.name}.font-merger.tmp")
        try:
            merged.save(temporary_output, reorderTables=False)
            merged.close()
            counts = validate_output(temporary_output, expected, target_upm)
            os.replace(temporary_output, output)
        finally:
            merged.close()
            if temporary_output.exists():
                temporary_output.unlink()

    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="font-merger",
        description="按输入顺序合并 TTF/OTF/TTC/OTC；相同字符由前面的字体提供。",
    )
    parser.add_argument("fonts", nargs="*", metavar="FONT", help="字体路径；集合 face 写作 'path.ttc#0'")
    parser.add_argument("-o", "--output", type=Path, default=Path("merged.ttf"), help="输出 TTF（默认 merged.ttf）")
    parser.add_argument("--family", help="输出字体家族名")
    parser.add_argument("--style", help="输出样式名；默认沿用第一个字体")
    parser.add_argument("--axis", action="append", default=[], metavar="TAG=VALUE", help="可变字体轴坐标，可重复")
    parser.add_argument("--curve-error", type=float, default=1.0, metavar="UNITS", help="OTF 曲线转换最大误差（默认 1.0）")
    parser.add_argument("--list", dest="list_font", type=Path, metavar="FONT", help="列出 TTC/OTC 中的 face 后退出")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示 fontTools 详细日志")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="[%(levelname)s] %(message)s",
    )
    LOG.setLevel(logging.INFO)
    if not args.verbose:
        logging.getLogger("fontTools").setLevel(logging.ERROR)

    try:
        if args.list_font:
            for face in collection_faces(args.list_font.expanduser().resolve()):
                print(f"#{face.index}\t{face.family}\t{face.style}")
            return 0
        if not args.fonts:
            parser.print_help()
            return 0

        sources = [parse_source(value) for value in args.fonts]
        axes = parse_axis(args.axis)
        characters, glyphs = merge_fonts(
            sources,
            args.output,
            family=args.family,
            style=args.style,
            axes=axes,
            curve_error=args.curve_error,
        )
        print(f"完成：{args.output.resolve()}（{characters} 个 Unicode 字符，{glyphs} 个 glyph）")
        return 0
    except FontMergerError as exc:
        parser.error(str(exc))
    except Exception as exc:
        if args.verbose:
            raise
        parser.error(f"合并失败：{exc}（使用 -v 查看详细信息）")
    return 2


if __name__ == "__main__":
    sys.exit(main())
