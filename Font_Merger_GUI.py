#!/usr/bin/env python3
"""Localized, standalone Tk GUI for Font Merger."""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import re
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from Font_Merger import (
    FontMergerError,
    LOG,
    VERSION,
    collection_faces,
    is_collection,
    merge_font_family,
    parse_axis,
    parse_source,
)


DEFAULT_LOCALE = "zh_CN"
GUI_FONT_FAMILY = "JetBrainsLxgwNerdMono"
GUI_FONT_FILENAME = "JetBrainsLxgwNerdMono-Regular.ttf"
GUI_FONT_FALLBACK = "Segoe UI"
GUI_FONT_RELATIVE_PATH = Path("assets") / "fonts" / GUI_FONT_FILENAME


def gui_font_candidates(
    app_dir: Path | None = None, windows_fonts: Path | None = None
) -> tuple[Path, Path]:
    """Return deterministic bundled-first locations for the GUI font."""
    if app_dir is None:
        app_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    if windows_fonts is None:
        windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    return app_dir / GUI_FONT_RELATIVE_PATH, windows_fonts / GUI_FONT_FILENAME


def select_gui_font_family(available_families: tuple[str, ...]) -> str:
    """Select the requested family when Tk can see it, otherwise fall back safely."""
    families = {family.casefold(): family for family in available_families}
    return families.get(GUI_FONT_FAMILY.casefold(), GUI_FONT_FALLBACK)


def register_private_font(path: Path) -> bool:
    """Register a font for this Windows process without installing it globally."""
    if sys.platform != "win32" or not path.is_file():
        return False
    return bool(ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0))


def unregister_private_font(path: Path | None) -> None:
    if sys.platform == "win32" and path is not None:
        ctypes.windll.gdi32.RemoveFontResourceExW(str(path), 0x10, 0)


def configure_gui_font(root: tk.Tk) -> tuple[str, Path | None]:
    """Load the bundled font and apply one family to every Tk widget class."""
    registered = next(
        (path for path in gui_font_candidates() if register_private_font(path)),
        None,
    )
    family = select_gui_font_family(tuple(tkfont.families(root)))
    for name in (
        "TkDefaultFont",
        "TkTextFont",
        "TkFixedFont",
        "TkMenuFont",
        "TkHeadingFont",
        "TkCaptionFont",
        "TkSmallCaptionFont",
        "TkIconFont",
        "TkTooltipFont",
    ):
        try:
            tkfont.nametofont(name, root=root).configure(family=family)
        except tk.TclError:
            pass
    root.option_add("*Font", f"{{{family}}} 10")
    root.option_add("*TCombobox*Listbox.font", f"{{{family}}} 10")
    return family, registered


LANGUAGES = {
    "zh_CN": "简体中文",
    "zh_TW": "繁體中文",
    "en": "English",
}

