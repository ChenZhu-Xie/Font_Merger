# Font_Merger Roadmap

本文档记录已经结合当前源码、回归测试和代表性字体样本复核过的改进方向。原始外部调研材料归档于
[`research/2026-10-23-font-merger-landscape.txt`](research/2026-10-23-font-merger-landscape.txt)。

更新时间：2026-10-24；代码基线：v2.3.8。

## 当前定位

Font_Merger 是建立在 fontTools 之上的成品字体合并工作流，重点处理 TTC/OTC face、UPM
归一化、静态化、字符来源优先级、CFF→glyf、Hinting 来源、命名和发布包装。近期目标不是替换
fontTools merger，也不是立即覆盖所有 OpenType 格式，而是让已经声明支持的输入拥有可验证的
输出语义。

## 已解决：MATH 表合并

GitHub issue #2 暴露的问题来自旧版 fontTools：顶层 `MATH` 表虽然可以进入 merge 流程，
`MathConstants`、`MathGlyphInfo`、`MathVariants` 等子表却没有 merge policy。fontTools 4.67.0
加入了上游支持；Font_Merger v2.3.8 还为 Python 3.10 使用的旧版 fontTools 回移了相同策略。

现有回归测试覆盖 MathConstants、TopAccentAttachment、ExtendedShapeCoverage 和纵向 variants。
后续仍应补充不同 UPM 和两个 MATH 来源发生字体级常量冲突的测试。

## P0：UVS / cmap format 14 全流程支持

### 已确认的问题

fontTools 已支持合并 cmap format 14，但 Font_Merger 当前的字符扫描、来源分配、子集化和输出
验证只建模标量 Unicode code point。实测中，当高优先级字体取得基础字符，而低优先级字体提供该
字符的 non-default UVS 时，后者会在子集化阶段丢失，输出中连 format 14 子表也不再存在。

### 目标

- 扫描并保存 format 14 的 default UVS range 和 non-default UVS mapping。
- 为 `(base codepoint, variation selector)` 建立明确的来源和冲突策略。
- 基础字符和其 UVS 可以来自不同输入；不能仅因基础字符归属另一字体就丢弃 UVS。
- 子集化时保留被选中的 UVS 及其所引用 glyph。
- 输出验证同时检查标量 cmap、default UVS 和 non-default UVS。
- 日志报告 UVS 数量、来源和冲突结果。

### 验收测试

- 单来源 default UVS 保留。
- 单来源 non-default UVS 保留。
- 基础字符由高优先级字体提供、UVS glyph 由低优先级字体提供。
- 两个输入定义相同 variation sequence 时遵守字符优先级。
- 无关 UVS 不会因保留引用 glyph 而污染输出。
- 保存后重新打开输出字体并再次核对 format 14。

## P0：发布产物级回归与诊断

- PyInstaller 构建后不能只运行 `--version`；应让产物执行一次包含 MATH、UVS 和纵排信息的
  小型端到端合并，再重新打开并验证输出。
- 新增 `--diagnostics`，或扩展版本输出，记录 Font_Merger、Python、fontTools、平台、架构和
  frozen 状态；GUI 合并日志也应记录这些信息。
- 发布构建锁定或至少记录准确的 fontTools、PyInstaller 版本，以便复现依赖相关问题。

## P1：显式的表处理策略和 QA

- 为非核心表记录 `preserved / merged / rebuilt / dropped / unsupported / unverified` 状态。
- 不应在默认模式中隐藏所有 fontTools warning；仅定向过滤已知无害的重复消息。
- 输出验证应完整 decompile 各表，而不只访问 best cmap、UPM 和 `fvar`。
- CI 优先引入 OTS sanitizer 和 HarfBuzz shaping corpus。它们适合发布门禁，不宜成为普通用户
  每次合并都必须安装和运行的依赖。
- FontBakery/Fontspector 更适合作为可选深度检查；合并字体可能有大量与 foundry policy 有关、
  但不代表数据损坏的报告。

### 重点回归语料

- issue #2 的 MATH 场景，以及不同 UPM、两个 MATH 来源的场景。
- UVS default/non-default 和冲突场景。
- CJK CFF 字体的 `vert/vrt2 + vhea/vmtx + VORG`。
- Latin ligature、combining mark，以及 Arabic/Indic 等复杂 shaping 样例。

## P2：实验性 CFF2 可变字体静态化

当前 fontTools 可以通过 `instantiateVariableFont(..., downgradeCFF2=True, static=True)` 将代表性的
CFF2 VF 静态化为 CFF；实测 Source Serif 4 可继续经过现有 CFF→glyf 和 merge 流程。但上游仍有
CFF2 instancing 的未解决失败案例，因此不应直接移除限制并宣称完整支持。

建议先放在显式 experimental flag 后，使用 Adobe/Google CFF2 VF corpus 覆盖默认/自定义轴实例，
并分别测试 Python 3.10 兼容依赖路径和 Python 3.11+ 当前依赖路径。失败必须中止并给出清晰诊断。

## P2：纵排与 VORG 回归

CFF→glyf 后删除 VORG 在格式层面合理。对带 230 个显式 VORG 记录的 Noto Sans CJK 样本检查时，
原始 vertical origin 可以由 glyph bounds 与 vmtx 重建，抽样转换后未发现偏移。因此这不是已确认
bug，但应该成为 corpus regression，尤其覆盖 exceptional records 和 UPM 缩放。

## 暂缓项目

- **真正的 CFF/PostScript outline 输出**：OpenType 的 `.otf` 容器也可以合法包含 glyf。为同时维护
  CFF 输出需要处理 charstring 生成、subroutinization、hinting 丢失和双轮廓 pipeline，当前没有足够
  用户收益支撑这项复杂度。
- **彩色字体**：COLRv1、SVG、CBDT/CBLC、sbix 都有额外 glyph 引用和专用数据结构，继续明确拒绝。
- **保持 Variable Font 输出**：任意 VF union 涉及 axis mapping、masters compatibility 和多个
  VariationStore，远超当前静态化合并的产品边界。

## 建议实施顺序

1. UVS/cmap 14 全流程支持和回归测试。
2. 发布版可执行文件的真实合并测试与依赖诊断。
3. 表处理摘要、warning 策略、完整 decompile 验证。
4. OTS + HarfBuzz corpus CI，补 MATH/纵排边界测试。
5. experimental CFF2 静态化。
