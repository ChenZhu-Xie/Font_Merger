# 同类项目调研（2026-09-17）

## 找到的 GitHub issue

仓库作者 `ChenZhu-Xie` 在以下两个 issue 中贴过本项目：

- [sublimehq/sublime_text#2795](https://github.com/sublimehq/sublime_text/issues/2795#issuecomment-3289201058)
- [JetBrains/JetBrainsMono#530](https://github.com/JetBrains/JetBrainsMono/issues/530#issuecomment-3289204222)

记忆中的“下一条回复”是 JetBrains Mono issue 中
[Charles94jp 的回复](https://github.com/JetBrains/JetBrainsMono/issues/530#issuecomment-4181486905)，
它指向 [CandyTek/EditorMonospacedFont](https://github.com/CandyTek/EditorMonospacedFont)。
该仓库收集已经制作好的中英等宽字体，没有提供通用合并器源码，因此没有解决本项目的
`TTC + TTF` 输入问题。它适合直接取用已有组合，不适合让用户自由选择字体集合。

## 项目对比

| 项目 | TTC | 多输入 | 免 Python | 主要问题 |
|---|---:|---:|---:|---|
| CandyTek/EditorMonospacedFont | 不适用 | 不适用 | 是 | 成品字体集合，不是合并工具 |
| [mrx7014/FontMerger](https://github.com/mrx7014/FontMerger) | 否 | 是 | 否 | 调用外部 `pyftmerge`；手工 UPM 缩放没有覆盖所有相关 OpenType 坐标表；明确不处理可变/彩色字体 |
| [luzi82/mono-merge](https://github.com/luzi82/mono-merge) | 是（CJK 输入 + index） | 否（固定 Latin/CJK） | 否 | 合并流程删除 GPOS/GSUB，复杂文字 shaping 与定位信息会丢失 |
| [nowar-fonts/Warcraft-Font-Merger](https://github.com/nowar-fonts/Warcraft-Font-Merger) | 未作为主要输入接口 | 是 | 发布包是 | C++/otfcc 工具链成熟且快，但面向魔兽字体补全，分发包还捆绑字库和多个程序 |
| 本项目 2.0 | 是（按文件签名识别） | 是（前者优先） | Release 是 | 静态轮廓字体；暂不合并彩色字体，CFF2 可变字体需先导出静态实例 |

## 2.0 的取舍

- 使用 `fontTools.ttLib.TTFont(..., fontNumber=N)` 直接读取 TTC/OTC face，不需要先拆文件。
- 所有输入在同一次 merge 中处理；后续字体只保留前序字体没有的 Unicode 字符，优先级明确且不会靠不稳定的重复 cmap 行为决定。
- 用 fontTools 的 `scale_upem` 缩放轮廓、度量和 GPOS 等相关字段；若 TrueType hinting 因缩放失效，只移除被缩放字体的 hinting。
- 保留并合并 GSUB/GPOS。对缺少 `vhea/vmtx` 的字体补充中性纵排度量，避免为了通过合并而删除 CJK 原生纵排信息。
- CFF OTF 在内存中以 cu2qu 转为 TrueType 轮廓；TrueType 可变字体先静态化。
- 输出后重新打开，核对 Unicode 覆盖、UPM 和静态化状态，再原子替换目标文件。
- GitHub Actions 用 PyInstaller 生成包含 Python 与 fontTools 的单文件程序；最终用户不安装 Python 或 pip。

“任意字体都能无损合并”在 OpenType 中并不是可兑现的承诺。彩色字体涉及 COLR/CPAL、CBDT/CBLC、
SVG 或 sbix 的额外 glyph 引用；CFF2 可变字体也需要完整的 variation 实例化支持。2.0 对这些输入明确
报错，避免生成表面可安装、实际缺字或 shaping 损坏的字体。
