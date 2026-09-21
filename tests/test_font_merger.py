from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.tables._f_v_a_r import Axis, NamedInstance

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


if __name__ == "__main__":
    import unittest

    unittest.main()