TEXT = {
    "zh_CN": {
        "window_title": "Font Merger {version}",
        "header_subtitle": "把西文与中文字体合并为开箱即用的完整字体家族",
        "language": "界面语言",
        "fonts_title": "选择字体",
        "fonts_desc": "至少添加两个字体；TTC / OTC 会提示选择其中的字体。",
        "font_count": "{count} 个字体",
        "add_fonts": "＋ 添加字体",
        "remove_selected": "移除所选",
        "move_up": "↑ 上移",
        "move_down": "↓ 下移",
        "output_title": "设置输出",
        "output_desc": "多字重会自动在文件名后添加 Thin、Regular、Bold 等样式名。",
        "output_file": "输出文件",
        "browse": "浏览…",
        "family_optional": "家族名（可选）",
        "rules_title": "选择合并策略",
        "rules_desc": "下面三项彼此独立。保持推荐值即可完成常见的中西文字体合并。",
        "reset_recommended": "恢复推荐设置",
        "glyph_title": "字符覆盖",
        "glyph_desc": "重复字符使用哪一款字体",
        "hint_title": "显示清晰度",
        "hint_desc": "选择整份字体的 Hinting 来源",
        "weights_title": "输出字重",
        "weights_desc": "决定生成哪些 Thin / Bold 等文件",
        "missing_weight": "缺失字重",
        "advanced_show": "▸ 显示高级设置",
        "advanced_hide": "▾ 收起高级设置",
        "advanced_desc": "自定义顺序、字重数值、实例和可变轴",
        "custom_priority": "字符顺序",
        "custom_priority_hint": "例如 2,1,3",
        "custom_hinting": "Hinting 字体序号",
        "custom_hinting_hint": "例如 2",
        "custom_weights": "自定义字重",
        "custom_weights_hint": "例如 300,400,700",
        "max_gap": "最大字重差",
        "max_gap_hint": "留空表示不限制",
        "fixed_instance": "固定单一实例",
        "fixed_instance_hint": "例如 Bold",
        "variable_axes": "可变轴坐标",
        "variable_axes_hint": "例如 wdth=90,slnt=-10",
        "summary": "当前方案",
        "start": "开始合并字体",
        "log_show": "▸ 查看运行记录",
        "log_hide": "▾ 收起运行记录",
        "status_need_fonts": "请先添加至少两个字体",
        "status_ready": "已选择 {count} 个字体，可以开始合并",
        "status_reset": "已恢复推荐设置",
        "status_running": "正在分析并合并字体…",
        "status_done": "合并完成 · 已生成 {count} 个字体",
        "status_error": "合并失败，请查看运行记录",
        "task_start": "──────── 开始新的合并任务 ────────",
        "completed_path": "完成：{path}",
        "font_dialog_title": "选择字体",
        "font_files": "字体文件",
        "all_files": "所有文件",
        "collection_title": "选择集合字体",
        "collection_prompt": "{name} 包含：\n\n{choices}\n\n请输入序号：",
        "font_read_error": "无法读取字体",
        "output_dialog_title": "选择输出文件名基准",
        "ttf_file": "TrueType 字体",
        "missing_fonts_title": "缺少字体",
        "missing_fonts_text": "请至少添加两个字体。",
        "missing_output_title": "缺少输出",
        "missing_output_text": "请选择输出文件。",
        "parameter_error": "参数错误",
        "done_title": "合并完成",
        "done_text": "已生成 {count} 个字体。",
        "error_title": "合并失败",
        "engine_error_generic": "字体处理失败，请检查所选字体和高级参数。",
        "priority_auto": "自动识别（推荐）",
        "priority_input": "按字体列表顺序",
        "priority_first": "第 1 个优先",
        "priority_second": "第 2 个优先",
        "hint_auto": "自动保持中文 / CJK（推荐）",
        "hint_latin": "优先保持西文",
        "hint_cjk": "优先保持中文 / CJK",
        "hint_none": "移除 Hinting",
        "weights_auto": "采用字重更多的一侧（推荐）",
        "weights_latin": "采用西文字重",
        "weights_cjk": "采用中文 / CJK 字重",
        "weights_union": "合并双方全部字重",
        "weights_intersection": "仅双方共有字重",
        "match_nearest": "使用最接近字重（推荐）",
        "match_exact": "必须精确匹配",
        "summary_instance": "固定 {value} 实例",
        "summary_axes": "轴 {value}",
    },
    "zh_TW": {
        "window_title": "Font Merger {version}",
        "header_subtitle": "將西文字型與中文字型合併為開箱即用的完整字型家族",
        "language": "介面語言",
        "fonts_title": "選擇字型",
        "fonts_desc": "至少加入兩個字型；TTC / OTC 會提示選擇其中的字型。",
        "font_count": "{count} 個字型",
        "add_fonts": "＋ 加入字型",
        "remove_selected": "移除所選",
        "move_up": "↑ 上移",
        "move_down": "↓ 下移",
        "output_title": "設定輸出",
        "output_desc": "多字重會自動在檔名後加入 Thin、Regular、Bold 等樣式名稱。",
        "output_file": "輸出檔案",
        "browse": "瀏覽…",
        "family_optional": "家族名稱（選填）",
        "rules_title": "選擇合併策略",
        "rules_desc": "以下三項彼此獨立。保留建議值即可完成常見的中西文字型合併。",
        "reset_recommended": "恢復建議設定",
        "glyph_title": "字元覆蓋",
        "glyph_desc": "重複字元要使用哪一款字型",
        "hint_title": "顯示清晰度",
        "hint_desc": "選擇整份字型的 Hinting 來源",
        "weights_title": "輸出字重",
        "weights_desc": "決定產生哪些 Thin / Bold 等檔案",
        "missing_weight": "缺少字重",
        "advanced_show": "▸ 顯示進階設定",
        "advanced_hide": "▾ 收合進階設定",
        "advanced_desc": "自訂順序、字重數值、實例與可變軸",
        "custom_priority": "字元順序",
        "custom_priority_hint": "例如 2,1,3",
        "custom_hinting": "Hinting 字型序號",
        "custom_hinting_hint": "例如 2",
        "custom_weights": "自訂字重",
        "custom_weights_hint": "例如 300,400,700",
        "max_gap": "最大字重差",
        "max_gap_hint": "留空表示不限制",
        "fixed_instance": "固定單一實例",
        "fixed_instance_hint": "例如 Bold",
        "variable_axes": "可變軸座標",
        "variable_axes_hint": "例如 wdth=90,slnt=-10",
        "summary": "目前方案",
        "start": "開始合併字型",
        "log_show": "▸ 查看執行記錄",
        "log_hide": "▾ 收合執行記錄",
        "status_need_fonts": "請先加入至少兩個字型",
        "status_ready": "已選擇 {count} 個字型，可以開始合併",
        "status_reset": "已恢復建議設定",
        "status_running": "正在分析並合併字型…",
        "status_done": "合併完成 · 已產生 {count} 個字型",
        "status_error": "合併失敗，請查看執行記錄",
        "task_start": "──────── 開始新的合併工作 ────────",
        "completed_path": "完成：{path}",
        "font_dialog_title": "選擇字型",
        "font_files": "字型檔案",
        "all_files": "所有檔案",
        "collection_title": "選擇集合字型",
        "collection_prompt": "{name} 包含：\n\n{choices}\n\n請輸入序號：",
        "font_read_error": "無法讀取字型",
        "output_dialog_title": "選擇輸出檔名基準",
        "ttf_file": "TrueType 字型",
        "missing_fonts_title": "缺少字型",
        "missing_fonts_text": "請至少加入兩個字型。",
        "missing_output_title": "缺少輸出",
        "missing_output_text": "請選擇輸出檔案。",
        "parameter_error": "參數錯誤",
        "done_title": "合併完成",
        "done_text": "已產生 {count} 個字型。",
        "error_title": "合併失敗",
        "engine_error_generic": "字型處理失敗，請檢查所選字型與進階參數。",
        "priority_auto": "自動辨識（建議）",
        "priority_input": "依字型清單順序",
        "priority_first": "第 1 個優先",
        "priority_second": "第 2 個優先",
        "hint_auto": "自動保留中文 / CJK（建議）",
        "hint_latin": "優先保留西文",
        "hint_cjk": "優先保留中文 / CJK",
        "hint_none": "移除 Hinting",
        "weights_auto": "採用字重較多的一側（建議）",
        "weights_latin": "採用西文字重",
        "weights_cjk": "採用中文 / CJK 字重",
        "weights_union": "合併雙方全部字重",
        "weights_intersection": "僅雙方共有字重",
        "match_nearest": "使用最接近字重（建議）",
        "match_exact": "必須精確符合",
        "summary_instance": "固定 {value} 實例",
        "summary_axes": "軸 {value}",
    },
    "en": {
        "window_title": "Font Merger {version}",
        "header_subtitle": "Combine Western and CJK fonts into a ready-to-use font family",
        "language": "Language",
        "fonts_title": "Choose fonts",
        "fonts_desc": "Add at least two fonts. TTC / OTC files will prompt for a face.",
        "font_count": "{count} fonts",
        "add_fonts": "+ Add fonts",
        "remove_selected": "Remove selected",
        "move_up": "↑ Move up",
        "move_down": "↓ Move down",
        "output_title": "Set output",
        "output_desc": "Multiple weights are suffixed with names such as Thin, Regular and Bold.",
        "output_file": "Output file",
        "browse": "Browse…",
        "family_optional": "Family name (optional)",
        "rules_title": "Choose merge rules",
        "rules_desc": "These three choices are independent. The recommended defaults suit most Latin + CJK merges.",
        "reset_recommended": "Restore defaults",
        "glyph_title": "Glyph priority",
        "glyph_desc": "Which font supplies duplicate characters",
        "hint_title": "Screen clarity",
        "hint_desc": "Which font supplies global TrueType hinting",
        "weights_title": "Output weights",
        "weights_desc": "Which Thin / Bold and other files to create",
        "missing_weight": "Missing weights",
        "advanced_show": "▸ Show advanced settings",
        "advanced_hide": "▾ Hide advanced settings",
        "advanced_desc": "Custom order, numeric weights, instances and variable axes",
        "custom_priority": "Glyph order",
        "custom_priority_hint": "For example: 2,1,3",
        "custom_hinting": "Hinting font number",
        "custom_hinting_hint": "For example: 2",
        "custom_weights": "Custom weights",
        "custom_weights_hint": "For example: 300,400,700",
        "max_gap": "Maximum weight gap",
        "max_gap_hint": "Leave blank for no limit",
        "fixed_instance": "Single named instance",
        "fixed_instance_hint": "For example: Bold",
        "variable_axes": "Variable axis values",
        "variable_axes_hint": "For example: wdth=90,slnt=-10",
        "summary": "Current plan",
        "start": "Merge fonts",
        "log_show": "▸ Show activity log",
        "log_hide": "▾ Hide activity log",
        "status_need_fonts": "Add at least two fonts to continue",
        "status_ready": "{count} fonts selected — ready to merge",
        "status_reset": "Recommended settings restored",
        "status_running": "Analyzing and merging fonts…",
        "status_done": "Complete · created {count} fonts",
        "status_error": "Merge failed — see the activity log",
        "task_start": "──────── Starting a new merge ────────",
        "completed_path": "Created: {path}",
        "font_dialog_title": "Choose fonts",
        "font_files": "Font files",
        "all_files": "All files",
        "collection_title": "Choose a collection face",
        "collection_prompt": "{name} contains:\n\n{choices}\n\nEnter a face number:",
        "font_read_error": "Could not read font",
        "output_dialog_title": "Choose the output file base name",
        "ttf_file": "TrueType font",
        "missing_fonts_title": "Fonts required",
        "missing_fonts_text": "Add at least two fonts.",
        "missing_output_title": "Output required",
        "missing_output_text": "Choose an output file.",
        "parameter_error": "Invalid settings",
        "done_title": "Merge complete",
        "done_text": "Created {count} fonts.",
        "error_title": "Merge failed",
        "engine_error_generic": "Font processing failed. Check the selected fonts and advanced settings.",
        "priority_auto": "Detect automatically (recommended)",
        "priority_input": "Follow the font list order",
        "priority_first": "Font 1 first",
        "priority_second": "Font 2 first",
        "hint_auto": "Preserve CJK automatically (recommended)",
        "hint_latin": "Prefer Latin hinting",
        "hint_cjk": "Prefer CJK hinting",
        "hint_none": "Remove hinting",
        "weights_auto": "Use the richer weight set (recommended)",
        "weights_latin": "Use Latin font weights",
        "weights_cjk": "Use CJK font weights",
        "weights_union": "Use all weights from both",
        "weights_intersection": "Use shared weights only",
        "match_nearest": "Use nearest weight (recommended)",
        "match_exact": "Require an exact match",
        "summary_instance": "Instance {value}",
        "summary_axes": "Axes {value}",
    },
}

