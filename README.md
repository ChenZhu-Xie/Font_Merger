# Font_Merger

将 🀄️:🦜（= 2:1 的等宽）双字体并集（纯英字体所有字符，覆盖中文字体中的对应部分），生成中 + 英双语单字体。

- Vscode 效果：
<img width="2375" height="1485" alt="image" src="https://github.com/user-attachments/assets/aa372e72-b045-4001-97ad-668e82db3af8" />

- Sublime 效果：
<img width="2442" height="1538" alt="image" src="https://github.com/user-attachments/assets/fcc89898-a2df-4936-b238-2726e244f963" />

- SilverBullet 效果：
<img width="2700" height="1811" alt="image" src="https://github.com/user-attachments/assets/d542753d-c39a-48a2-a116-387369416237" />

## 项目简介

**Font_Merger** 是一个字体合并工具，用于生成中英文（等宽）混排字体家族。

作为示例，它将 Inconsolata 的 1 等宽西文字符与 LXGW Bright 的 2 等宽中文字符，拼合成一个统一的英:中 = 1:2 等宽字体，并支持多字重和样式（Regular、Medium、Bold、Italic 等）。

- 合并一款西文字体和一款中文字体时，会自动让西文字体覆盖重复字符；输入顺序不影响结果。
- 支持 TTF、OTF、TTC 和 OTC，也可以依次合并多个字体。
- 支持微软雅黑等 `.ttc` 字体，无须预先拆分。
- 自动修改字体内部名称，避免与原字体冲突。
- 提供 Windows、Linux、macOS 单文件程序，无须安装 Python。
- 默认自动生成字体中可用的多个字重，也可以只选择一个字重。

---

## 功能亮点

1. **中英文混排优化**：作为示例，英文使用 Inconsolata，中文使用 LXGW Bright，保持视觉一致的 2:1 等宽比例。
2. **多字重支持**：可生成 Regular、Medium、Bold、Italic 等不同字重和样式的字体。
3. **字体集合支持**：可以直接选择 TTC/OTC 中的字体，例如微软雅黑。
4. **开箱即用**：下载程序即可合并，生成的字体可直接安装使用。

---

## 使用方法

### 下载

在 [Releases](https://github.com/ChenZhu-Xie/Font_Merger/releases) 下载适合你系统的文件：

- Windows：`font-merger-windows-x64.exe`
- Windows 图形界面：`font-merger-gui-windows-x64.zip`
- Linux：`font-merger-linux-x64`
- macOS：`font-merger-macos`

### GUI（Windows 推荐）

Windows 用户推荐下载图形界面压缩包，解压后双击 `font-merger-gui-windows-x64.exe`。添加字体、选择输出位置，再点击“开始合并”即可。界面支持简体中文、繁體中文和 English。

默认设置已经是适合大多数人的推荐方案：自动识别西文与 CJK 字体，让西文字体覆盖英文等重复字符，同时保留中文字体的其余字符，并以中文字体作为显示基准，避免中文笔画因缩放而变粗。程序还会自动生成可用字重；两款字体的添加顺序不影响识别结果。

### 命令行

把程序和字体放在同一文件夹，在该文件夹打开终端后运行：

```powershell
./font-merger-windows-x64.exe "Inconsolata-Medium.ttf" "LXGWBright-Medium.ttf" --family "Inconsolata-LXGWMono" --style Medium -o "Inconsolata-LXGWMono-Medium.ttf"
```

命令行默认使用相同的推荐策略。合并其他字体或三个以上字体时，则按输入顺序决定字符优先级。

#### 合并微软雅黑

TTC / OTC 是字体集合。先查看其中的字体：

```powershell
./font-merger-windows-x64.exe --list "C:\Windows\Fonts\msyh.ttc"
```

再选择要使用的序号，例如 `#0`：

```powershell
./font-merger-windows-x64.exe "Inconsolata-Medium.ttf" "C:\Windows\Fonts\msyh.ttc#0" --family "Inconsolata-YaHei" --style Medium -o "Inconsolata-YaHei-Medium.ttf"
```

> 路径中有 `#0` 时，请保留两边的英文双引号。

#### Hinting

一份字体只能安全使用一套 TrueType Hinting。中西文双字体默认以中文 / CJK 字体的 UPM 和 Hinting 为显示基准；源字体含可用 Hinting 时会优先保留。如果更在意西文 Hinting，可以加上：

```powershell
--hinting-source latin
```

也可以选择 `cjk`、`none` 或输入字体序号，例如 `--hinting-source 2`。

#### 多字重

不指定字重时，程序采用字重较丰富的一侧，自动生成 Thin、Regular、Bold 等文件；另一侧缺少对应字重时使用最接近的一款。可用 `--list` 查看字体包含的实例：

```powershell
./font-merger-windows-x64.exe --list "C:\Windows\Fonts\NotoSansSC-VF.ttf"
```

只需一个字重时明确指定实例：

```powershell
./font-merger-windows-x64.exe "consolab.ttf" "NotoSansSC-VF.ttf" --instance Bold --family "Consolas Noto Sans SC" -o "Consolas-Noto-Bold.ttf"
```

需要更多控制时，可用 `--weights latin`、`cjk`、`union`、`intersection` 或 `300,400,700`；`--weight-match exact` 可禁止使用相近字重替代。

### 安装与使用

- Windows：双击 TTF 文件 → 点击“安装”
- macOS：双击 TTF 文件 → 安装到字体册
- Linux：拷贝到 `~/.local/share/fonts/` → 运行 `fc-cache -fv`

Sublime Text 的 `Preferences.sublime-settings`：

```json
{
    "font_face": "Inconsolata-LXGWMono",
    "font_size": 14
}
```

VS Code：管理 → 设置 → 搜索 `Font Family`：

```text
'Inconsolata-LXGWMono', 'Source Han Mono SC', Consolas, 'Courier New', monospace
```

### 开发者

普通用户不需要安装 Python。源码运行方式：

```powershell
python -m pip install -e .
font-merger "Inconsolata-Medium.ttf" "LXGWBright-Medium.ttf" -o "merged.ttf"
```

GUI 使用 Python 标准库 Tkinter / ttk，字体处理使用 fontTools，并由 PyInstaller 打包为单文件程序。合并任务在后台线程运行；耗时主要取决于字体大小、字符数量和输出字重数量。

字体合并不会改变源字体许可证。分享合并后的字体前，请确认所有源字体都允许这样使用。

同类工具调研与技术说明见 [docs/research.md](docs/research.md)。

## License

[GPL-3.0](LICENSE)
