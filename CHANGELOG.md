# Changelog

This file records user-visible changes to Font_Merger. GitHub release assets and
checksums remain available from the [Releases page](https://github.com/ChenZhu-Xie/Font_Merger/releases).

## Unreleased

### Added

- Add a GUI “Report issue” action after both successful and failed merges. It
  opens a reviewable GitHub Issue draft prefilled with privacy-safe source file
  names, merge settings, output summaries, runtime diagnostics, and sanitized
  error details. It never submits or uploads font files automatically, omits
  full local paths and activity logs, and copies the draft URL to the clipboard
  only when the browser cannot be opened.

### Fixed

- Preserve the actionable core exception details in Traditional Chinese and
  English GUI error dialogs instead of replacing them with a generic message.

## [2.4.0] - 2026-10-27

### Added

- Preserve default and non-default Unicode Variation Sequences (`cmap` format
  14) through source selection, subsetting, merging, and output validation.
- Add `--table-policy warn|strict` so advanced OpenType table handling is
  explicit. Unsafe color, AAT, and Graphite tables are rejected in both modes.
- Add `--diagnostics` output for the Font_Merger, Python, fontTools, platform,
  architecture, and frozen-executable versions. The GUI records the same
  environment information in its merge log.
- Add opt-in `--experimental-cff2-staticize` support. It fully instances a CFF2
  variable font, downgrades it to static CFF, and then uses the existing
  CFF-to-TrueType pipeline. This remains experimental and is not exposed in the
  GUI.

### Fixed

- Merge MATH data from multiple contributing fonts and preserve font-level
  constant precedence independently of the internal hinting order.
- Scale MATH design-unit fields that fontTools does not scale during UPM
  normalization.
- Preserve CFF `VORG` default and per-glyph vertical origins when converting
  outlines to TrueType `glyf`/`vmtx` data.
- Reject or report advanced tables with an explicit policy instead of silently
  assuming that serialization preserves their semantics.

### Validation and release engineering

- Run a real packaged-executable merge on Windows, Linux, macOS arm64, and
  macOS x64 release builds instead of checking only `--version`.
- Validate the Linux source and packaged outputs with OTS and a deterministic
  HarfBuzz corpus covering scalar cmap, UVS, Latin ligatures, combining marks,
  Arabic joining, and Indic conjuncts.
- Exercise the experimental path against a pinned Adobe Source Serif 4 CFF2
  variable font in CI.
- Pin release-build dependencies and publish SHA-256 checksums and runtime
  diagnostics with the release artifacts.

### Compatibility and limits

- Python 3.10 uses `fontTools>=4.65.0,<4.66`; Python 3.11 and newer use
  `fontTools>=4.67.0,<4.68`. Version 4.68.0 is temporarily excluded because it
  regresses staticization of the pinned Adobe CFF2 corpus; the upper bound can
  be removed after an upstream fix is released and passes that CI gate.
- Output remains a static font with TrueType `glyf` outlines. Variable-font
  output and true CFF/PostScript-outline output are not supported.
- Color-font merging remains unsupported. CFF2 staticization is opt-in because
  upstream instancing still has known failures for some fonts.

[2.4.0]: https://github.com/ChenZhu-Xie/Font_Merger/compare/v2.3.8...v2.4.0