PRIORITY_CHOICES = (
    ("priority_auto", "auto"),
    ("priority_input", "input"),
    ("priority_first", "1,2"),
    ("priority_second", "2,1"),
)
HINTING_CHOICES = (
    ("hint_auto", "auto"),
    ("hint_latin", "latin"),
    ("hint_cjk", "cjk"),
    ("hint_none", "none"),
)
WEIGHT_CHOICES = (
    ("weights_auto", "auto"),
    ("weights_latin", "latin"),
    ("weights_cjk", "cjk"),
    ("weights_union", "union"),
    ("weights_intersection", "intersection"),
)
MATCH_CHOICES = (
    ("match_nearest", "nearest"),
    ("match_exact", "exact"),
)

# Each major region owns a muted Morandi palette. Nested controls inherit it.
PALETTES = {
    "Header": {
        "surface": "#697A8D",
        "control": "#E2E7EA",
        "border": "#8795A3",
        "text": "#F7F8F8",
        "muted": "#DCE2E7",
        "accent": "#4E6073",
    },
    "Input": {
        "surface": "#DDE5DA",
        "control": "#EDF1EA",
        "border": "#B6C2B1",
        "text": "#3F4A3D",
        "muted": "#6F7C6B",
        "accent": "#71816C",
    },
    "Output": {
        "surface": "#E8DAD8",
        "control": "#F3E9E7",
        "border": "#CDB5B3",
        "text": "#544241",
        "muted": "#876F6D",
        "accent": "#967978",
    },
    "Rules": {
        "surface": "#DCE3E9",
        "control": "#EBEFF3",
        "border": "#B7C2CC",
        "text": "#3D4854",
        "muted": "#6B7885",
        "accent": "#718496",
    },
    "Advanced": {
        "surface": "#E4DCE5",
        "control": "#F0EAF1",
        "border": "#C5B6C7",
        "text": "#4D414F",
        "muted": "#7D6D80",
        "accent": "#87728A",
    },
    "Footer": {
        "surface": "#E5DFD2",
        "control": "#F1EDE5",
        "border": "#C7BDA9",
        "text": "#4E493F",
        "muted": "#7C7465",
        "accent": "#80745F",
    },
    "Log": {
        "surface": "#D8DDDC",
        "control": "#303837",
        "border": "#AAB4B2",
        "text": "#34403E",
        "muted": "#667371",
        "accent": "#657774",
    },
}

APP_BACKGROUND = "#E9E5DF"
SUCCESS = "#5D7C6A"
DANGER = "#9A5F5B"

