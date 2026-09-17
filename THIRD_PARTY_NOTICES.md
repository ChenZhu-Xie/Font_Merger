# Third-party notices

The Windows GUI embeds the Latin and CJK text glyphs from
[JetBrainsLxgwNerdMono v1.3](https://github.com/lvbibir/JetBrainsLxgwNerdMono/releases/tag/v1.3),
copyright (c) 2024 lvbibir. It combines JetBrains Mono Nerd Font v3.4.0 with
LXGW WenKai Mono GB Screen v1.521.

The release build removes the Nerd Fonts private-use and icon codepoint ranges
because the GUI does not use them. It validates that those glyphs are absent
before packaging. This avoids redistributing aggregated Font Logos and other
third-party icon glyphs with separate or unclear licenses.

The release ZIP includes the relevant upstream license documents in its
`licenses` directory:

- `JetBrains-Mono-OFL.txt`
- `LXGW-WenKai-Screen-OFL.txt`
- `Nerd-Fonts-LICENSE.txt`, including Nerd Fonts' combined notices and terms
- `Nerd-Fonts-license-audit.md`, listing glyph sources and their licenses

The bundled Nerd Fonts audit documents the excluded icon sources. The prepared
font records the removal and its remaining OFL terms in its name metadata.
