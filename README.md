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

### 1. 下载程序

在 [Releases](https://github.com/ChenZhu-Xie/Font_Merger/releases) 下载适合你系统的文件：

- Windows：`font-merger-windows-x64.exe`
- Windows 图形界面：`font-merger-gui-windows-x64.exe`
- Linux：`font-merger-linux-x64`
- macOS：`font-merger-macos`

### 2. 准备字体

将要合并的字体放在程序旁边。例如：

```text
font-merger-windows-x64.exe
Inconsolata-Medium.ttf
LXGWBright-Medium.ttf
```

### 3. 合并字体

Windows 用户推荐双击 `font-merger-gui-windows-x64.exe`。添加字体后，可以直观选择字形来源、Hinting 来源和字重规则，再点击“开始合并”。界面支持简体中文、繁體中文和 English，可在右上角随时切换。

也可以使用命令行。Windows 用户在文件夹空白处按住 Shift 并单击鼠标右键，选择“在此处打开 PowerShell 窗口”，然后运行：

```powershell
./font-merger-windows-x64.exe "Inconsolata-Medium.ttf" "LXGWBright-Medium.ttf" --family "Inconsolata-LXGWMono" --style Medium -o "Inconsolata-LXGWMono-Medium.ttf"
```

程序会自动识别常见的“西文 + 中文”组合：西文字体提供英文等重复字符，中文字体补充其余字符。合并其他字体或三个以上字体时，则按输入顺序决定优先级。

#### 合并微软雅黑

微软雅黑是 TTC 字体集合。先查看其中有哪些字体：

```powershell
./font-merger-windows-x64.exe --list "C:\Windows\Fonts\msyh.ttc"
```

再选择要使用的序号，例如 `#0`：

```powershell
./font-merger-windows-x64.exe "Inconsolata-Medium.ttf" "C:\Windows\Fonts\msyh.ttc#0" --family "Inconsolata-YaHei" --style Medium -o "Inconsolata-YaHei-Medium.ttf"
```

> 路径中有 `#0` 时，请保留两边的英文双引号。

#### 选择中文字体的显示效果

一份字体只能安全使用一套 TrueType hinting。默认优先保持西文字体的小字号显示效果；如果更在意中文，可以加上：

```powershell
--hinting-source cjk
```

也可以选择 `latin`、`none` 或输入字体序号，例如 `--hinting-source 2`。

#### 自动生成多个字重

先查看字体包含的 Thin、Regular、Medium、Bold 等实例：

```powershell
./font-merger-windows-x64.exe --list "C:\Windows\Fonts\NotoSansSC-VF.ttf"
```

不指定字重时，程序会采用字重较丰富的一侧，自动生成多个字体；另一侧缺少对应字重时会选择最接近的一款：

```powershell
./font-merger-windows-x64.exe "consola.ttf" "NotoSansSC-VF.ttf" --family "Consolas Noto Sans SC" -o "Consolas-Noto.ttf"
```

如果只需要一个字重，再明确指定：

```powershell
./font-merger-windows-x64.exe "consolab.ttf" "NotoSansSC-VF.ttf" --instance Bold --family "Consolas Noto Sans SC" -o "Consolas-Noto-Bold.ttf"
```

需要更多控制时，可以用 `--weights latin`、`cjk`、`union`、`intersection` 或 `300,400,700`。加上 `--weight-match exact` 可以禁止使用相近字重替代。

### 4. 输出结果

合并完成后，会在指定位置生成新的 `.ttf` 字体。自动生成多个字重时，文件名会带上样式，例如：

```text
Consolas-Noto-Thin.ttf
Consolas-Noto-Regular.ttf
Consolas-Noto-Bold.ttf
```

### 5. 安装字体

- Windows：双击 TTF 文件 → 点击“安装”
- macOS：双击 TTF 文件 → 安装到字体册
- Linux：拷贝到 `~/.local/share/fonts/` → 运行 `fc-cache -fv`

### 6. 编辑器使用

Sublime Text：打开 `Preferences.sublime-settings`：

```json
{
    "font_face": "Inconsolata-LXGWMono",
    "font_size": 14
}
```

VS Code：管理 → 设置，搜索 `Font Family`，粘贴：

```text
'Inconsolata-LXGWMono', 'Source Han Mono SC', Consolas, 'Courier New', monospace
```

### 7. 使用 Python 源码（开发者）

普通用户不需要这一步。如果想直接运行源码：

```powershell
python -m pip install -e .
font-merger "Inconsolata-Medium.ttf" "LXGWBright-Medium.ttf" -o "merged.ttf"
```

### 8. 项目文件结构示例

```text
.
├── Font_Merger.py                  # 主程序
├── Inconsolata-Medium.ttf          # 示例英文字体
├── LXGWBright-Medium.ttf           # 示例中文字体
├── merged_fonts/                   # 输出字体文件夹
└── tests/                          # 自动化测试
```

字体合并不会改变源字体许可证。分享合并后的字体前，请确认所有源字体都允许这样使用。

同类工具调研与技术说明见 [docs/research.md](docs/research.md)。

## License

[MIT](LICENSE)
