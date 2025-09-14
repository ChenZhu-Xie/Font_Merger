# Font_Merger

将 🀄️:🦜 = 2:1 的 等宽 双字体 并集，生成 单字体

## 项目简介

**Font_Merger** 是一个 Python 工具，用于自动生成中英文等宽混排字体家族。  
作为示例，它将 Inconsolata 的 1 等宽 西文字符 与 LXGW Bright 的 2 等宽 中文字符，
拼合成一个统一的 英:中 = 1:2 等宽字体，并支持多字重和样式（Regular、Medium、Bold、Italic 等）。  

主要特点：
- 自动处理 ASCII 字符和中文字符的补集，避免重复覆盖。  
- 支持批量生成多字重字体家族，保证编辑器（如 Sublime Text、VS Code）可识别。  
- 自动修改字体内部名称（Family Name、Full Name、PostScript Name），避免与原字体冲突。  
- 清理临时文件，一步生成可安装的最终字体。  

---

## 功能亮点

1. **自动字重检测**：自动识别目录中可用的字重并生成对应拼合字体。  
2. **中英文混排优化**：英文使用 Inconsolata，中文使用 LXGW Bright，保持视觉一致的 2:1 等宽比例。  
3. **多字重支持**：可生成 Regular / Medium / Bold / Italic 字重，编辑器可直接识别不同字重。  
4. **开箱即用**：生成的字体可直接安装使用，无需额外配置。  

---

## 使用方法

### 1. 准备字体
- 将 `Inconsolata-Medium.ttf` 和 `LXGWBright-Medium.ttf` 字体文件放在脚本同一目录。  
- 运行脚本 `python Font_Merger.py`

### 2. 输出结果
- 拼合字体将生成在 merged_fonts 文件夹，例如：
```
    merged_fonts/
    ├── Inconsolata-LXGWMono-Regular.ttf
    ├── Inconsolata-LXGWMono-Medium.ttf (对于此示例)
    ├── Inconsolata-LXGWMono-Bold.ttf
    └── Inconsolata-LXGWMono-Italic.ttf
```

### 3. 安装字体
- Windows：双击 TTF 文件 → 点击“安装”
- macOS：双击 TTF 文件 → 安装到字体册
- Linux：拷贝到 `~/.local/share/fonts/` → 运行 `fc-cache -fv`

### 4. 编辑器使用
- Sublime Text: 打开 Preferences.sublime-settings
```
{
    "font_face": "Inconsolata-LXGWMono"
    "font_size": 14,
}
```

- VScode: 管理-设置，搜索 Font Family
  - 粘贴 'Inconsolata-LXGWMono', 'Source Han Mono SC', Consolas, 'Courier New', monospace

### 5. 依赖
```
    pip install fonttools
```
### 6. 项目文件结构示例
```
.
├── merge_fonts_auto_detect.py  # 主脚本
├── Inconsolata-Regular.ttf
├── Inconsolata-Bold.ttf
├── LXGWBright-Medium.ttf
├── LXGWBright-Bold.ttf
└── merged_fonts/               # 输出的拼合字体文件夹
```