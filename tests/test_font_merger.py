from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.tables._f_v_a_r import Axis, NamedInstance

from Font_Merger import (
    FontSource,
    collection_faces,
    merge_fonts,
    parse_source,
    variable_details,
)


ROOT = Path(__file__).resolve().parents[1]
LATIN = ROOT / "Inconsolata-Medium.ttf"
CJK = ROOT / "LXGWBright-Medium.ttf"


class FontMergerTests(TestCase):
    def test_parse_plain_font(self):
        source = parse_source(str(LATIN))
        self.assertEqual(source.path, LATIN.resolve())
        self.assertFalse(source.face_explicit)

    def test_variable_font_axes_and_named_instances_are_listed(self):
        font = TTFont()
        name = newTable("name")
        name.names = []
        name.setName("Weight", 256, 3, 1, 0x409)
        name.setName("Regular", 257, 3, 1, 0x409)
        font["name"] = name

        axis = Axis()
        axis.axisTag = "wght"
        axis.minValue = 100
        axis.defaultValue = 100
        axis.maxValue = 900
        axis.flags = 0
        axis.axisNameID = 256
        regular = NamedInstance()
        regular.subfamilyNameID = 257
        regular.postscriptNameID = 0xFFFF
        regular.coordinates = {"wght": 400}
        fvar = newTable("fvar")
        fvar.axes = [axis]
        fvar.instances = [regular]
        font["fvar"] = fvar

        axes, instances = variable_details(font)
        self.assertEqual(axes[0].tag, "wght")
        self.assertEqual(axes[0].maximum, 900)
        self.assertEqual(instances[0].name, "Regular")
        self.assertEqual(instances[0].coordinate_map, {"wght": 400})

    def test_ttc_face_selection_and_merge(self):
        with TemporaryDirectory() as directory:
            temp = Path(directory)
            collection_path = temp / "fixtures.ttc"
            collection = TTCollection()
            collection.fonts = [TTFont(LATIN), TTFont(CJK)]
            collection.save(collection_path)
            collection.close()

            faces = collection_faces(collection_path)
            self.assertEqual(len(faces), 2)
            self.assertIn("LXGW", faces[1].family)

            selected = parse_source(f"{collection_path}#1")
            self.assertEqual(selected.face_index, 1)
            self.assertTrue(selected.face_explicit)

            output = temp / "merged.ttf"
            with TTFont(LATIN) as latin, TTFont(CJK) as cjk:
                expected = set(latin.getBestCmap()) | set(cjk.getBestCmap())
            characters, glyphs = merge_fonts(
                [FontSource(LATIN), selected],
                output,
                family="Test Merged",
                style="Medium",
            )

            with TTFont(output) as merged:
                cmap = merged.getBestCmap()
                self.assertTrue(expected.issubset(cmap))
                self.assertEqual(merged["name"].getBestFamilyName(), "Test Merged")
                self.assertEqual(merged["hmtx"][cmap[ord("A")]][0], 500)
                self.assertIn("vhea", merged)
                self.assertIn("vmtx", merged)
            self.assertEqual(characters, len(expected))
            self.assertGreaterEqual(glyphs, characters)

    def test_auto_priority_is_independent_of_latin_cjk_input_order(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "reversed.ttf"
            merge_fonts(
                [FontSource(CJK), FontSource(LATIN)],
                output,
                family="Auto Priority",
            )

            with TTFont(LATIN) as latin, TTFont(output) as merged:
                latin_cmap = latin.getBestCmap()
                merged_cmap = merged.getBestCmap()
                latin_name = latin_cmap[ord("A")]
                merged_name = merged_cmap[ord("A")]
                self.assertEqual(
                    merged["hmtx"][merged_name][0],
                    latin["hmtx"][latin_name][0],
                )

    def test_weight_and_style_metadata_are_synchronized(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "bold.ttf"
            merge_fonts(
                [FontSource(LATIN), FontSource(CJK)],
                output,
                family="Test Family",
                style="Bold",
            )

            with TTFont(output) as merged:
                self.assertEqual(merged["name"].getDebugName(16), "Test Family")
                self.assertEqual(merged["name"].getDebugName(17), "Bold")
                self.assertEqual(merged["name"].getDebugName(2), "Bold")
                self.assertEqual(merged["OS/2"].usWeightClass, 700)
                self.assertTrue(merged["OS/2"].fsSelection & (1 << 5))
                self.assertTrue(merged["head"].macStyle & 1)

    def test_hinting_source_none_removes_global_and_glyph_hints(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "unhinted.ttf"
            merge_fonts(
                [FontSource(LATIN), FontSource(CJK)],
                output,
                hinting_source="none",
            )

            with TTFont(output) as merged:
                self.assertFalse({"cvt ", "fpgm", "prep"}.intersection(merged.keys()))
                glyph = merged["glyf"][merged.getBestCmap()[ord("A")]]
                self.assertEqual(len(glyph.program.getBytecode()), 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
