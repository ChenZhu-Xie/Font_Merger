from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from fontTools.ttLib import TTCollection, TTFont

from Font_Merger import FontSource, collection_faces, merge_fonts, parse_source


ROOT = Path(__file__).resolve().parents[1]
LATIN = ROOT / "Inconsolata-Medium.ttf"
CJK = ROOT / "LXGWBright-Medium.ttf"


class FontMergerTests(TestCase):
    def test_parse_plain_font(self):
        source = parse_source(str(LATIN))
        self.assertEqual(source.path, LATIN.resolve())
        self.assertFalse(source.face_explicit)

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


if __name__ == "__main__":
    import unittest

    unittest.main()
