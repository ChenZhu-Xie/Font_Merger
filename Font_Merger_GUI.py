#!/usr/bin/env python3
"""Small Tk GUI for Font Merger's standalone Windows executable."""

from __future__ import annotations

import logging
import queue
import re
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
        self.root.minsize(760, 650)

        outer = ttk.Frame(root, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        outer.rowconfigure(5, weight=1)

        ttk.Label(
            outer,
            text="添加要合并的字体。西文 + 中文组合会自动让西文字形优先。",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        inputs = ttk.Frame(outer)
        inputs.grid(row=1, column=0, sticky="nsew")
        inputs.columnconfigure(0, weight=1)
        inputs.rowconfigure(0, weight=1)
        self.fonts = tk.Listbox(inputs, height=7, selectmode=tk.EXTENDED)
        self.fonts.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(inputs, orient=tk.VERTICAL, command=self.fonts.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.fonts.configure(yscrollcommand=scrollbar.set)

        input_buttons = ttk.Frame(inputs)
        input_buttons.grid(row=0, column=2, sticky="ns", padx=(8, 0))
        ttk.Button(input_buttons, text="添加字体…", command=self.add_fonts).pack(
            fill="x"
        )
        ttk.Button(input_buttons, text="移除", command=self.remove_fonts).pack(
            fill="x", pady=(6, 0)
        )
        ttk.Button(input_buttons, text="上移", command=lambda: self.move_font(-1)).pack(
            fill="x", pady=(14, 0)
        )
        ttk.Button(input_buttons, text="下移", command=lambda: self.move_font(1)).pack(
            fill="x", pady=(6, 0)
        )

        output_frame = ttk.LabelFrame(outer, text="输出", padding=10)
        output_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        output_frame.columnconfigure(1, weight=1)
        self.output = tk.StringVar(value=str(Path.cwd() / "merged.ttf"))
        self.family = tk.StringVar()
        ttk.Label(output_frame, text="文件名基准").grid(row=0, column=0, sticky="w")
        ttk.Entry(output_frame, textvariable=self.output).grid(
            row=0, column=1, sticky="ew", padx=8
        )
        ttk.Button(output_frame, text="选择…", command=self.choose_output).grid(
            row=0, column=2
        )
        ttk.Label(output_frame, text="字体家族名").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Entry(output_frame, textvariable=self.family).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(8, 0), pady=(8, 0)
        )

        settings = ttk.LabelFrame(outer, text="合并规则（各项互不影响）", padding=10)
        settings.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)

        self.priority = tk.StringVar(value="auto")
        self.hinting = tk.StringVar(value="auto")
        self.weights = tk.StringVar(value="auto")
        self.weight_match = tk.StringVar(value="nearest")
        self.max_gap = tk.StringVar()
        self.instance = tk.StringVar()
        self.axes = tk.StringVar()

        self._combo_row(
            settings,
            0,
            "重叠字符来源",
            self.priority,
            ("auto", "input", "1,2", "2,1"),
            "Hinting 来源",
            self.hinting,
            ("auto", "latin", "cjk", "none", "1", "2"),
        )
        self._combo_row(
            settings,
            1,
            "生成哪些字重",
            self.weights,
            ("auto", "latin", "cjk", "union", "intersection", "400,700"),
            "缺失字重处理",
            self.weight_match,
            ("nearest", "exact"),
        )

        ttk.Label(settings, text="最大字重差").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(settings, textvariable=self.max_gap, width=18).grid(
            row=2, column=1, sticky="ew", padx=(8, 18), pady=5
        )
        ttk.Label(settings, text="固定单一实例").grid(
            row=2, column=2, sticky="w", pady=5
        )
        ttk.Entry(settings, textvariable=self.instance).grid(
            row=2, column=3, sticky="ew", padx=(8, 0), pady=5
        )
        ttk.Label(settings, text="高级轴坐标").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(settings, textvariable=self.axes).grid(
            row=3, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=5
        )
        ttk.Label(
            settings,
            text=(
                "auto 默认采用字重最丰富的一侧；nearest 用最接近字重补齐。"
                "填写固定实例或 wght=数值时只生成一个字体。"
            ),
            foreground="#555555",
            wraplength=700,
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=4, column=0, sticky="ew", pady=12)
        actions.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(actions, mode="indeterminate")
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.start_button = ttk.Button(actions, text="开始合并", command=self.start)
        self.start_button.grid(row=0, column=1)

        self.log = tk.Text(outer, height=10, state=tk.DISABLED, wrap="word")
        self.log.grid(row=5, column=0, sticky="nsew")

        handler = QueueLogHandler(self.events)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        LOG.addHandler(handler)
        LOG.setLevel(logging.INFO)
        logging.getLogger("fontTools").setLevel(logging.ERROR)
        self.root.after(100, self.poll_events)

    @staticmethod
    def _combo_row(
        parent: ttk.Frame,
        row: int,
        left_label: str,
        left_var: tk.StringVar,
        left_values: tuple[str, ...],
        right_label: str,
        right_var: tk.StringVar,
        right_values: tuple[str, ...],
    ) -> None:
        ttk.Label(parent, text=left_label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Combobox(parent, textvariable=left_var, values=left_values).grid(
            row=row, column=1, sticky="ew", padx=(8, 18), pady=5
        )
        ttk.Label(parent, text=right_label).grid(row=row, column=2, sticky="w", pady=5)
        ttk.Combobox(parent, textvariable=right_var, values=right_values).grid(
            row=row, column=3, sticky="ew", padx=(8, 0), pady=5
        )

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

    def remove_fonts(self) -> None:
        for index in reversed(self.fonts.curselection()):
            self.fonts.delete(index)

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
        self.append_log("开始合并…")
        kwargs = {
            "sources": sources,
            "output": Path(self.output.get()),
            "family": self.family.get().strip() or None,
            "axes": axes,
            "priority": self.priority.get().strip() or "auto",
            "hinting_source": self.hinting.get().strip() or "auto",
            "instance": self.instance.get().strip() or None,
            "weights": self.weights.get().strip() or "auto",
            "weight_match": self.weight_match.get().strip() or "nearest",
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
                    self.finish()
                    messagebox.showinfo(
                        "合并完成",
                        f"已生成 {len(results)} 个字体。",
                        parent=self.root,
                    )
                elif event == "error":
                    self.append_log(f"[ERROR] {payload}")
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
        self.start_button.configure(state=tk.NORMAL)


def main() -> None:
    root = tk.Tk()
    FontMergerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
