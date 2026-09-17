from pathlib import Path
from unittest import TestCase, skipUnless

from fontTools.ttLib import TTFont

from Font_Merger_GUI import (
    DEFAULT_LOCALE,
    GUI_FONT_FAMILY,
    GUI_FONT_FILENAME,
    TEXT,
    gui_font_candidates,
    select_gui_font_family,
)
from scripts.prepare_gui_font import is_nerd_symbol_codepoint


ROOT = Path(__file__).resolve().parents[1]
BUNDLED_FONT = ROOT / "assets" / "fonts" / GUI_FONT_FILENAME
SYSTEM_FONT = Path("C:/Windows/Fonts") / GUI_FONT_FILENAME
TEST_FONT = BUNDLED_FONT if BUNDLED_FONT.is_file() else SYSTEM_FONT


class GUIFontTests(TestCase):
    def test_default_locale_is_simplified_chinese(self):
        self.assertEqual(DEFAULT_LOCALE, "zh_CN")

    def test_simplified_chinese_text_does_not_mix_traditional_wording(self):
        traditional_only = set("選擇型檔併產進階顯設個與軸錯誤讀處順語")
        text = "".join(TEXT["zh_CN"].values())
        self.assertTrue(traditional_only.isdisjoint(text))

    def test_bundled_font_is_preferred_over_an_installed_font(self):
        app_dir = Path("C:/FontMerger")
        windows_fonts = Path("C:/Windows/Fonts")
        self.assertEqual(
            gui_font_candidates(app_dir, windows_fonts),
            (
                app_dir / "assets" / "fonts" / GUI_FONT_FILENAME,
                windows_fonts / GUI_FONT_FILENAME,
            ),
        )

    def test_exact_gui_family_is_selected_when_available(self):
        self.assertEqual(
            select_gui_font_family(("Arial", GUI_FONT_FAMILY)),
            GUI_FONT_FAMILY,
        )

    def test_safe_system_family_is_used_as_last_resort(self):
        self.assertEqual(select_gui_font_family(("Arial",)), "Segoe UI")

    def test_nerd_symbol_ranges_are_identified_for_removal(self):
        for codepoint in (
            0xE000,
            0xF8FF,
            0xF0000,
            0xFFFFD,
            0x23FB,
            0x2665,
            0x26A1,
            0x2B58,
        ):
            self.assertTrue(is_nerd_symbol_codepoint(codepoint))
        for character in "Font简体繁體←→":
            self.assertFalse(is_nerd_symbol_codepoint(ord(character)))

    def test_old_explicit_gui_fonts_are_not_left_in_source(self):
        source = (ROOT / "Font_Merger_GUI.py").read_text(encoding="utf-8")
        self.assertNotIn('font=("Segoe UI', source)
        self.assertNotIn('font=("Cascadia Mono', source)

    @skipUnless(TEST_FONT.is_file(), "JetBrainsLxgwNerdMono is unavailable")
    def test_font_covers_english_simplified_and_traditional_samples(self):
        with TTFont(TEST_FONT, lazy=True) as font:
            cmap = font.getBestCmap()
        self.assertTrue(set(map(ord, "Font简体繁體國国龍龙臺台灣湾")).issubset(cmap))

    @skipUnless(BUNDLED_FONT.is_file(), "bundled GUI font is unavailable")
    def test_bundled_gui_font_contains_no_nerd_symbol_ranges(self):
        with TTFont(BUNDLED_FONT, lazy=True) as font:
            cmap = font.getBestCmap()
            license_summary = font["name"].getDebugName(13)
        self.assertFalse(any(map(is_nerd_symbol_codepoint, cmap)))
        self.assertIn("symbol glyphs were removed", license_summary)


if __name__ == "__main__":
    import unittest

    unittest.main()
