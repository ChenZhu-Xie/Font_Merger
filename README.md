# Font Merger

按优先级把 TTF、OTF、TTC 或 OTC 中的字体合成一个静态 TTF。第一个字体优先，后续字体只补齐它尚未覆盖的 Unicode 字符。

这意味着微软雅黑 `msyh.ttc` 可以直接和普通 `.ttf` 合并，无需先拆 TTC，也不要求最终用户安装 Python。

## 直接使用（推荐）

从 GitHub Releases 下载对应平台的单文件程序。Windows 示例：

```powershell
# 先查看 TTC 中有哪些 face
font-merger-windows-x64.exe --list "C:\Windows\Fonts\msyh.ttc"

# #0 是 Microsoft YaHei；路径必须加引号，避免 PowerShell 把 # 当作注释
font-merger-windows-x64.exe `
  "Inconsolata-Medium.ttf" `
  "C:\Windows\Fonts\msyh.ttc#0" `
  --family "Inconsolata YaHei" `
  --style Medium `
  -o "Inconsolata-YaHei-Medium.ttf"
```

`msyh.ttc` 在当前 Windows 中通常包含：

```text
#0  Microsoft YaHei     Regular
#1  Microsoft YaHei UI  Regular
```

也可以一次合并任意数量的字体。输入顺序就是回退顺序：

```powershell
font-merger-windows-x64.exe "Latin.ttf" "CJK.ttc#0" "Symbols.ttf" -o "Combined.ttf"
```

## 开发运行

```powershell
python -m pip install -e .
font-merger --list "C:\Windows\Fonts\msyh.ttc"
font-merger "Latin.ttf" "CJK.ttc#0" -o "Merged.ttf"
python -m unittest discover -s tests -v
```

可变 TrueType 字体默认在各轴默认值处静态化，也可以指定坐标：

```powershell
font-merger "Latin-VF.ttf" "CJK-VF.ttf" --axis "wght=600" -o "Merged-Semibold.ttf"
```

## 正确性与性能

- TTC/OTC 依据文件签名识别，而不是只看扩展名；用 `path#INDEX` 精确选择 face。
- 后续字体先取 Unicode 补集再合并，减少大字体的内存、I/O 和输出体积。
- 不启动 `pyftmerge` 子进程；所有输入一次合并。
- UPM 不同时使用 fontTools 的全表缩放器，覆盖轮廓、度量和 OpenType 定位数据。
- 保留 GSUB/GPOS 及其 glyph closure；保留已有纵排度量，并给缺少纵排表的字体补充中性度量。
- CFF OTF 自动转换为 TrueType 二次曲线；输出统一为静态 TTF。
- 写入后重新打开并核验字符覆盖与 UPM，验证通过后才替换目标文件。

当前有意拒绝彩色/位图字体（COLR/CPAL、CBDT/CBLC、SVG、sbix）和 CFF2 可变字体。静默丢表会得到“能安装但显示错误”的文件，明确失败更安全。字体合并不会改变字体许可证；发布或分发成品前请检查所有源字体的授权。

## 调研结论

你记忆中的相似仓库是 [CandyTek/EditorMonospacedFont](https://github.com/CandyTek/EditorMonospacedFont)：它收集现成混合字体，并非通用合并工具，因此没有解决 TTC 输入问题。

对 `mrx7014/FontMerger`、`luzi82/mono-merge`、Warcraft Font Merger 的代码级比较和本实现的取舍见 [docs/research.md](docs/research.md)。底层合并基于 [fontTools merge](https://fonttools.readthedocs.io/en/stable/merge.html)。

## License

[MIT](LICENSE)