# fontTools work runs in a worker thread. Keeping the original printf-style
# arguments lets the GUI render the same activity record in the active locale.
CORE_LOG_TEXT = {
    "%s 含 %d 个 face；未指定时使用 #0（%s %s）": {
        "zh_TW": "%s 含有 %d 個 face；未指定時使用 #0（%s %s）",
        "en": "%s contains %d faces; using #0 by default (%s %s)",
    },
    "检测到西文 + CJK：%s 覆盖重叠字符，%s 补充其余字符": {
        "zh_TW": "偵測到西文 + CJK：%s 覆蓋重複字元，%s 補充其餘字元",
        "en": "Detected Latin + CJK: %s supplies duplicate characters; %s fills the rest",
    },
    "未检测到明确的西文 + CJK 双字体组合，按输入顺序处理": {
        "zh_TW": "未偵測到明確的西文 + CJK 雙字型組合，依輸入順序處理",
        "en": "No clear Latin + CJK pair detected; using input order",
    },
    "自动字重来源：#%d %s（%s）": {
        "zh_TW": "自動字重來源：#%d %s（%s）",
        "en": "Automatic weight source: #%d %s (%s)",
    },
    "%s 没有字重 %d，将使用最接近的 %d（相差 %d）": {
        "zh_TW": "%s 沒有字重 %d，將使用最接近的 %d（相差 %d）",
        "en": "%s has no weight %d; using nearest weight %d (gap %d)",
    },
    "静态化可变字体：%s": {
        "zh_TW": "靜態化可變字型：%s",
        "en": "Instantiating variable font: %s",
    },
    "缩放 UPM：%d -> %d（并移除已失效的 TrueType hinting）": {
        "zh_TW": "縮放 UPM：%d -> %d（並移除已失效的 TrueType hinting）",
        "en": "Scaling UPM: %d -> %d (and removing invalid TrueType hinting)",
    },
    "%s 没有 %s 或 Regular 实例，使用其默认轴坐标": {
        "zh_TW": "%s 沒有 %s 或 Regular 實例，使用預設軸座標",
        "en": "%s has no %s or Regular instance; using default axis values",
    },
    "%s 没有 %s 实例，改用 Regular": {
        "zh_TW": "%s 沒有 %s 實例，改用 Regular",
        "en": "%s has no %s instance; using Regular",
    },
    "选择 %s 的 %s 实例：%s": {
        "zh_TW": "選擇 %s 的 %s 實例：%s",
        "en": "Selecting %s instance %s: %s",
    },
    "Hinting：全部移除": {
        "zh_TW": "Hinting：全部移除",
        "en": "Hinting: removed",
    },
    "Hinting 来源：#%d %s": {
        "zh_TW": "Hinting 來源：#%d %s",
        "en": "Hinting source: #%d %s",
    },
    "读取 [%d/%d] %s": {
        "zh_TW": "讀取 [%d/%d] %s",
        "en": "Reading [%d/%d] %s",
    },
    "采用 %d 个字符，忽略 %d 个由更高优先级字体提供的字符": {
        "zh_TW": "採用 %d 個字元，忽略 %d 個由較高優先級字型提供的字元",
        "en": "Using %d characters; ignoring %d supplied by a higher-priority font",
    },
    "将 PostScript 三次曲线轮廓转换为 TrueType 二次曲线": {
        "zh_TW": "將 PostScript 三次曲線輪廓轉換為 TrueType 二次曲線",
        "en": "Converting PostScript cubic outlines to TrueType quadratic outlines",
    },
    "指定的 hinting 来源不包含可保留的 TrueType hinting": {
        "zh_TW": "指定的 hinting 來源不包含可保留的 TrueType hinting",
        "en": "The selected hinting source has no reusable TrueType hinting",
    },
    "合并 %d 个已完成字符归属分配的字体": {
        "zh_TW": "合併 %d 個已完成字元歸屬分配的字型",
        "en": "Merging %d fonts after assigning character ownership",
    },
    "生成字重 [%d/%d] %s (%d)：%s": {
        "zh_TW": "產生字重 [%d/%d] %s (%d)：%s",
        "en": "Generating weight [%d/%d] %s (%d): %s",
    },
}


class QueueLogHandler(logging.Handler):
    def __init__(self, events: queue.Queue[tuple[str, object]]) -> None:
        super().__init__()
        self.events = events

    def emit(self, record: logging.LogRecord) -> None:
        self.events.put(
            (
                "log",
                (record.levelname, str(record.msg), record.args, self.format(record)),
            )
        )


class FontMergerGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.locale = DEFAULT_LOCALE
        self.gui_font_family, self._registered_gui_font = configure_gui_font(root)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.localized_widgets: list[tuple[tk.Widget, str]] = []
        self.choice_bindings: list[dict[str, Any]] = []
        self.status_key = "status_need_fonts"
        self.status_values: dict[str, object] = {}
        self.advanced_visible = False
        self.log_visible = False
        self._resize_job: str | None = None
        self._scroll_job: str | None = None
        self._pending_width = 0
        self._last_canvas_width = 0
        self._last_scrollregion: tuple[int, int, int, int] | None = None

        self.root.minsize(820, 700)
        self.root.configure(background=APP_BACKGROUND)
        self._configure_styles()
        self._center_window(960, 840)

        self.output = tk.StringVar(value=str(Path.cwd() / "merged.ttf"))
        self.family = tk.StringVar()
        self.priority = tk.StringVar(value="auto")
        self.hinting = tk.StringVar(value="auto")
        self.weights = tk.StringVar(value="auto")
        self.weight_match = tk.StringVar(value="nearest")
        self.custom_priority = tk.StringVar()
        self.custom_hinting = tk.StringVar()
        self.custom_weights = tk.StringVar()
        self.max_gap = tk.StringVar()
        self.instance = tk.StringVar()
        self.axes = tk.StringVar()
        self.summary = tk.StringVar()
        self.status = tk.StringVar()
        self.font_count = tk.StringVar()
        self.language_display = tk.StringVar(value=LANGUAGES[self.locale])

        self._build_layout()
        for variable in (
            self.priority,
            self.hinting,
            self.weights,
            self.weight_match,
            self.custom_priority,
            self.custom_hinting,
            self.custom_weights,
            self.max_gap,
            self.instance,
            self.axes,
        ):
            variable.trace_add("write", self.update_summary)

        self.log_handler = QueueLogHandler(self.events)
        self.log_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        LOG.addHandler(self.log_handler)
        LOG.setLevel(logging.INFO)
        logging.getLogger("fontTools").setLevel(logging.ERROR)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh_language()
        self.root.after(100, self.poll_events)

    def t(self, key: str, **values: object) -> str:
        return TEXT[self.locale][key].format(**values)

    def _register_text(self, widget: tk.Widget, key: str) -> tk.Widget:
        self.localized_widgets.append((widget, key))
        widget.configure(text=self.t(key))
        return widget

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=(self.gui_font_family, 10))
        style.configure("App.TFrame", background=APP_BACKGROUND)
        for region, colors in PALETTES.items():
            style.configure(
                f"{region}.TFrame",
                background=colors["surface"],
                bordercolor=colors["border"],
            )
            style.configure(f"{region}.Inner.TFrame", background=colors["control"])
            style.configure(
                f"{region}.TLabel",
                background=colors["surface"],
                foreground=colors["text"],
            )
            style.configure(
                f"{region}.Title.TLabel",
                background=colors["surface"],
                foreground=colors["text"],
                font=(self.gui_font_family, 12, "bold"),
            )
            style.configure(
                f"{region}.Muted.TLabel",
                background=colors["surface"],
                foreground=colors["muted"],
                font=(self.gui_font_family, 9),
            )
            style.configure(
                f"{region}.Inner.TLabel",
                background=colors["control"],
                foreground=colors["text"],
            )
            style.configure(
                f"{region}.InnerMuted.TLabel",
                background=colors["control"],
                foreground=colors["muted"],
                font=(self.gui_font_family, 9),
            )
            style.configure(
                f"{region}.TButton",
                background=colors["control"],
                foreground=colors["accent"],
                bordercolor=colors["border"],
                padding=(11, 7),
            )
            style.map(
                f"{region}.TButton",
                background=[("active", colors["surface"])],
            )
            style.configure(
                f"{region}.TEntry",
                fieldbackground=colors["control"],
                foreground=colors["text"],
                bordercolor=colors["border"],
                lightcolor=colors["border"],
                darkcolor=colors["border"],
                padding=7,
            )
            style.configure(
                f"{region}.TCombobox",
                fieldbackground=colors["control"],
                background=colors["control"],
                foreground=colors["text"],
                bordercolor=colors["border"],
                arrowcolor=colors["accent"],
                padding=6,
            )
            style.map(
                f"{region}.TCombobox",
                fieldbackground=[("readonly", colors["control"])],
                selectbackground=[("readonly", colors["control"])],
                selectforeground=[("readonly", colors["text"])],
            )
        footer = PALETTES["Footer"]
        style.configure(
            "Primary.TButton",
            background=footer["accent"],
            foreground="#FFFFFF",
            borderwidth=0,
            padding=(23, 11),
            font=(self.gui_font_family, 10, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#6D624F"), ("disabled", "#B9B09F")],
            foreground=[("disabled", "#F3F0EA")],
        )
        style.configure(
            "Morandi.Horizontal.TProgressbar",
            background=footer["accent"],
            troughcolor=footer["control"],
            borderwidth=0,
        )

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame")
        shell.pack(fill=tk.BOTH, expand=True)

        footer = self._region_frame(shell, "Footer", padding=(22, 10, 22, 14))
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        footer.columnconfigure(0, weight=1)
        self._build_summary(footer).grid(row=0, column=0, sticky="ew")
        self._build_actions(footer).grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self.canvas = tk.Canvas(
            shell,
            bg=APP_BACKGROUND,
            borderwidth=0,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(shell, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        outer = ttk.Frame(self.canvas, padding=(22, 18, 22, 18), style="App.TFrame")
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=outer, anchor="nw"
        )
        outer.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        outer.columnconfigure(0, weight=1)

        self._build_header(outer).grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self._build_input_card(outer).grid(row=1, column=0, sticky="nsew")
        self._build_output_card(outer).grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self._build_rules_card(outer).grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self._build_advanced_card(outer).grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self._build_log(outer).grid(row=5, column=0, sticky="nsew", pady=(8, 0))

    def _on_content_configure(self, _event: tk.Event) -> None:
        if self._scroll_job is not None:
            self.root.after_cancel(self._scroll_job)
        self._scroll_job = self.root.after_idle(self._apply_scrollregion)

    def _apply_scrollregion(self) -> None:
        self._scroll_job = None
        bounds = self.canvas.bbox("all")
        if bounds is not None and bounds != self._last_scrollregion:
            self._last_scrollregion = bounds
            self.canvas.configure(scrollregion=bounds)

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._pending_width = event.width
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(32, self._apply_canvas_width)

    def _apply_canvas_width(self) -> None:
        self._resize_job = None
        if abs(self._pending_width - self._last_canvas_width) < 2:
            return
        self._last_canvas_width = self._pending_width
        self.canvas.itemconfigure(self.canvas_window, width=self._pending_width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        bounds = self.canvas.bbox("all")
        if bounds is None or bounds[3] <= self.canvas.winfo_height():
            return
        units = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(units * 3, "units")

    def _center_window(self, width: int, height: int) -> None:
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    @staticmethod
    def _region_frame(
        parent: tk.Misc,
        region: str,
        padding: tuple[int, ...] = (16, 13),
        inner: bool = False,
    ) -> ttk.Frame:
        infix = ".Inner" if inner else ""
        return ttk.Frame(
            parent,
            padding=padding,
            style=f"{region}{infix}.TFrame",
            borderwidth=1 if not inner else 0,
            relief="solid" if not inner else "flat",
        )

    def _section_heading(
        self, parent: ttk.Frame, region: str, number: str, title: str, description: str
    ) -> ttk.Frame:
        colors = PALETTES[region]
        heading = ttk.Frame(parent, style=f"{region}.TFrame")
        heading.columnconfigure(1, weight=1)
        tk.Label(
            heading,
            text=number,
            width=2,
            bg=colors["control"],
            fg=colors["accent"],
            font=(self.gui_font_family, 10, "bold"),
        ).grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 10))
        title_label = ttk.Label(heading, style=f"{region}.Title.TLabel")
        self._register_text(title_label, title)
        title_label.grid(row=0, column=1, sticky="w")
        description_label = ttk.Label(heading, style=f"{region}.Muted.TLabel")
        self._register_text(description_label, description)
        description_label.grid(row=1, column=1, sticky="w", pady=(2, 0))
        return heading

    def _build_header(self, parent: ttk.Frame) -> ttk.Frame:
        header = self._region_frame(parent, "Header", padding=(20, 15))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="Font Merger",
            style="Header.TLabel",
            font=(self.gui_font_family, 20, "bold"),
        ).grid(row=0, column=0, sticky="w")
        subtitle = ttk.Label(header, style="Header.Muted.TLabel")
        self._register_text(subtitle, "header_subtitle")
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))

        language_label = ttk.Label(header, style="Header.Muted.TLabel")
        self._register_text(language_label, "language")
        language_label.grid(row=0, column=1, sticky="e", padx=(15, 8))
        language = ttk.Combobox(
            header,
            textvariable=self.language_display,
            values=tuple(LANGUAGES.values()),
            state="readonly",
            width=12,
            style="Header.TCombobox",
        )
        language.grid(row=0, column=2, sticky="e")
        language.bind("<<ComboboxSelected>>", self._language_selected)
        ttk.Label(
            header,
            text=f"v{VERSION}",
            style="Header.TLabel",
            font=(self.gui_font_family, 9, "bold"),
        ).grid(row=1, column=2, sticky="e", pady=(4, 0))
        return header

    def _build_input_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = self._region_frame(parent, "Input")
        card.columnconfigure(0, weight=1)
        heading = self._section_heading(card, "Input", "1", "fonts_title", "fonts_desc")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(
            heading, textvariable=self.font_count, style="Input.Muted.TLabel"
        ).grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 0))

        inputs = self._region_frame(card, "Input", padding=(0,), inner=True)
        inputs.grid(row=1, column=0, sticky="nsew")
        inputs.columnconfigure(0, weight=1)
        colors = PALETTES["Input"]
        self.fonts = tk.Listbox(
            inputs,
            height=5,
            selectmode=tk.EXTENDED,
            borderwidth=1,
            relief="solid",
            bg=colors["control"],
            fg=colors["text"],
            selectbackground=colors["accent"],
            selectforeground="#FFFFFF",
            highlightthickness=0,
            font=(self.gui_font_family, 10),
            activestyle="none",
        )
        self.fonts.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(inputs, orient=tk.VERTICAL, command=self.fonts.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.fonts.configure(yscrollcommand=scrollbar.set)

        buttons = ttk.Frame(inputs, style="Input.Inner.TFrame")
        buttons.grid(row=0, column=2, sticky="ns", padx=(10, 0))
        add = ttk.Button(buttons, command=self.add_fonts, style="Input.TButton")
        self._register_text(add, "add_fonts")
        add.pack(fill="x")
        remove = ttk.Button(buttons, command=self.remove_fonts, style="Input.TButton")
        self._register_text(remove, "remove_selected")
        remove.pack(fill="x", pady=(6, 0))
        up = ttk.Button(
            buttons, command=lambda: self.move_font(-1), style="Input.TButton"
        )
        self._register_text(up, "move_up")
        up.pack(fill="x", pady=(12, 0))
        down = ttk.Button(
            buttons, command=lambda: self.move_font(1), style="Input.TButton"
        )
        self._register_text(down, "move_down")
        down.pack(fill="x", pady=(6, 0))
        return card

    def _build_output_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = self._region_frame(parent, "Output")
        card.columnconfigure(1, weight=3)
        card.columnconfigure(4, weight=2)
        self._section_heading(card, "Output", "2", "output_title", "output_desc").grid(
            row=0, column=0, columnspan=5, sticky="ew", pady=(0, 10)
        )
        output_label = ttk.Label(card, style="Output.TLabel")
        self._register_text(output_label, "output_file")
        output_label.grid(row=1, column=0, sticky="w")
        ttk.Entry(card, textvariable=self.output, style="Output.TEntry").grid(
            row=1, column=1, sticky="ew", padx=8
        )
        browse = ttk.Button(card, command=self.choose_output, style="Output.TButton")
        self._register_text(browse, "browse")
        browse.grid(row=1, column=2, sticky="w")
        family_label = ttk.Label(card, style="Output.TLabel")
        self._register_text(family_label, "family_optional")
        family_label.grid(row=1, column=3, sticky="w", padx=(18, 0))
        ttk.Entry(card, textvariable=self.family, style="Output.TEntry", width=22).grid(
            row=1, column=4, sticky="ew", padx=(8, 0)
        )
        return card

    def _build_rules_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = self._region_frame(parent, "Rules")
        for column in range(3):
            card.columnconfigure(column, weight=1, uniform="rule")
        heading = self._section_heading(card, "Rules", "3", "rules_title", "rules_desc")
        heading.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        reset = ttk.Button(
            heading, command=self.reset_recommended, style="Rules.TButton"
        )
        self._register_text(reset, "reset_recommended")
        reset.grid(row=0, column=2, rowspan=2, sticky="e")

        self._choice_panel(
            card,
            "glyph_title",
            "glyph_desc",
            self.priority,
            PRIORITY_CHOICES,
        ).grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self._choice_panel(
            card,
            "hint_title",
            "hint_desc",
            self.hinting,
            HINTING_CHOICES,
        ).grid(row=1, column=1, sticky="nsew", padx=3)
        weight_panel = self._choice_panel(
            card,
            "weights_title",
            "weights_desc",
            self.weights,
            WEIGHT_CHOICES,
        )
        weight_panel.grid(row=1, column=2, sticky="nsew", padx=(6, 0))
        missing = ttk.Label(weight_panel, style="Rules.InnerMuted.TLabel")
        self._register_text(missing, "missing_weight")
        missing.grid(row=3, column=0, sticky="w", pady=(9, 3))
        self._localized_choice(
            weight_panel,
            self.weight_match,
            MATCH_CHOICES,
            "Rules.TCombobox",
        ).grid(row=4, column=0, sticky="ew")
        return card

    def _choice_panel(
        self,
        parent: ttk.Frame,
        title: str,
        description: str,
        variable: tk.StringVar,
        choices: tuple[tuple[str, str], ...],
    ) -> ttk.Frame:
        panel = self._region_frame(parent, "Rules", padding=(12,), inner=True)
        panel.columnconfigure(0, weight=1)
        title_label = ttk.Label(
            panel,
            style="Rules.Inner.TLabel",
            font=(self.gui_font_family, 10, "bold"),
        )
        self._register_text(title_label, title)
        title_label.grid(row=0, column=0, sticky="w")
        description_label = ttk.Label(
            panel, style="Rules.InnerMuted.TLabel", wraplength=230
        )
        self._register_text(description_label, description)
        description_label.grid(row=1, column=0, sticky="w", pady=(3, 8))
        self._localized_choice(panel, variable, choices, "Rules.TCombobox").grid(
            row=2, column=0, sticky="ew"
        )
        return panel

    def _localized_choice(
        self,
        parent: tk.Misc,
        code_variable: tk.StringVar,
        choices: tuple[tuple[str, str], ...],
        style: str,
    ) -> ttk.Combobox:
        display = tk.StringVar()
        combo = ttk.Combobox(
            parent,
            textvariable=display,
            state="readonly",
            style=style,
        )
        binding = {
            "combo": combo,
            "display": display,
            "code": code_variable,
            "choices": choices,
        }
        self.choice_bindings.append(binding)
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _event, item=binding: self._choice_selected(item),
        )
        self._refresh_choice(binding)
        return combo

    def _choice_selected(self, binding: dict[str, Any]) -> None:
        selected = binding["display"].get()
        for key, code in binding["choices"]:
            if self.t(key) == selected:
                binding["code"].set(code)
                break

    def _refresh_choice(self, binding: dict[str, Any]) -> None:
        values = tuple(self.t(key) for key, _code in binding["choices"])
        binding["combo"].configure(values=values)
        code = binding["code"].get()
        for key, value in binding["choices"]:
            if value == code:
                binding["display"].set(self.t(key))
                return

    def _choice_label(self, code: str, choices: tuple[tuple[str, str], ...]) -> str:
        return next((self.t(key) for key, value in choices if value == code), code)

    def _build_advanced_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = self._region_frame(parent, "Advanced", padding=(14, 9))
        card.columnconfigure(0, weight=1)
        top = ttk.Frame(card, style="Advanced.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        self.advanced_button = ttk.Button(
            top, command=self.toggle_advanced, style="Advanced.TButton"
        )
        self.advanced_button.grid(row=0, column=0, sticky="w")
        description = ttk.Label(top, style="Advanced.Muted.TLabel")
        self._register_text(description, "advanced_desc")
        description.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.advanced_body = ttk.Frame(card, style="Advanced.TFrame")
        self.advanced_body.grid(row=1, column=0, sticky="ew", pady=(10, 2))
        self.advanced_body.grid_remove()
        self.advanced_body.columnconfigure(0, weight=1)
        self.advanced_body.columnconfigure(1, weight=1)
        fields = (
            ("custom_priority", self.custom_priority, "custom_priority_hint"),
            ("custom_hinting", self.custom_hinting, "custom_hinting_hint"),
            ("custom_weights", self.custom_weights, "custom_weights_hint"),
            ("max_gap", self.max_gap, "max_gap_hint"),
            ("fixed_instance", self.instance, "fixed_instance_hint"),
            ("variable_axes", self.axes, "variable_axes_hint"),
        )
        for index, (label, variable, hint) in enumerate(fields):
            row, side = divmod(index, 2)
            field = self._region_frame(
                self.advanced_body, "Advanced", padding=(10,), inner=True
            )
            field.grid(
                row=row,
                column=side,
                sticky="ew",
                padx=(0, 8) if side == 0 else (8, 0),
                pady=5,
            )
            field.columnconfigure(0, weight=1)
            label_widget = ttk.Label(field, style="Advanced.Inner.TLabel")
            self._register_text(label_widget, label)
            label_widget.grid(row=0, column=0, sticky="w")
            ttk.Entry(field, textvariable=variable, style="Advanced.TEntry").grid(
                row=1, column=0, sticky="ew", pady=(4, 2)
            )
            hint_widget = ttk.Label(field, style="Advanced.InnerMuted.TLabel")
            self._register_text(hint_widget, hint)
            hint_widget.grid(row=2, column=0, sticky="w")
        return card

    def _build_summary(self, parent: ttk.Frame) -> ttk.Frame:
        frame = self._region_frame(parent, "Footer", padding=(12, 9), inner=True)
        frame.columnconfigure(1, weight=1)
        label = ttk.Label(
            frame,
            style="Footer.Inner.TLabel",
            font=(self.gui_font_family, 9, "bold"),
        )
        self._register_text(label, "summary")
        label.grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Label(
            frame,
            textvariable=self.summary,
            style="Footer.Inner.TLabel",
            wraplength=740,
        ).grid(row=0, column=1, sticky="ew")
        return frame

    def _build_actions(self, parent: ttk.Frame) -> ttk.Frame:
        actions = ttk.Frame(parent, style="Footer.TFrame")
        actions.columnconfigure(1, weight=1)
        self.status_label = ttk.Label(
            actions, textvariable=self.status, style="Footer.TLabel"
        )
        self.status_label.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(
            actions, mode="indeterminate", style="Morandi.Horizontal.TProgressbar"
        )
        self.progress.grid(row=0, column=1, sticky="ew", padx=16)
        self.start_button = ttk.Button(
            actions,
            command=self.start,
            style="Primary.TButton",
            state=tk.DISABLED,
        )
        self._register_text(self.start_button, "start")
        self.start_button.grid(row=0, column=2)
        return actions

    def _build_log(self, parent: ttk.Frame) -> ttk.Frame:
        frame = self._region_frame(parent, "Log", padding=(14, 9))
        frame.columnconfigure(0, weight=1)
        self.log_button = ttk.Button(
            frame, command=self.toggle_log, style="Log.TButton"
        )
        self.log_button.grid(row=0, column=0, sticky="w")
        colors = PALETTES["Log"]
        self.log = tk.Text(
            frame,
            height=7,
            state=tk.DISABLED,
            wrap="word",
            bg=colors["control"],
            fg="#DDE3E1",
            insertbackground="#FFFFFF",
            borderwidth=0,
            padx=10,
            pady=8,
            font=(self.gui_font_family, 9),
        )
        self.log.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.log.grid_remove()
        return frame

    def _language_selected(self, _event: tk.Event) -> None:
        selected = self.language_display.get()
        locale_code = next(
            (code for code, label in LANGUAGES.items() if label == selected),
            self.locale,
        )
        if locale_code != self.locale:
            self.locale = locale_code
            self.refresh_language()

    def refresh_language(self) -> None:
        self.root.title(self.t("window_title", version=VERSION))
        for widget, key in self.localized_widgets:
            widget.configure(text=self.t(key))
        for binding in self.choice_bindings:
            self._refresh_choice(binding)
        self.language_display.set(LANGUAGES[self.locale])
        self._refresh_toggle_texts()
        self._refresh_font_count()
        self._refresh_status()
        self.update_summary()
        self._on_content_configure(tk.Event())

    def _refresh_toggle_texts(self) -> None:
        self.advanced_button.configure(
            text=self.t("advanced_hide" if self.advanced_visible else "advanced_show")
        )
        self.log_button.configure(
            text=self.t("log_hide" if self.log_visible else "log_show")
        )

    def _refresh_font_count(self) -> None:
        self.font_count.set(self.t("font_count", count=self.fonts.size()))

    def set_status(self, key: str, **values: object) -> None:
        self.status_key = key
        self.status_values = values
        self._refresh_status()

    def _refresh_status(self) -> None:
        self.status.set(self.t(self.status_key, **self.status_values))

    def reset_recommended(self) -> None:
        self.priority.set("auto")
        self.hinting.set("auto")
        self.weights.set("auto")
        self.weight_match.set("nearest")
        self.custom_priority.set("")
        self.custom_hinting.set("")
        self.custom_weights.set("")
        self.max_gap.set("")
        self.instance.set("")
        self.axes.set("")
        self.set_status("status_reset")
        self.status_label.configure(foreground=PALETTES["Footer"]["muted"])

    def toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced_body.grid()
        else:
            self.advanced_body.grid_remove()
        self._refresh_toggle_texts()

    def toggle_log(self, force_open: bool = False) -> None:
        visible = True if force_open else not self.log_visible
        if visible == self.log_visible:
            return
        self.log_visible = visible
        if visible:
            self.log.grid()
        else:
            self.log.grid_remove()
        self._refresh_toggle_texts()

    def update_summary(self, *_args: object) -> None:
        priority = self.custom_priority.get().strip() or self._choice_label(
            self.priority.get(), PRIORITY_CHOICES
        )
        hinting = self.custom_hinting.get().strip() or self._choice_label(
            self.hinting.get(), HINTING_CHOICES
        )
        weights = self.custom_weights.get().strip() or self._choice_label(
            self.weights.get(), WEIGHT_CHOICES
        )
        matching = self._choice_label(self.weight_match.get(), MATCH_CHOICES)
        details = [priority, hinting, weights, matching]
        if self.instance.get().strip():
            details.append(
                self.t("summary_instance", value=self.instance.get().strip())
            )
        if self.axes.get().strip():
            details.append(self.t("summary_axes", value=self.axes.get().strip()))
        self.summary.set("  ·  ".join(details))

    def update_font_state(self) -> None:
        count = self.fonts.size()
        self._refresh_font_count()
        self.status_label.configure(foreground=PALETTES["Footer"]["muted"])
        if count < 2:
            self.set_status("status_need_fonts")
            self.start_button.configure(state=tk.DISABLED)
        else:
            self.set_status("status_ready", count=count)
            self.start_button.configure(state=tk.NORMAL)

    def add_fonts(self) -> None:
        paths = filedialog.askopenfilenames(
            title=self.t("font_dialog_title"),
            filetypes=[
                (self.t("font_files"), "*.ttf *.otf *.ttc *.otc"),
                (self.t("all_files"), "*.*"),
            ],
        )
        for value in paths:
            path = Path(value)
            label = str(path)
            try:
                if is_collection(path):
                    faces = collection_faces(path)
                    if len(faces) > 1:
                        choices = "\n".join(
                            f"#{face.index}  {face.family} {face.style}"
                            for face in faces
                        )
                        index = simpledialog.askinteger(
                            self.t("collection_title"),
                            self.t(
                                "collection_prompt", name=path.name, choices=choices
                            ),
                            minvalue=0,
                            maxvalue=len(faces) - 1,
                            parent=self.root,
                        )
                        if index is None:
                            continue
                        label = f"{path}#{index}"
            except Exception as exc:
                messagebox.showerror(
                    self.t("font_read_error"), str(exc), parent=self.root
                )
                continue
            self.fonts.insert(tk.END, label)
        self.update_font_state()

    def remove_fonts(self) -> None:
        for index in reversed(self.fonts.curselection()):
            self.fonts.delete(index)
        self.update_font_state()

    def move_font(self, offset: int) -> None:
        selection = self.fonts.curselection()
        if len(selection) != 1:
            return
        index = selection[0]
        target = index + offset
        if target < 0 or target >= self.fonts.size():
            return
        value = self.fonts.get(index)
        self.fonts.delete(index)
        self.fonts.insert(target, value)
        self.fonts.selection_set(target)

    def choose_output(self) -> None:
        value = filedialog.asksaveasfilename(
            title=self.t("output_dialog_title"),
            defaultextension=".ttf",
            filetypes=[(self.t("ttf_file"), "*.ttf")],
            initialfile=Path(self.output.get()).name,
        )
        if value:
            self.output.set(value)

    def start(self) -> None:
        font_values = list(self.fonts.get(0, tk.END))
        if len(font_values) < 2:
            messagebox.showwarning(
                self.t("missing_fonts_title"),
                self.t("missing_fonts_text"),
                parent=self.root,
            )
            return
        if not self.output.get().strip():
            messagebox.showwarning(
                self.t("missing_output_title"),
                self.t("missing_output_text"),
                parent=self.root,
            )
            return
        try:
            max_gap = int(self.max_gap.get()) if self.max_gap.get().strip() else None
            axis_values = [
                item for item in re.split(r"[,;\s]+", self.axes.get().strip()) if item
            ]
            axes = parse_axis(axis_values)
            sources = [parse_source(value) for value in font_values]
        except (ValueError, FontMergerError) as exc:
            messagebox.showerror(self.t("parameter_error"), str(exc), parent=self.root)
            return

        self.start_button.configure(state=tk.DISABLED)
        self.progress.start(12)
        self.set_status("status_running")
        self.status_label.configure(foreground=PALETTES["Footer"]["accent"])
        self.toggle_log(force_open=True)
        self.append_log(self.t("task_start"))
        kwargs = {
            "sources": sources,
            "output": Path(self.output.get()),
            "family": self.family.get().strip() or None,
            "axes": axes,
            "priority": self.custom_priority.get().strip() or self.priority.get(),
            "hinting_source": self.custom_hinting.get().strip() or self.hinting.get(),
            "instance": self.instance.get().strip() or None,
            "weights": self.custom_weights.get().strip() or self.weights.get(),
            "weight_match": self.weight_match.get(),
            "max_weight_gap": max_gap,
        }
        threading.Thread(target=self.run_merge, kwargs=kwargs, daemon=True).start()

    def run_merge(self, **kwargs: object) -> None:
        try:
            results = merge_font_family(**kwargs)
            self.events.put(("done", results))
        except Exception as exc:
            self.events.put(("error", exc))

    def localize_core_log(self, payload: object) -> str | None:
        level, template, arguments, formatted = payload
        if self.locale == "zh_CN":
            return str(formatted)
        localized = CORE_LOG_TEXT.get(str(template), {}).get(self.locale)
        if localized is None:
            return None
        try:
            message = localized % arguments if arguments else localized
        except (TypeError, ValueError):
            message = localized
        return f"[{level}] {message}"

    def poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "log":
                    message = self.localize_core_log(payload)
                    if message is not None:
                        self.append_log(message)
                elif event == "done":
                    results = payload
                    assert isinstance(results, list)
                    for result in results:
                        self.append_log(self.t("completed_path", path=result.path))
                    self.set_status("status_done", count=len(results))
                    self.status_label.configure(foreground=SUCCESS)
                    self.finish()
                    messagebox.showinfo(
                        self.t("done_title"),
                        self.t("done_text", count=len(results)),
                        parent=self.root,
                    )
                elif event == "error":
                    error_message = (
                        str(payload)
                        if self.locale == "zh_CN"
                        else self.t("engine_error_generic")
                    )
                    self.append_log(f"[ERROR] {error_message}")
                    self.set_status("status_error")
                    self.status_label.configure(foreground=DANGER)
                    self.finish()
                    messagebox.showerror(
                        self.t("error_title"), error_message, parent=self.root
                    )
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    def append_log(self, message: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def finish(self) -> None:
        self.progress.stop()
        self.start_button.configure(
            state=tk.NORMAL if self.fonts.size() >= 2 else tk.DISABLED
        )

    def close(self) -> None:
        LOG.removeHandler(self.log_handler)
        self.canvas.unbind_all("<MouseWheel>")
        unregister_private_font(self._registered_gui_font)
        self.root.destroy()


def main() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    FontMergerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
