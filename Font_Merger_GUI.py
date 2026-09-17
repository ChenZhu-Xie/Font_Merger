#!/usr/bin/env python3
"""Small Tk GUI for Font Merger's standalone Windows executable."""

from __future__ import annotations

import logging
import queue
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

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


COLORS = {
    "background": "#F3F6FA",
    "surface": "#FFFFFF",
    "surface_muted": "#F7F9FC",
    "border": "#DCE3EC",
    "text": "#172033",
    "muted": "#667085",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_soft": "#E8F0FF",
    "success": "#087A55",
    "success_soft": "#E8F7F1",
    "danger": "#B42318",
}

PRIORITY_OPTIONS = {
    "自动识别（推荐）": "auto",
    "按字体列表顺序": "input",
    "第 1 个优先": "1,2",
    "第 2 个优先": "2,1",
}
HINTING_OPTIONS = {
    "跟随字符来源（推荐）": "auto",
    "优先保持西文": "latin",
    "优先保持中文 / CJK": "cjk",
    "移除 Hinting": "none",
}
WEIGHT_OPTIONS = {
    "采用字重更多的一侧（推荐）": "auto",
    "采用西文字重": "latin",
    "采用中文 / CJK 字重": "cjk",
    "合并双方全部字重": "union",
    "仅双方共有字重": "intersection",
}
MATCH_OPTIONS = {
    "使用最接近字重（推荐）": "nearest",
    "必须精确匹配": "exact",
}


class QueueLogHandler(logging.Handler):
    def __init__(self, events: queue.Queue[tuple[str, object]]) -> None:
        super().__init__()
        self.events = events

    def emit(self, record: logging.LogRecord) -> None:
        self.events.put(("log", self.format(record)))


class FontMergerGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.root.title(f"Font Merger {VERSION}")
        self.root.minsize(820, 720)
        self.root.configure(background=COLORS["background"])
        self._configure_styles()
        self._center_window(920, 820)

        self.output = tk.StringVar(value=str(Path.cwd() / "merged.ttf"))
        self.family = tk.StringVar()
        self.priority = tk.StringVar(value=next(iter(PRIORITY_OPTIONS)))
        self.hinting = tk.StringVar(value=next(iter(HINTING_OPTIONS)))
        self.weights = tk.StringVar(value=next(iter(WEIGHT_OPTIONS)))
        self.weight_match = tk.StringVar(value=next(iter(MATCH_OPTIONS)))
        self.custom_priority = tk.StringVar()
        self.custom_hinting = tk.StringVar()
        self.custom_weights = tk.StringVar()
        self.max_gap = tk.StringVar()
        self.instance = tk.StringVar()
        self.axes = tk.StringVar()
        self.summary = tk.StringVar()
        self.status = tk.StringVar(value="请先添加至少两个字体")
        self.font_count = tk.StringVar(value="0 个字体")
        self.advanced_visible = False
        self.log_visible = False

        shell = ttk.Frame(root, style="App.TFrame")
        shell.pack(fill=tk.BOTH, expand=True)

        footer = ttk.Frame(shell, padding=(22, 10, 22, 14), style="Surface.TFrame")
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        footer.columnconfigure(0, weight=1)
        self._build_summary(footer).grid(row=0, column=0, sticky="ew")
        self._build_actions(footer).grid(row=1, column=0, sticky="ew", pady=(10, 0))

        self.canvas = tk.Canvas(
            shell,
            bg=COLORS["background"],
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
        outer.rowconfigure(1, weight=2)
        outer.rowconfigure(5, weight=1)

        self._build_header(outer).grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self._build_input_card(outer).grid(row=1, column=0, sticky="nsew")
        self._build_output_card(outer).grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self._build_rules_card(outer).grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self._build_advanced_card(outer).grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self._build_log(outer).grid(row=5, column=0, sticky="nsew", pady=(8, 0))

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
        self.update_summary()

        handler = QueueLogHandler(self.events)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        LOG.addHandler(handler)
        LOG.setLevel(logging.INFO)
        logging.getLogger("fontTools").setLevel(logging.ERROR)
        self.root.after(100, self.poll_events)

    def _on_content_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self.canvas.bbox("all") is None:
            return
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        base_font = ("Segoe UI", 10)
        style.configure(
            ".",
            font=base_font,
            background=COLORS["background"],
            foreground=COLORS["text"],
        )
        style.configure("App.TFrame", background=COLORS["background"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Muted.TFrame", background=COLORS["surface_muted"])
        style.configure(
            "Surface.TLabel", background=COLORS["surface"], foreground=COLORS["text"]
        )
        style.configure(
            "Muted.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure(
            "Section.TLabel",
            background=COLORS["surface"],
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 12),
        )
        style.configure(
            "Primary.TButton",
            background=COLORS["accent"],
            foreground="#FFFFFF",
            borderwidth=0,
            padding=(22, 11),
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", COLORS["accent_hover"]),
                ("disabled", "#9DB7EB"),
            ],
            foreground=[("disabled", "#EFF4FF")],
        )
        style.configure(
            "Secondary.TButton",
            background=COLORS["surface"],
            foreground=COLORS["accent"],
            bordercolor=COLORS["border"],
            padding=(12, 7),
        )
        style.map("Secondary.TButton", background=[("active", COLORS["accent_soft"])])
        style.configure(
            "Quiet.TButton",
            background=COLORS["surface"],
            foreground=COLORS["muted"],
            borderwidth=0,
            padding=(8, 5),
        )
        style.map("Quiet.TButton", foreground=[("active", COLORS["accent"])])
        style.configure(
            "TEntry",
            fieldbackground="#FFFFFF",
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            padding=7,
        )
        style.configure(
            "TCombobox",
            fieldbackground="#FFFFFF",
            background="#FFFFFF",
            bordercolor=COLORS["border"],
            padding=6,
        )
        style.configure(
            "Accent.Horizontal.TProgressbar",
            background=COLORS["accent"],
            troughcolor=COLORS["accent_soft"],
            borderwidth=0,
        )

    def _center_window(self, width: int, height: int) -> None:
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _card(
        self, parent: ttk.Frame, padding: tuple[int, ...] = (16, 13)
    ) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=padding, style="Surface.TFrame")
        return frame

    def _section_heading(
        self, parent: ttk.Frame, number: str, title: str, description: str
    ) -> ttk.Frame:
        heading = ttk.Frame(parent, style="Surface.TFrame")
        heading.columnconfigure(1, weight=1)
        badge = tk.Label(
            heading,
            text=number,
            width=2,
            height=1,
            bg=COLORS["accent_soft"],
            fg=COLORS["accent"],
            font=("Segoe UI Semibold", 10),
        )
        badge.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 10))
        ttk.Label(heading, text=title, style="Section.TLabel").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(heading, text=description, style="Muted.TLabel").grid(
            row=1, column=1, sticky="w", pady=(2, 0)
        )
        return heading

    def _build_header(self, parent: ttk.Frame) -> tk.Frame:
        header = tk.Frame(parent, bg="#152238", padx=20, pady=16)
        header.columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="Font Merger",
            bg="#152238",
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 20),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="把西文与中文字体合并为开箱即用的完整字体家族",
            bg="#152238",
            fg="#BFD0EA",
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        tk.Label(
            header,
            text=f"v{VERSION}",
            bg="#263A59",
            fg="#DCE9FF",
            padx=10,
            pady=4,
            font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=1, rowspan=2, sticky="e")
        return header

    def _build_input_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = self._card(parent)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        heading = self._section_heading(
            card,
            "1",
            "选择字体",
            "至少添加两个字体；TTC / OTC 会提示选择其中的字体。",
        )
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(heading, textvariable=self.font_count, style="Muted.TLabel").grid(
            row=0, column=2, rowspan=2, sticky="e", padx=(12, 0)
        )

        inputs = ttk.Frame(card, style="Surface.TFrame")
        inputs.grid(row=1, column=0, columnspan=2, sticky="nsew")
        inputs.columnconfigure(0, weight=1)
        inputs.rowconfigure(0, weight=1)
        self.fonts = tk.Listbox(
            inputs,
            height=5,
            selectmode=tk.EXTENDED,
            borderwidth=1,
            relief="solid",
            bg=COLORS["surface_muted"],
            fg=COLORS["text"],
            selectbackground=COLORS["accent"],
            selectforeground="#FFFFFF",
            highlightthickness=0,
            font=("Segoe UI", 10),
            activestyle="none",
        )
        self.fonts.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(inputs, orient=tk.VERTICAL, command=self.fonts.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.fonts.configure(yscrollcommand=scrollbar.set)

        input_buttons = ttk.Frame(inputs, style="Surface.TFrame")
        input_buttons.grid(row=0, column=2, sticky="ns", padx=(10, 0))
        ttk.Button(
            input_buttons,
            text="＋ 添加字体",
            command=self.add_fonts,
            style="Secondary.TButton",
        ).pack(fill="x")
        ttk.Button(
            input_buttons,
            text="移除所选",
            command=self.remove_fonts,
            style="Quiet.TButton",
        ).pack(fill="x", pady=(6, 0))
        ttk.Separator(input_buttons).pack(fill="x", pady=8)
        ttk.Button(
            input_buttons,
            text="↑ 上移",
            command=lambda: self.move_font(-1),
            style="Quiet.TButton",
        ).pack(fill="x")
        ttk.Button(
            input_buttons,
            text="↓ 下移",
            command=lambda: self.move_font(1),
            style="Quiet.TButton",
        ).pack(fill="x", pady=(4, 0))
        return card

    def _build_output_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = self._card(parent)
        card.columnconfigure(1, weight=3)
        card.columnconfigure(4, weight=2)
        self._section_heading(
            card,
            "2",
            "设置输出",
            "多字重会自动在文件名后添加 Thin、Regular、Bold 等样式名。",
        ).grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 10))
        ttk.Label(card, text="输出文件", style="Surface.TLabel").grid(
            row=1, column=0, sticky="w"
        )
        ttk.Entry(card, textvariable=self.output).grid(
            row=1, column=1, sticky="ew", padx=(8, 8)
        )
        ttk.Button(
            card,
            text="浏览…",
            command=self.choose_output,
            style="Secondary.TButton",
        ).grid(row=1, column=2, sticky="w")
        ttk.Label(card, text="家族名（可选）", style="Surface.TLabel").grid(
            row=1, column=3, sticky="w", padx=(18, 0)
        )
        ttk.Entry(card, textvariable=self.family, width=22).grid(
            row=1, column=4, sticky="ew", padx=(8, 0)
        )
        return card

    def _build_rules_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = self._card(parent)
        for column in range(3):
            card.columnconfigure(column, weight=1, uniform="rule")
        heading = self._section_heading(
            card,
            "3",
            "选择合并策略",
            "下面三项彼此独立。保持推荐值即可完成常见的中西文字体合并。",
        )
        heading.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        ttk.Button(
            heading,
            text="恢复推荐设置",
            command=self.reset_recommended,
            style="Quiet.TButton",
        ).grid(row=0, column=2, rowspan=2, sticky="e")

        self._choice_panel(
            card,
            "字符覆盖",
            "重复字符使用哪一款字体",
            self.priority,
            tuple(PRIORITY_OPTIONS),
        ).grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self._choice_panel(
            card,
            "显示清晰度",
            "选择整份字体的 Hinting 来源",
            self.hinting,
            tuple(HINTING_OPTIONS),
        ).grid(row=1, column=1, sticky="nsew", padx=3)
        weight_panel = self._choice_panel(
            card,
            "输出字重",
            "决定生成哪些 Thin / Bold 等文件",
            self.weights,
            tuple(WEIGHT_OPTIONS),
        )
        weight_panel.grid(row=1, column=2, sticky="nsew", padx=(6, 0))
        ttk.Label(weight_panel, text="缺失字重", style="Muted.TLabel").grid(
            row=3, column=0, sticky="w", pady=(9, 3)
        )
        ttk.Combobox(
            weight_panel,
            textvariable=self.weight_match,
            values=tuple(MATCH_OPTIONS),
            state="readonly",
        ).grid(row=4, column=0, sticky="ew")
        return card

    def _choice_panel(
        self,
        parent: ttk.Frame,
        title: str,
        description: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
    ) -> ttk.Frame:
        panel = ttk.Frame(parent, padding=12, style="Muted.TFrame")
        panel.columnconfigure(0, weight=1)
        ttk.Label(
            panel,
            text=title,
            background=COLORS["surface_muted"],
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 10),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            panel,
            text=description,
            background=COLORS["surface_muted"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 9),
            wraplength=220,
        ).grid(row=1, column=0, sticky="w", pady=(3, 8))
        ttk.Combobox(
            panel, textvariable=variable, values=values, state="readonly"
        ).grid(row=2, column=0, sticky="ew")
        return panel

    def _build_advanced_card(self, parent: ttk.Frame) -> ttk.Frame:
        card = self._card(parent, (14, 9))
        card.columnconfigure(0, weight=1)
        top = ttk.Frame(card, style="Surface.TFrame")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        self.advanced_button = ttk.Button(
            top,
            text="▸ 显示高级设置",
            command=self.toggle_advanced,
            style="Quiet.TButton",
        )
        self.advanced_button.grid(row=0, column=0, sticky="w")
        ttk.Label(
            top,
            text="自定义顺序、字重数值、实例和可变轴",
            style="Muted.TLabel",
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.advanced_body = ttk.Frame(card, style="Surface.TFrame")
        self.advanced_body.grid(row=1, column=0, sticky="ew", pady=(10, 2))
        self.advanced_body.grid_remove()
        for column in (0, 1):
            self.advanced_body.columnconfigure(column, weight=1)
        advanced_fields = (
            ("字符顺序", self.custom_priority, "例如 2,1,3"),
            ("Hinting 字体序号", self.custom_hinting, "例如 2"),
            ("自定义字重", self.custom_weights, "例如 300,400,700"),
            ("最大字重差", self.max_gap, "留空表示不限制"),
            ("固定单一实例", self.instance, "例如 Bold"),
            ("可变轴坐标", self.axes, "例如 wdth=90,slnt=-10"),
        )
        for index, (label, variable, hint) in enumerate(advanced_fields):
            row, side = divmod(index, 2)
            field = ttk.Frame(self.advanced_body, style="Surface.TFrame")
            field.grid(
                row=row,
                column=side,
                sticky="ew",
                padx=(0, 18) if side == 0 else (0, 0),
                pady=5,
            )
            field.columnconfigure(0, weight=1)
            ttk.Label(field, text=label, style="Surface.TLabel").grid(
                row=0, column=0, sticky="w"
            )
            ttk.Entry(field, textvariable=variable).grid(
                row=1, column=0, sticky="ew", pady=(4, 2)
            )
            ttk.Label(
                field,
                text=hint,
                style="Muted.TLabel",
            ).grid(row=2, column=0, sticky="w")
        return card

    def _build_summary(self, parent: ttk.Frame) -> tk.Frame:
        frame = tk.Frame(
            parent,
            bg=COLORS["accent_soft"],
            padx=14,
            pady=10,
            highlightthickness=1,
            highlightbackground="#C9D9FA",
        )
        frame.columnconfigure(1, weight=1)
        tk.Label(
            frame,
            text="当前方案",
            bg=COLORS["accent_soft"],
            fg=COLORS["accent"],
            font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        tk.Label(
            frame,
            textvariable=self.summary,
            bg=COLORS["accent_soft"],
            fg=COLORS["text"],
            font=("Segoe UI", 10),
            anchor="w",
            wraplength=700,
            justify="left",
        ).grid(row=0, column=1, sticky="ew")
        return frame

    def _build_actions(self, parent: ttk.Frame) -> ttk.Frame:
        actions = ttk.Frame(parent, style="Surface.TFrame")
        actions.columnconfigure(1, weight=1)
        self.status_label = ttk.Label(
            actions,
            textvariable=self.status,
            foreground=COLORS["muted"],
            background=COLORS["surface"],
        )
        self.status_label.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(
            actions, mode="indeterminate", style="Accent.Horizontal.TProgressbar"
        )
        self.progress.grid(row=0, column=1, sticky="ew", padx=16)
        self.start_button = ttk.Button(
            actions,
            text="开始合并字体",
            command=self.start,
            style="Primary.TButton",
            state=tk.DISABLED,
        )
        self.start_button.grid(row=0, column=2)
        return actions

    def _build_log(self, parent: ttk.Frame) -> ttk.Frame:
        frame = ttk.Frame(parent, style="App.TFrame")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        self.log_button = ttk.Button(
            frame,
            text="▸ 查看运行记录",
            command=self.toggle_log,
            style="Quiet.TButton",
        )
        self.log_button.grid(row=0, column=0, sticky="w")
        self.log = tk.Text(
            frame,
            height=7,
            state=tk.DISABLED,
            wrap="word",
            bg="#101828",
            fg="#D0D5DD",
            insertbackground="#FFFFFF",
            borderwidth=0,
            padx=10,
            pady=8,
            font=("Cascadia Mono", 9),
        )
        self.log.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.log.grid_remove()
        return frame

    @staticmethod
    def _option_value(variable: tk.StringVar, options: dict[str, str]) -> str:
        value = variable.get().strip()
        return options.get(value, value)

    def reset_recommended(self) -> None:
        self.priority.set(next(iter(PRIORITY_OPTIONS)))
        self.hinting.set(next(iter(HINTING_OPTIONS)))
        self.weights.set(next(iter(WEIGHT_OPTIONS)))
        self.weight_match.set(next(iter(MATCH_OPTIONS)))
        self.custom_priority.set("")
        self.custom_hinting.set("")
        self.custom_weights.set("")
        self.max_gap.set("")
        self.instance.set("")
        self.axes.set("")
        self.status.set("已恢复推荐设置")
        self.status_label.configure(foreground=COLORS["muted"])

    def toggle_advanced(self) -> None:
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced_body.grid()
            self.advanced_button.configure(text="▾ 收起高级设置")
        else:
            self.advanced_body.grid_remove()
            self.advanced_button.configure(text="▸ 显示高级设置")

    def toggle_log(self, force_open: bool = False) -> None:
        visible = True if force_open else not self.log_visible
        if visible == self.log_visible:
            return
        self.log_visible = visible
        if visible:
            self.log.grid()
            self.log_button.configure(text="▾ 收起运行记录")
        else:
            self.log.grid_remove()
            self.log_button.configure(text="▸ 查看运行记录")

    def update_summary(self, *_args: object) -> None:
        priority = self.custom_priority.get().strip() or self.priority.get()
        hinting = self.custom_hinting.get().strip() or self.hinting.get()
        weights = self.custom_weights.get().strip() or self.weights.get()
        matching = self.weight_match.get()
        details = [priority, hinting, weights, matching]
        if self.instance.get().strip():
            details.append(f"固定 {self.instance.get().strip()} 实例")
        if self.axes.get().strip():
            details.append(f"轴 {self.axes.get().strip()}")
        self.summary.set("  ·  ".join(details))

    def update_font_state(self) -> None:
        count = self.fonts.size()
        self.font_count.set(f"{count} 个字体")
        self.status_label.configure(foreground=COLORS["muted"])
        if count < 2:
            self.status.set("请先添加至少两个字体")
            self.start_button.configure(state=tk.DISABLED)
        else:
            self.status.set(f"已选择 {count} 个字体，可以开始合并")
            self.start_button.configure(state=tk.NORMAL)

    def add_fonts(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择字体",
            filetypes=[
                ("字体文件", "*.ttf *.otf *.ttc *.otc"),
                ("所有文件", "*.*"),
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
                            "选择集合字体",
                            f"{path.name} 包含：\n\n{choices}\n\n请输入序号：",
                            minvalue=0,
                            maxvalue=len(faces) - 1,
                            parent=self.root,
                        )
                        if index is None:
                            continue
                        label = f"{path}#{index}"
            except Exception as exc:
                messagebox.showerror("无法读取字体", str(exc), parent=self.root)
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
            title="选择输出文件名基准",
            defaultextension=".ttf",
            filetypes=[("TrueType 字体", "*.ttf")],
            initialfile=Path(self.output.get()).name,
        )
        if value:
            self.output.set(value)

    def start(self) -> None:
        font_values = list(self.fonts.get(0, tk.END))
        if len(font_values) < 2:
            messagebox.showwarning("缺少字体", "请至少添加两个字体。", parent=self.root)
            return
        if not self.output.get().strip():
            messagebox.showwarning("缺少输出", "请选择输出文件。", parent=self.root)
            return
        try:
            max_gap = int(self.max_gap.get()) if self.max_gap.get().strip() else None
            axis_values = [
                item for item in re.split(r"[,;\s]+", self.axes.get().strip()) if item
            ]
            axes = parse_axis(axis_values)
            sources = [parse_source(value) for value in font_values]
        except (ValueError, FontMergerError) as exc:
            messagebox.showerror("参数错误", str(exc), parent=self.root)
            return

        self.start_button.configure(state=tk.DISABLED)
        self.progress.start(12)
        self.status.set("正在分析并合并字体…")
        self.status_label.configure(foreground=COLORS["accent"])
        self.toggle_log(force_open=True)
        self.append_log("──────── 开始新的合并任务 ────────")
        priority = self.custom_priority.get().strip() or self._option_value(
            self.priority, PRIORITY_OPTIONS
        )
        hinting = self.custom_hinting.get().strip() or self._option_value(
            self.hinting, HINTING_OPTIONS
        )
        weights = self.custom_weights.get().strip() or self._option_value(
            self.weights, WEIGHT_OPTIONS
        )
        kwargs = {
            "sources": sources,
            "output": Path(self.output.get()),
            "family": self.family.get().strip() or None,
            "axes": axes,
            "priority": priority,
            "hinting_source": hinting,
            "instance": self.instance.get().strip() or None,
            "weights": weights,
            "weight_match": self._option_value(self.weight_match, MATCH_OPTIONS),
            "max_weight_gap": max_gap,
        }
        threading.Thread(target=self.run_merge, kwargs=kwargs, daemon=True).start()

    def run_merge(self, **kwargs: object) -> None:
        try:
            results = merge_font_family(**kwargs)
            self.events.put(("done", results))
        except Exception as exc:
            self.events.put(("error", exc))

    def poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "log":
                    self.append_log(str(payload))
                elif event == "done":
                    results = payload
                    assert isinstance(results, list)
                    for result in results:
                        self.append_log(f"完成：{result.path}")
                    self.status.set(f"合并完成 · 已生成 {len(results)} 个字体")
                    self.status_label.configure(foreground=COLORS["success"])
                    self.finish()
                    messagebox.showinfo(
                        "合并完成",
                        f"已生成 {len(results)} 个字体。",
                        parent=self.root,
                    )
                elif event == "error":
                    self.append_log(f"[ERROR] {payload}")
                    self.status.set("合并失败，请查看运行记录")
                    self.status_label.configure(foreground=COLORS["danger"])
                    self.finish()
                    messagebox.showerror("合并失败", str(payload), parent=self.root)
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


def main() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    FontMergerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
