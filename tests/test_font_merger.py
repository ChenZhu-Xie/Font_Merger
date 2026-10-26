from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fontTools.otlLib.builder import buildMathTable
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.tables._f_v_a_r import Axis, NamedInstance
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

from Font_Merger import (
    AxisInfo,
    FontSource,
    InstanceInfo,
    SourceInfo,
    collection_faces,
    legacy_names,
    merge_font_family,
    merge_fonts,
    main,
    parse_source,
    plan_weights,
    resolve_hinting_source,
    style_flags,
    variable_details,
)


ROOT = Path(__file__).resolve().parents[1]
LATIN = ROOT / "Inconsolata-Medium.ttf"
CJK = ROOT / "LXGWBright-Medium.ttf"


class FontMergerTests(TestCase):
    @staticmethod
    def _font_with_uvs(source, destination, entries):
        with TTFont(source) as font:
            by_selector = {}
            for base, selector, glyph_name in entries:
                by_selector.setdefault(selector, []).append((base, glyph_name))
            table = CmapSubtable.newSubtable(14)
            table.platformID = 0
            table.platEncID = 5
            table.language = 0
            table.cmap = {}
            table.uvsDict = by_selector
            font["cmap"].tables.append(table)
            font.save(destination)

    @staticmethod
    def _uvs_mappings(font):
        mappings = {}
        for table in font["cmap"].tables:
            if table.format == 14:
                for selector, entries in table.uvsDict.items():
                    for base, glyph_name in entries:
                        mappings[(base, selector)] = glyph_name
        return mappings

    @staticmethod
    def _weight_infos():
        latin = SourceInfo(
            FontSource(LATIN),
            "Latin",
            "Regular",
            frozenset(range(128)),
            1000,
            False,
            (),
            (),
            400,
        )
        axis = AxisInfo("wght", "Weight", 100, 100, 900)
        instances = tuple(
            InstanceInfo(name, (("wght", weight),))
            for name, weight in (("Thin", 100), ("Regular", 400), ("Bold", 700))
        )
        cjk = SourceInfo(
            FontSource(CJK),
            "CJK",
            "Thin",
            frozenset(range(0x4E00, 0x5000)),
            1000,
            True,
            (axis,),
            instances,
            100,
        )
        return latin, cjk

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

    def test_list_labels_a_standalone_font_as_font_not_face_zero(self):
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--list", str(LATIN)]), 0)
        self.assertTrue(output.getvalue().startswith("font\t"))
        self.assertNotIn("#0", output.getvalue())

    def test_automatic_weight_plan_matches_variable_font_to_static_weight(self):
        infos = self._weight_infos()
        plan = plan_weights(infos, [0, 1], (0, 1), "auto")
        self.assertEqual([weight for weight, _mapping in plan], [400])
        self.assertEqual(plan[0][1], (None, 400))

    def test_automatic_weight_plan_matches_arbitrary_static_weight(self):
        latin, cjk = self._weight_infos()
        latin = SourceInfo(
            latin.source,
            latin.family,
            "DemiLight",
            latin.unicodes,
            latin.upm,
            latin.variable,
            latin.axes,
            latin.instances,
            350,
        )
        plan = plan_weights((latin, cjk), [0, 1], (0, 1), "auto")
        self.assertEqual([weight for weight, _mapping in plan], [350])
        self.assertEqual(plan[0][1], (None, 350))

    def test_extended_weights_share_family_without_bold_alias_collisions(self):
        for style, weight in (
            ("DemiLight", 350),
            ("Medium", 500),
            ("SemiBold", 600),
            ("ExtraBold", 800),
            ("Black", 900),
        ):
            with self.subTest(style=style):
                self.assertEqual(
                    legacy_names("Consolas NotoSans", style, weight),
                    ("Consolas NotoSans", style),
                )
                self.assertFalse(style_flags(style, weight)[0])

        self.assertEqual(
            legacy_names("Consolas NotoSans", "Bold Italic", 700),
            ("Consolas NotoSans", "Bold Italic"),
        )
        self.assertTrue(style_flags("Bold", 700)[0])
        self.assertTrue(style_flags("Bold Italic", 700)[0])

    def test_automatic_weight_plan_keeps_named_weights_when_all_are_variable(self):
        latin, cjk = self._weight_infos()
        latin = SourceInfo(
            latin.source,
            latin.family,
            latin.style,
            latin.unicodes,
            latin.upm,
            True,
            (AxisInfo("wght", "Weight", 100, 400, 900),),
            (
                InstanceInfo("Regular", (("wght", 400),)),
                InstanceInfo("Bold", (("wght", 700),)),
            ),
            400,
        )
        plan = plan_weights((latin, cjk), [0, 1], (0, 1), "auto")
        self.assertEqual([weight for weight, _mapping in plan], [100, 400, 700])
        self.assertEqual(plan[-1][1], (700, 700))

    def test_weight_plan_modes_remain_independent(self):
        infos = self._weight_infos()
        intersection = plan_weights(
            infos, [0, 1], (0, 1), "intersection", match="exact"
        )
        self.assertEqual([weight for weight, _mapping in intersection], [400])
        with self.assertRaisesRegex(Exception, "无法精确生成字重 100"):
            plan_weights(infos, [0, 1], (0, 1), "100", match="exact")

    def test_static_inputs_keep_single_output_by_default(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "family.ttf"
            results = merge_font_family(
                [FontSource(LATIN), FontSource(CJK)],
                output,
                family="Single Weight Family",
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].path, output.resolve())
            self.assertTrue(output.is_file())

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
                self.assertEqual(merged["name"].getDebugName(1), "Test Merged")
                self.assertEqual(merged["name"].getDebugName(2), "Medium")
                self.assertEqual(merged["name"].getBestFamilyName(), "Test Merged")
                self.assertEqual(merged["name"].getDebugName(16), "Test Merged")
                self.assertEqual(merged["name"].getDebugName(17), "Medium")
                self.assertEqual(merged["OS/2"].usWeightClass, 500)
                self.assertFalse(merged["OS/2"].fsSelection & (1 << 5))
                self.assertFalse(merged["OS/2"].fsSelection & (1 << 6))
                self.assertFalse(merged["head"].macStyle & 1)
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

    def test_auto_hinting_prefers_cjk_for_a_latin_cjk_pair(self):
        infos = self._weight_infos()
        self.assertEqual(resolve_hinting_source("auto", infos, [0, 1], (0, 1)), 1)

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

    def test_instance_name_overrides_metadata_style_at_explicit_axis_weight(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "compat-bold.ttf"
            # The bundled fixtures are static fonts. Mock only the variable-font
            # instancing step so this test can exercise the instance-vs-axis
            # metadata precedence without requiring a large variable fixture.
            with patch("Font_Merger.instantiate_if_variable", return_value={"wght"}):
                merge_fonts(
                    [FontSource(LATIN), FontSource(CJK)],
                    output,
                    family="Compatibility Family",
                    instance="Bold",
                    axes={"wght": 500},
                )

            with TTFont(output) as merged:
                self.assertEqual(merged["name"].getDebugName(2), "Bold")
                self.assertEqual(merged["name"].getDebugName(17), "Bold")
                self.assertEqual(merged["OS/2"].usWeightClass, 500)
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

    def test_math_table_is_merged_and_preserved(self):
        with TemporaryDirectory() as directory:
            temp = Path(directory)
            math_cjk = temp / "math-cjk.ttf"
            output = temp / "merged-math.ttf"

            with TTFont(CJK) as font:
                math_codepoint = 0x4E00
                math_glyph = font.getBestCmap()[math_codepoint]
                buildMathTable(
                    font,
                    constants={"AxisHeight": 250},
                    topAccentAttachments={math_glyph: 500},
                    extendedShapes={math_glyph},
                    minConnectorOverlap=50,
                    vertGlyphVariants={math_glyph: [(math_glyph, 1000)]},
                )
                font.save(math_cjk)

            merge_fonts(
                [FontSource(LATIN), FontSource(math_cjk)],
                output,
                family="Math Merge Test",
            )

            with TTFont(output) as merged:
                self.assertIn("MATH", merged)
                merged_math_glyph = merged.getBestCmap()[math_codepoint]
                math = merged["MATH"].table
                self.assertEqual(math.MathConstants.AxisHeight.Value, 250)
                self.assertIn(
                    merged_math_glyph,
                    math.MathGlyphInfo.MathTopAccentAttachment.TopAccentCoverage.glyphs,
                )
                self.assertIn(
                    merged_math_glyph,
                    math.MathGlyphInfo.ExtendedShapeCoverage.glyphs,
                )
                self.assertIn(
                    merged_math_glyph,
                    math.MathVariants.VertGlyphCoverage.glyphs,
                )

    def test_uvs_only_source_contributes_default_and_non_default_sequences(self):
        with TemporaryDirectory() as directory:
            temp = Path(directory)
            uvs_latin = temp / "uvs-latin.ttf"
            output = temp / "merged-uvs-only.ttf"

            with TTFont(LATIN) as font:
                cmap = font.getBestCmap()
                alternate = cmap[ord("B")]
                expected_characters = len(cmap)
            self._font_with_uvs(
                LATIN,
                uvs_latin,
                [
                    (ord("A"), 0xFE00, alternate),
                    (ord("A"), 0xFE01, None),
                ],
            )

            characters, _glyphs = merge_fonts(
                [FontSource(LATIN), FontSource(uvs_latin)],
                output,
                family="UVS-only contribution",
                priority="input",
            )

            with TTFont(output) as merged:
                mappings = self._uvs_mappings(merged)
                self.assertEqual(
                    set(mappings), {(ord("A"), 0xFE00), (ord("A"), 0xFE01)}
                )
                self.assertIsNotNone(mappings[(ord("A"), 0xFE00)])
                self.assertIsNone(mappings[(ord("A"), 0xFE01)])
                self.assertNotEqual(
                    mappings[(ord("A"), 0xFE00)],
                    merged.getBestCmap()[ord("B")],
                )
            self.assertEqual(characters, expected_characters)

    def test_uvs_priority_is_independent_of_hinting_merge_order(self):
        with TemporaryDirectory() as directory:
            temp = Path(directory)
            latin_uvs = temp / "latin-uvs.ttf"
            cjk_uvs = temp / "cjk-uvs.ttf"
            output = temp / "merged-uvs-priority.ttf"

            with TTFont(LATIN) as latin:
                latin_cmap = latin.getBestCmap()
                latin_alternate = latin_cmap[ord("C")]
                latin_alternate_width = latin["hmtx"][latin_alternate][0]
            with TTFont(CJK) as cjk:
                cjk_cmap = cjk.getBestCmap()
                han = cjk_cmap[0x4E00]
                han_width = cjk["hmtx"][han][0]

            self._font_with_uvs(
                LATIN,
                latin_uvs,
                [(ord("A"), 0xFE00, latin_alternate)],
            )
            self._font_with_uvs(
                CJK,
                cjk_uvs,
                [
                    (ord("A"), 0xFE00, han),
                    (ord("A"), 0xFE01, han),
                    (ord("A"), 0xFE02, None),
                    (0x4E00, 0xE0100, None),
                ],
            )

            # Auto priority chooses Latin for duplicate characters and UVS, while
            # auto hinting puts CJK first in the internal fontTools merge order.
            merge_fonts(
                [FontSource(cjk_uvs), FontSource(latin_uvs)],
                output,
                family="UVS priority",
            )

            with TTFont(output) as merged:
                mappings = self._uvs_mappings(merged)
                self.assertEqual(
                    set(mappings),
                    {
                        (ord("A"), 0xFE00),
                        (ord("A"), 0xFE01),
                        (ord("A"), 0xFE02),
                        (0x4E00, 0xE0100),
                    },
                )
                self.assertEqual(
                    merged["hmtx"][mappings[(ord("A"), 0xFE00)]][0],
                    latin_alternate_width,
                )
                self.assertEqual(
                    merged["hmtx"][mappings[(ord("A"), 0xFE01)]][0],
                    han_width,
                )
                self.assertIsNone(mappings[(ord("A"), 0xFE02)])
                self.assertIsNone(mappings[(0x4E00, 0xE0100)])


if __name__ == "__main__":
    import unittest

    unittest.main()
