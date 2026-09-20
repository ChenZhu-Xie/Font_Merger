#!/usr/bin/env python3
"""Merge OpenType font families with independent glyph, hinting and weight rules.

TTF, OTF, TTC and OTC inputs are accepted; collection faces are selected with
``path#INDEX``. Clear Latin/CJK pairs use the Latin source for duplicate code
points by default, independent of input order.
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

VERSION = "2.3.1"
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
        suffix = (
            f"#{self.face_index}"
            if self.face_explicit or is_collection(self.path)
            else ""
        )
        return f"{self.path}{suffix}"


@dataclass(frozen=True)
class FaceInfo:
    index: int
    family: str
    style: str
    axes: tuple["AxisInfo", ...] = ()
    instances: tuple["InstanceInfo", ...] = ()


@dataclass(frozen=True)
class AxisInfo:
    tag: str
    name: str
    minimum: float
    default: float
    maximum: float


@dataclass(frozen=True)
class InstanceInfo:
    name: str
    coordinates: tuple[tuple[str, float], ...]

    @property
    def coordinate_map(self) -> dict[str, float]:
        return dict(self.coordinates)


@dataclass(frozen=True)
class SourceInfo:
    source: FontSource
    family: str
    style: str
    unicodes: frozenset[int]
    upm: int
    variable: bool
    axes: tuple[AxisInfo, ...]
    instances: tuple[InstanceInfo, ...]
    weight: int


@dataclass(frozen=True)
class StyleMetadata:
    weight: int
    width: int
    fs_selection: int
    mac_style: int
    italic_angle: float


@dataclass(frozen=True)
class MergeResult:
    path: Path
    style: str
    weight: int
    characters: int
    glyphs: int


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
            axes, instances = variable_details(font)
            return [
                FaceInfo(
                    0,
                    best_name(font, "family"),
                    best_name(font, "style"),
                    axes,
                    instances,
                )
            ]

    collection = TTCollection(path, lazy=True)
    try:
        faces = []
        for index, font in enumerate(collection.fonts):
            axes, instances = variable_details(font)
            faces.append(
                FaceInfo(
                    index,
                    best_name(font, "family"),
                    best_name(font, "style"),
                    axes,
                    instances,
                )
            )
        return faces
    finally:
        collection.close()


def best_name(font: TTFont, kind: str) -> str:
    name = font["name"] if "name" in font else None
    if name is None:
        return "Unknown"
    if kind == "family":
        return name.getDebugName(16) or name.getDebugName(1) or "Unknown"
    return name.getDebugName(17) or name.getDebugName(2) or "Regular"


def variable_details(
    font: TTFont,
) -> tuple[tuple[AxisInfo, ...], tuple[InstanceInfo, ...]]:
    if "fvar" not in font:
        return (), ()
    name = font["name"]
    axes = tuple(
        AxisInfo(
            axis.axisTag,
            name.getDebugName(axis.axisNameID) or axis.axisTag,
            float(axis.minValue),
            float(axis.defaultValue),
            float(axis.maxValue),
        )
        for axis in font["fvar"].axes
    )
    instances = tuple(
        InstanceInfo(
            name.getDebugName(instance.subfamilyNameID) or f"Instance {index + 1}",
            tuple((tag, float(value)) for tag, value in instance.coordinates.items()),
        )
        for index, instance in enumerate(font["fvar"].instances)
    )
    return axes, instances


def open_source(source: FontSource) -> TTFont:
    collection = is_collection(source.path)
    if source.face_explicit and not collection and source.face_index != 0:
        raise FontMergerError(
            f"{source.path} 不是字体集合，不能选择 face #{source.face_index}"
        )

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


def inspect_source(source: FontSource) -> SourceInfo:
    font = open_source(source)
    try:
        axes, instances = variable_details(font)
        weight = (
            int(font["OS/2"].usWeightClass)
            if "OS/2" in font
            else style_weight(best_name(font, "style")) or 400
        )
        return SourceInfo(
            source,
            best_name(font, "family"),
            best_name(font, "style"),
            frozenset((font.getBestCmap() or {}).keys()),
            font["head"].unitsPerEm,
            "fvar" in font,
            axes,
            instances,
            weight,
        )
    finally:
        font.close()


def cjk_character_count(unicodes: Iterable[int]) -> int:
    ranges = (
        (0x1100, 0x11FF),
        (0x2E80, 0x33FF),
        (0x3400, 0x4DBF),
        (0x4E00, 0x9FFF),
        (0xAC00, 0xD7AF),
        (0xF900, 0xFAFF),
        (0x20000, 0x323AF),
    )
    return sum(
        any(start <= codepoint <= end for start, end in ranges)
        for codepoint in unicodes
    )


def detect_latin_cjk_pair(infos: Sequence[SourceInfo]) -> tuple[int, int] | None:
    if len(infos) != 2:
        return None
    cjk_counts = [cjk_character_count(info.unicodes) for info in infos]
    cjk_index = 0 if cjk_counts[0] > cjk_counts[1] else 1
    latin_index = 1 - cjk_index
    ascii_letters = set(range(ord("A"), ord("Z") + 1)) | set(
        range(ord("a"), ord("z") + 1)
    )
    if (
        cjk_counts[cjk_index] >= 256
        and cjk_counts[latin_index] <= 16
        and ascii_letters.issubset(infos[latin_index].unicodes)
    ):
        return latin_index, cjk_index
    return None


def resolve_priority(
    value: str,
    infos: Sequence[SourceInfo],
    pair: tuple[int, int] | None,
) -> list[int]:
    normalized = value.strip().casefold()
    if normalized == "auto":
        if pair is not None:
            latin, cjk = pair
            LOG.info(
                "检测到西文 + CJK：%s 覆盖重叠字符，%s 补充其余字符",
                infos[latin].family,
                infos[cjk].family,
            )
            return [latin, cjk]
        LOG.info("未检测到明确的西文 + CJK 双字体组合，按输入顺序处理")
        return list(range(len(infos)))
    if normalized == "input":
        return list(range(len(infos)))
    try:
        order = [int(item.strip()) - 1 for item in value.split(",")]
    except ValueError as exc:
        raise FontMergerError(
            "--priority 应为 auto、input 或 1,2,3 形式的字体序号"
        ) from exc
    if len(order) != len(infos) or set(order) != set(range(len(infos))):
        raise FontMergerError("--priority 必须恰好包含每个输入字体的序号一次")
    return order


def resolve_hinting_source(
    value: str,
    infos: Sequence[SourceInfo],
    priority: Sequence[int],
    pair: tuple[int, int] | None,
) -> int | None:
    normalized = value.strip().casefold()
    if normalized == "none":
        return None
    if normalized == "auto":
        return pair[1] if pair is not None else priority[0]
    if normalized == "first":
        return priority[0]
    if normalized == "last":
        return priority[-1]
    if normalized in {"latin", "western"}:
        if pair is None:
            raise FontMergerError(
                "无法可靠识别西文字体；请用 --hinting-source N 指定输入序号"
            )
        return pair[0]
    if normalized in {"cjk", "chinese"}:
        if pair is None:
            raise FontMergerError(
                "无法可靠识别 CJK 字体；请用 --hinting-source N 指定输入序号"
            )
        return pair[1]
    try:
        index = int(value) - 1
    except ValueError as exc:
        raise FontMergerError(
            "--hinting-source 应为 auto、latin、cjk、none 或输入字体序号"
        ) from exc
    if index not in range(len(infos)):
        raise FontMergerError(f"--hinting-source 字体序号应在 1 到 {len(infos)} 之间")
    return index


STYLE_WEIGHTS = {
    "thin": 100,
    "hairline": 100,
    "extralight": 200,
    "ultralight": 200,
    "light": 300,
    "demilight": 350,
    "semilight": 350,
    "regular": 400,
    "normal": 400,
    "book": 400,
    "medium": 500,
    "semibold": 600,
    "demibold": 600,
    "bold": 700,
    "extrabold": 800,
    "ultrabold": 800,
    "black": 900,
    "heavy": 900,
}


def normalized_style(value: str) -> str:
    return (
        re.sub(r"[^a-z0-9]", "", value.casefold())
        .replace("italic", "")
        .replace("oblique", "")
        or "regular"
    )


def style_weight(value: str) -> int | None:
    return STYLE_WEIGHTS.get(normalized_style(value))


def style_for_weight(weight: float) -> str:
    choices = (
        (100, "Thin"),
        (200, "ExtraLight"),
        (300, "Light"),
        (350, "DemiLight"),
        (400, "Regular"),
        (500, "Medium"),
        (600, "SemiBold"),
        (700, "Bold"),
        (800, "ExtraBold"),
        (900, "Black"),
    )
    return min(choices, key=lambda item: abs(item[0] - weight))[1]


def find_instance(info: SourceInfo, name: str) -> InstanceInfo | None:
    wanted = re.sub(r"[^a-z0-9]", "", name.casefold())
    for instance in info.instances:
        if re.sub(r"[^a-z0-9]", "", instance.name.casefold()) == wanted:
            return instance
    weight = style_weight(name)
    if weight is not None:
        for instance in info.instances:
            if instance.coordinate_map.get("wght") == weight:
                return instance
    return None


def weight_axis(info: SourceInfo) -> AxisInfo | None:
    return next((axis for axis in info.axes if axis.tag == "wght"), None)


def available_weights(info: SourceInfo) -> tuple[int, ...]:
    """Return useful output-weight anchors exposed by one input face."""
    weights = {
        int(round(instance.coordinate_map["wght"]))
        for instance in info.instances
        if "wght" in instance.coordinate_map
    }
    axis = weight_axis(info)
    if axis is not None:
        weights.add(int(round(axis.default)))
    if not weights:
        weights.add(info.weight)
    return tuple(sorted(weights))


def matched_weight(info: SourceInfo, target: int) -> tuple[int, int]:
    """Return the realizable weight and its distance from the target."""
    axis = weight_axis(info)
    if axis is not None:
        value = int(round(min(max(target, axis.minimum), axis.maximum)))
    else:
        value = info.weight
    return value, abs(value - target)


def parse_weight_list(value: str) -> list[int] | None:
    normalized = value.strip().casefold()
    if normalized in {"auto", "latin", "cjk", "union", "intersection"}:
        return None
    try:
        weights = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise FontMergerError(
            "--weights 应为 auto、latin、cjk、union、intersection 或逗号分隔的数字"
        ) from exc
    if not weights or any(weight < 1 or weight > 1000 for weight in weights):
        raise FontMergerError("字重数值应在 1 到 1000 之间")
    return sorted(set(weights))


def plan_weights(
    infos: Sequence[SourceInfo],
    priority: Sequence[int],
    pair: tuple[int, int] | None,
    mode: str,
    match: str = "nearest",
    max_gap: int | None = None,
) -> list[tuple[int, tuple[int | None, ...]]]:
    """Plan output weights independently from glyph and hinting priority."""
    if match not in {"nearest", "exact"}:
        raise FontMergerError("--weight-match 应为 nearest 或 exact")
    if max_gap is not None and max_gap < 0:
        raise FontMergerError("--max-weight-gap 不能小于 0")

    explicit = parse_weight_list(mode)
    normalized = mode.strip().casefold()
    inventories = [available_weights(info) for info in infos]
    if explicit is not None:
        targets = explicit
    elif normalized == "union":
        targets = sorted({weight for values in inventories for weight in values})
    elif normalized == "intersection":
        candidates = sorted({weight for values in inventories for weight in values})
        targets = [
            weight
            for weight in candidates
            if all(matched_weight(info, weight)[1] == 0 for info in infos)
        ]
        if not targets:
            raise FontMergerError("输入字体没有可精确对应的共同字重")
    elif normalized in {"latin", "cjk"}:
        if pair is None:
            raise FontMergerError(
                f"无法可靠识别 {normalized} 字体；请改用 union、intersection 或数字列表"
            )
        index = pair[0 if normalized == "latin" else 1]
        targets = list(inventories[index])
    elif normalized == "auto":
        # A static face cannot change weight, so let it constrain variable inputs.
        # This makes the common "static Latin + variable CJK" case do what the
        # user expects: a Latin face at 350 automatically selects wght=350 from
        # the CJK font instead of producing several files with repeated Latin
        # outlines. When every input is variable, retain the richer family's
        # useful named-instance anchors.
        static_indexes = [
            index for index in priority if weight_axis(infos[index]) is None
        ]
        if static_indexes:
            index = static_indexes[0]
        else:
            index = max(
                priority,
                key=lambda item: (len(inventories[item]), -priority.index(item)),
            )
        preferred_targets = list(inventories[index])
        compatible_targets = [
            target
            for target in preferred_targets
            if all(matched_weight(info, target)[1] == 0 for info in infos)
        ]
        targets = compatible_targets or preferred_targets
        LOG.info(
            "自动字重基准：#%d %s（%s）",
            index + 1,
            infos[index].family,
            ", ".join(map(str, targets)),
        )
    else:
        raise FontMergerError(f"未知字重模式：{mode}")

    plan: list[tuple[int, tuple[int | None, ...]]] = []
    for target in targets:
        source_weights: list[int | None] = []
        for info in infos:
            selected, gap = matched_weight(info, target)
            if match == "exact" and gap:
                raise FontMergerError(
                    f"{info.family} 无法精确生成字重 {target}；"
                    "可改用 --weight-match nearest"
                )
            if max_gap is not None and gap > max_gap:
                raise FontMergerError(
                    f"{info.family} 与目标字重 {target} 相差 {gap}，"
                    f"超过 --max-weight-gap {max_gap}"
                )
            if gap:
                LOG.warning(
                    "%s 没有字重 %d，将使用最接近的 %d（相差 %d）",
                    info.family,
                    target,
                    selected,
                    gap,
                )
            source_weights.append(selected if weight_axis(info) is not None else None)
        plan.append((target, tuple(source_weights)))
    return plan


def choose_instance_name(
    infos: Sequence[SourceInfo],
    priority: Sequence[int],
    requested: str | None,
    output_style: str | None,
) -> tuple[str | None, bool]:
    if requested:
        return requested, True
    if output_style:
        return output_style, False
    for index in priority:
        if not infos[index].variable and infos[index].style:
            return infos[index].style, False
    variable_infos = [info for info in infos if info.variable]
    if variable_infos and all(
        find_instance(info, "Regular") for info in variable_infos
    ):
        return "Regular", False
    return None, False


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


def instantiate_if_variable(
    font: TTFont,
    requested_axes: dict[str, float],
    instance_coordinates: dict[str, float] | None = None,
) -> set[str]:
    if "fvar" not in font:
        return set()
    if "CFF2" in font:
        raise FontMergerError(
            "当前 fontTools 不能可靠地静态化 CFF2 可变字体；请先导出静态实例"
        )

    available = {axis.axisTag: axis for axis in font["fvar"].axes}
    used = set(requested_axes).intersection(available)
    instance_coordinates = instance_coordinates or {}
    limits = {
        tag: requested_axes.get(tag, instance_coordinates.get(tag, axis.defaultValue))
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
    LOG.info(
        "缩放 UPM：%d -> %d（并移除已失效的 TrueType hinting）", current, target_upm
    )
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


def style_flags(style: str, weight: int) -> tuple[bool, bool, bool]:
    lowered = style.casefold()
    italic = "italic" in lowered or "oblique" in lowered
    oblique = "oblique" in lowered
    # BOLD is a legacy style-linking flag, not a generic heavy-weight flag.
    # Reserve it for the actual Bold/Bold Italic face so that SemiBold,
    # ExtraBold and Black do not all collide as the same legacy Bold style.
    bold = normalized_style(style) == "bold"
    return bold, italic, oblique


def legacy_names(family: str, style: str, weight: int) -> tuple[str, str]:
    _bold, italic, _oblique = style_flags(style, weight)
    normalized = normalized_style(style)
    if normalized == "bold":
        return family, "Bold Italic" if italic else "Bold"
    if normalized in {"regular", "normal", "book"}:
        return family, "Italic" if italic else "Regular"

    # Share name ID 1 across extended weights so Windows and other clients
    # that expose the legacy family name do not turn each weight into a
    # separate visible family. Name IDs 16/17 still carry the same typographic
    # family plus the precise style, and usWeightClass selects the weight.
    return family, style


def set_font_names(font: TTFont, family: str, style: str, weight: int) -> None:
    if "name" not in font:
        return
    name = font["name"]
    full = family if style.casefold() == "regular" else f"{family} {style}"
    ps_name = postscript_name(family, style)
    unique = f"{VERSION};{ps_name}"
    legacy_family, legacy_style = legacy_names(family, style, weight)
    values = {
        1: legacy_family,
        2: legacy_style,
        3: unique,
        4: full,
        6: ps_name,
        16: family,
        17: style,
    }

    for name_id, value in values.items():
        name.removeNames(nameID=name_id)
        name.setName(value, name_id, 3, 1, 0x409)
        name.setName(value, name_id, 0, 4, 0)
        try:
            value.encode("mac_roman")
        except UnicodeEncodeError:
            continue
        name.setName(value, name_id, 1, 0, 0)


def read_style_metadata(font: TTFont) -> StyleMetadata:
    os2 = font["OS/2"]
    return StyleMetadata(
        int(os2.usWeightClass),
        int(os2.usWidthClass),
        int(os2.fsSelection),
        int(font["head"].macStyle),
        float(font["post"].italicAngle) if "post" in font else 0.0,
    )


def apply_style_metadata(
    font: TTFont, metadata: StyleMetadata, style: str, weight: int
) -> None:
    bold, italic, oblique = style_flags(style, weight)
    regular = normalized_style(style) in {"regular", "normal", "book"}
    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.usWeightClass = max(1, min(1000, int(weight)))
        os2.usWidthClass = metadata.width
        os2.fsSelection = metadata.fs_selection & ~(
            (1 << 0) | (1 << 5) | (1 << 6) | (1 << 9)
        )
        if italic:
            os2.fsSelection |= 1 << 0
        if bold:
            os2.fsSelection |= 1 << 5
        if regular and not bold and not italic:
            os2.fsSelection |= 1 << 6
        if oblique and os2.version >= 4:
            os2.fsSelection |= 1 << 9
    if "head" in font:
        font["head"].macStyle = (
            (metadata.mac_style & ~0x03) | (1 if bold else 0) | (2 if italic else 0)
        )
    if "post" in font:
        font["post"].italicAngle = metadata.italic_angle if italic else 0.0


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


def validate_output(
    path: Path, expected_unicodes: set[int], target_upm: int
) -> tuple[int, int]:
    with TTFont(path, lazy=False) as font:
        actual = set((font.getBestCmap() or {}).keys())
        missing = expected_unicodes - actual
        if missing:
            examples = ", ".join(f"U+{cp:04X}" for cp in sorted(missing)[:10])
            raise FontMergerError(
                f"输出自检失败：缺少 {len(missing)} 个字符（{examples}）"
            )
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
    priority: str = "auto",
    hinting_source: str = "auto",
    instance: str | None = None,
    source_weights: Sequence[int | None] | None = None,
    inspected_sources: Sequence[SourceInfo] | None = None,
    output_weight: int | None = None,
) -> tuple[int, int]:
    if len(sources) < 2:
        raise FontMergerError("至少需要两个输入字体")
    if curve_error <= 0:
        raise FontMergerError("--curve-error 必须大于 0")

    axes = axes or {}
    infos = list(inspected_sources or (inspect_source(source) for source in sources))
    if len(infos) != len(sources):
        raise FontMergerError("字体检查结果与输入数量不一致")
    if source_weights is not None and len(source_weights) != len(sources):
        raise FontMergerError("每字体字重映射与输入数量不一致")
    pair = detect_latin_cjk_pair(infos)
    priority_order = resolve_priority(priority, infos, pair)
    hint_index = resolve_hinting_source(hinting_source, infos, priority_order, pair)

    selected_unicodes: list[set[int]] = [set() for _ in infos]
    claimed: set[int] = set()
    expected: set[int] = set()
    for index in priority_order:
        selected = set(infos[index].unicodes) - claimed
        selected_unicodes[index] = selected
        claimed.update(infos[index].unicodes)
        expected.update(selected)

    contributing = [index for index in priority_order if selected_unicodes[index]]
    if len(contributing) < 2:
        raise FontMergerError("除优先字体外，没有输入字体能补充新字符")
    if hint_index is not None and hint_index not in contributing:
        if hinting_source.casefold() == "auto":
            hint_index = contributing[0]
        else:
            raise FontMergerError("指定的 hinting 来源没有为输出字体提供字符")

    chosen_instance_name, explicit_instance = choose_instance_name(
        infos,
        priority_order,
        instance,
        style,
    )
    instance_coordinates: list[dict[str, float]] = [{} for _ in infos]
    matched_instance_names: list[str | None] = [None for _ in infos]
    if chosen_instance_name:
        for index, info in enumerate(infos):
            if not info.variable:
                continue
            matched = find_instance(info, chosen_instance_name)
            if matched is None:
                if explicit_instance:
                    raise FontMergerError(
                        f"{info.source.label} 没有名为 {chosen_instance_name!r} 的可变字体实例"
                    )
                matched = find_instance(info, "Regular")
                if matched is None:
                    LOG.warning(
                        "%s 没有 %s 或 Regular 实例，使用其默认轴坐标",
                        info.source.label,
                        chosen_instance_name,
                    )
                    continue
                LOG.warning(
                    "%s 没有 %s 实例，改用 Regular",
                    info.source.label,
                    chosen_instance_name,
                )
            instance_coordinates[index] = matched.coordinate_map
            matched_instance_names[index] = matched.name
            LOG.info(
                "选择 %s 的 %s 实例：%s",
                info.family,
                matched.name,
                ", ".join(f"{tag}={value:g}" for tag, value in matched.coordinates),
            )

    if hint_index is None:
        internal_order = contributing
        target_upm = infos[priority_order[0]].upm
        LOG.info("Hinting：全部移除")
    else:
        internal_order = [
            hint_index,
            *[index for index in contributing if index != hint_index],
        ]
        target_upm = infos[hint_index].upm
        LOG.info("Hinting 来源：#%d %s", hint_index + 1, infos[hint_index].family)

    if style:
        chosen_style = style
    elif "wght" in axes:
        chosen_style = style_for_weight(axes["wght"])
    elif instance:
        chosen_style = next((name for name in matched_instance_names if name), instance)
    elif not infos[priority_order[0]].variable:
        chosen_style = infos[priority_order[0]].style
    elif chosen_instance_name and any(matched_instance_names):
        chosen_style = next(name for name in matched_instance_names if name)
    else:
        chosen_style = infos[priority_order[0]].style

    chosen_family = family or default_family(
        [(infos[index].family, infos[index].style) for index in priority_order]
    )
    used_axes: set[str] = set()
    style_metadata: StyleMetadata | None = None

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="font-merger-") as temp_name:
        temp_dir = Path(temp_name)
        prepared_paths: list[Path] = []

        for position, index in enumerate(internal_order):
            source = sources[index]
            LOG.info("读取 [%d/%d] %s", position + 1, len(internal_order), source.label)
            font = open_source(source)
            try:
                reject_color_font(font, source.label)
                source_axes = dict(axes)
                if source_weights is not None and source_weights[index] is not None:
                    source_axes["wght"] = float(source_weights[index])
                used_axes.update(
                    instantiate_if_variable(
                        font, source_axes, instance_coordinates[index]
                    )
                )
                selected = selected_unicodes[index]
                LOG.info(
                    "采用 %d 个字符，忽略 %d 个由更高优先级字体提供的字符",
                    len(selected),
                    len(infos[index].unicodes) - len(selected),
                )
                subset_to_unicodes(font, selected)

                if "CFF " in font or "CFF2" in font:
                    LOG.info("将 PostScript 三次曲线轮廓转换为 TrueType 二次曲线")
                    convert_cff_to_glyf(font, curve_error)
                normalize_upm(font, target_upm)
                if hint_index is None or index != hint_index:
                    remove_hinting(font)
                elif not HINT_TABLES.intersection(font.keys()):
                    LOG.warning("指定的 hinting 来源不包含可保留的 TrueType hinting")

                if index == priority_order[0]:
                    style_metadata = read_style_metadata(font)
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
            raise FontMergerError(
                f"输入字体均不包含这些轴：{', '.join(sorted(unknown_axes))}"
            )
        LOG.info("合并 %d 个已完成字符归属分配的字体", len(prepared_paths))
        options = MergeOptions(drop_tables=list(INVALIDATED_TABLES))
        merged = Merger(options=options).merge([str(path) for path in prepared_paths])
        merged.recalcTimestamp = False
        merged.recalcBBoxes = True

        assert style_metadata is not None
        requested_weight = output_weight
        if requested_weight is None:
            requested_weight = axes.get("wght")
        if requested_weight is None:
            requested_weight = style_weight(chosen_style)
        chosen_weight = int(round(requested_weight or style_metadata.weight))
        set_font_names(merged, chosen_family, chosen_style, chosen_weight)
        apply_style_metadata(merged, style_metadata, chosen_style, chosen_weight)
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


def style_for_output_weight(weight: int) -> str:
    style = style_for_weight(weight)
    if style_weight(style) == weight:
        return style
    return f"Weight {weight}"


def weighted_output_path(output: Path, style: str, multiple: bool) -> Path:
    if not multiple:
        return output
    suffix = output.suffix or ".ttf"
    stem = output.stem if output.suffix else output.name
    safe_style = re.sub(r"[^A-Za-z0-9._-]+", "-", style).strip("-")
    return output.with_name(f"{stem}-{safe_style}{suffix}")


def merge_font_family(
    sources: Sequence[FontSource],
    output: Path,
    family: str | None = None,
    style: str | None = None,
    axes: dict[str, float] | None = None,
    curve_error: float = 1.0,
    priority: str = "auto",
    hinting_source: str = "auto",
    instance: str | None = None,
    weights: str = "auto",
    weight_match: str = "nearest",
    max_weight_gap: int | None = None,
) -> list[MergeResult]:
    """Merge one explicit style, or automatically build a static font family."""
    axes = dict(axes or {})
    explicit_style = style is not None or instance is not None or "wght" in axes
    if explicit_style:
        if weights.strip().casefold() != "auto":
            raise FontMergerError(
                "--style、--instance 或 --axis wght 已指定单一字重，不能同时使用 --weights"
            )
        characters, glyphs = merge_fonts(
            sources,
            output,
            family=family,
            style=style,
            axes=axes,
            curve_error=curve_error,
            priority=priority,
            hinting_source=hinting_source,
            instance=instance,
        )
        selected_style = style or instance or style_for_weight(axes.get("wght", 400))
        selected_weight = int(
            round(axes.get("wght", style_weight(selected_style) or 400))
        )
        return [
            MergeResult(
                output.resolve(), selected_style, selected_weight, characters, glyphs
            )
        ]

    infos = [inspect_source(source) for source in sources]
    pair = detect_latin_cjk_pair(infos)
    priority_order = resolve_priority(priority, infos, pair)
    plan = plan_weights(
        infos,
        priority_order,
        pair,
        weights,
        match=weight_match,
        max_gap=max_weight_gap,
    )
    multiple = len(plan) > 1
    results: list[MergeResult] = []
    for position, (weight, source_weights) in enumerate(plan, start=1):
        output_style = style_for_output_weight(weight)
        target = weighted_output_path(output, output_style, multiple)
        LOG.info(
            "生成字重 [%d/%d] %s (%d)：%s",
            position,
            len(plan),
            output_style,
            weight,
            target,
        )
        characters, glyphs = merge_fonts(
            sources,
            target,
            family=family,
            style=output_style,
            axes=axes,
            curve_error=curve_error,
            priority=priority,
            hinting_source=hinting_source,
            source_weights=source_weights,
            inspected_sources=infos,
            output_weight=weight,
        )
        results.append(
            MergeResult(target.resolve(), output_style, weight, characters, glyphs)
        )
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="font-merger",
        description=(
            "合并 TTF/OTF/TTC/OTC。双字体的西文 + CJK 组合会自动让西文字体"
            "覆盖重复字符；其他组合默认按输入顺序。"
        ),
    )
    parser.add_argument(
        "fonts", nargs="*", metavar="FONT", help="字体路径；集合 face 写作 'path.ttc#0'"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("merged.ttf"),
        help="输出文件名基准；多个字重会自动添加样式名（默认 merged.ttf）",
    )
    parser.add_argument("--family", help="输出字体家族名")
    parser.add_argument("--style", help="输出样式名；默认自动匹配输入字体")
    parser.add_argument(
        "--instance",
        metavar="NAME",
        help="只生成一个可变字体实例，如 Regular、Medium、Bold",
    )
    parser.add_argument(
        "--axis",
        action="append",
        default=[],
        metavar="TAG=VALUE",
        help="可变字体轴坐标，可重复",
    )
    parser.add_argument(
        "--priority",
        default="auto",
        metavar="auto|input|ORDER",
        help="字符来源优先级；默认 auto，也可用 input 或 2,1,3",
    )
    parser.add_argument(
        "--hinting-source",
        default="auto",
        metavar="auto|latin|cjk|none|N",
        help="TrueType hinting 来源；中西文双字体默认保持 CJK，其余跟随最高优先级",
    )
    parser.add_argument(
        "--weights",
        default="auto",
        metavar="auto|latin|cjk|union|intersection|LIST",
        help="自动生成哪些字重；也可写 300,400,700（默认 auto）",
    )
    parser.add_argument(
        "--weight-match",
        choices=("nearest", "exact"),
        default="nearest",
        help="某输入缺少目标字重时使用最近字重或报错（默认 nearest）",
    )
    parser.add_argument(
        "--max-weight-gap",
        type=int,
        metavar="N",
        help="最近字重允许的最大差值；默认不限制",
    )
    parser.add_argument(
        "--curve-error",
        type=float,
        default=1.0,
        metavar="UNITS",
        help="OTF 曲线转换最大误差（默认 1.0）",
    )
    parser.add_argument(
        "--list",
        dest="list_font",
        type=Path,
        metavar="FONT",
        help="列出 TTC/OTC face 或可变字体实例后退出",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="显示 fontTools 详细日志"
    )
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
            list_path = args.list_font.expanduser().resolve()
            collection = is_collection(list_path)
            for face in collection_faces(list_path):
                label = f"face #{face.index}" if collection else "font"
                print(f"{label}\t{face.family}\t{face.style}")
                for axis in face.axes:
                    print(
                        f"  axis {axis.tag}\t{axis.minimum:g}..{axis.maximum:g}"
                        f" (default {axis.default:g})\t{axis.name}"
                    )
                for instance in face.instances:
                    coordinates = ", ".join(
                        f"{tag}={value:g}" for tag, value in instance.coordinates
                    )
                    print(f"  instance\t{instance.name}\t{coordinates}")
            return 0
        if not args.fonts:
            parser.print_help()
            return 0

        sources = [parse_source(value) for value in args.fonts]
        axes = parse_axis(args.axis)
        results = merge_font_family(
            sources,
            args.output,
            family=args.family,
            style=args.style,
            axes=axes,
            curve_error=args.curve_error,
            priority=args.priority,
            hinting_source=args.hinting_source,
            instance=args.instance,
            weights=args.weights,
            weight_match=args.weight_match,
            max_weight_gap=args.max_weight_gap,
        )
        for result in results:
            print(
                f"完成：{result.path}（{result.style}，{result.characters} 个 Unicode 字符，"
                f"{result.glyphs} 个 glyph）"
            )
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
