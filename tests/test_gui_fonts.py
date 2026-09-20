from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from unittest import TestCase, skipUnless
from unittest.mock import Mock, patch

from fontTools.ttLib import TTFont

from Font_Merger import FontSource
from Font_Merger_GUI import (
    DEFAULT_LOCALE,
    GUI_FONT_FAMILY,
    GUI_FONT_FILENAME,
    FontMergerGUI,
    InstalledFontFace,
    TEXT,
    filter_installed_font_faces,
    gui_font_candidates,
    installed_font_faces,
    installed_font_files,
    is_single_weight_request,
    select_gui_font_family,
    windows_font_directories,
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

    def test_single_weight_request_detects_instance_or_wght_axis(self):
        self.assertTrue(is_single_weight_request("Bold", ""))
        self.assertTrue(is_single_weight_request("", "wght=350"))
        self.assertTrue(is_single_weight_request("", "wdth=90, WGHT =350"))
        self.assertFalse(is_single_weight_request("", "wdth=90,slnt=-10"))
        self.assertFalse(is_single_weight_request("", ""))

    def test_installed_font_files_filters_and_sorts_supported_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            expected = (root / "Alpha.OTF", root / "zeta.ttf")
            for path in (*expected, root / "notes.txt"):
                path.touch()
            (root / "folder.ttc").mkdir()

            self.assertEqual(installed_font_files((root,)), expected)

    def test_installed_font_faces_expand_collections_and_sort_by_family(self):
        regular = Path("C:/Windows/Fonts/zeta.ttf")
        collection = Path("C:/Windows/Fonts/families.ttc")
        face = lambda index, family, style: Mock(  # noqa: E731
            index=index, family=family, style=style
        )
        with patch(
            "Font_Merger_GUI.is_collection",
            side_effect=lambda path: path.suffix.casefold() == ".ttc",
        ), patch(
            "Font_Merger_GUI.collection_faces",
            side_effect=[
                [face(0, "Zeta", "Regular")],
                [face(0, "Alpha", "Regular"), face(1, "Alpha", "Bold")],
            ],
        ):
            results = installed_font_faces((regular, collection))

        self.assertEqual(
            [(item.family, item.style) for item in results],
            [("Alpha", "Bold"), ("Alpha", "Regular"), ("Zeta", "Regular")],
        )
        self.assertEqual(results[0].source, f"{collection}#1")
        self.assertEqual(results[1].source, f"{collection}#0")
        self.assertEqual(results[2].source, str(regular))

    def test_installed_font_search_matches_family_style_file_and_multiple_terms(self):
        faces = (
            InstalledFontFace(
                "C:/Fonts/NotoSans-Medium.ttf",
                Path("C:/Fonts/NotoSans-Medium.ttf"),
                "Noto Sans CJK SC",
                "Medium",
            ),
            InstalledFontFace(
                "C:/Fonts/consola.ttf",
                Path("C:/Fonts/consola.ttf"),
                "Consolas",
                "Regular",
            ),
        )

        self.assertEqual(filter_installed_font_faces(faces, "noto medium"), faces[:1])
        self.assertEqual(filter_installed_font_faces(faces, "CONsola.ttf"), faces[1:])
        self.assertEqual(filter_installed_font_faces(faces, "missing"), ())
        self.assertIs(filter_installed_font_faces(faces, ""), faces)

    def test_windows_font_directories_include_system_and_user_locations(self):
        environment = {
            "WINDIR": "D:/Windows",
            "LOCALAPPDATA": "D:/Users/Test/AppData/Local",
        }
        with patch("Font_Merger_GUI.sys.platform", "win32"), patch.dict(
            "Font_Merger_GUI.os.environ", environment, clear=True
        ):
            self.assertEqual(
                windows_font_directories(),
                (
                    Path("D:/Windows/Fonts"),
                    Path("D:/Users/Test/AppData/Local/Microsoft/Windows/Fonts"),
                ),
            )

    def test_combobox_wheel_scrolls_page_without_changing_choice(self):
        gui = Mock()
        event = object()

        result = FontMergerGUI._on_combobox_mousewheel(gui, event)

        gui._on_mousewheel.assert_called_once_with(event)
        self.assertEqual(result, "break")

    def test_add_font_paths_keeps_preselected_collection_face(self):
        gui = Mock()
        gui.fonts = Mock()
        path = Path("C:/Windows/Fonts/family.ttc")
        source = FontSource(path, 2, True)

        with patch("Font_Merger_GUI.parse_source", return_value=source), patch(
            "Font_Merger_GUI.is_collection", return_value=True
        ), patch("Font_Merger_GUI.collection_faces") as collection_faces:
            FontMergerGUI._add_font_paths(gui, [f"{path}#2"])

        collection_faces.assert_not_called()
        gui.fonts.insert.assert_called_once_with(tk.END, f"{path}#2")
        gui.update_font_state.assert_called_once_with()

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
