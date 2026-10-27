from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.psCharStrings import T2CharString
from fontTools.misc.roundTools import otRound
from fontTools.otlLib.builder import buildMathTable
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.tables._f_v_a_r import Axis, NamedInstance
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

from Font_Merger import (
    AxisInfo,
    FontMergerError,
    FontSource,
    InstanceInfo,
    LOG,
    SourceInfo,
    VERSION,
    assess_table_policy,
    collection_faces,
    configure_standard_streams,
    instantiate_if_variable,
    legacy_names,
    merge_font_family,
    merge_fonts,
    main,
    parse_source,
    plan_weights,
    resolve_hinting_source,
    style_flags,
    summarize_table_policy,
    variable_details,
)


ROOT = Path(__file__).resolve().parents[1]
LATIN = ROOT / "Inconsolata-Medium.ttf"
CJK = ROOT / "LXGWBright-Medium.ttf"


class FontMergerTests(TestCase):
    @staticmethod
    def _rectangle_glyph(width, height):
        pen = TTGlyphPen(None)
        pen.moveTo((50, 0))
        pen.lineTo((width - 50, 0))
        pen.lineTo((width - 50, height))
        pen.lineTo((50, height))
        pen.closePath()
        return pen.glyph()

    @classmethod
    def _write_math_font(
        cls,
        path,
        *,
        family,
        upm,
        codepoint,
        glyph_name,
        axis_height,
        top_accent,
        min_connector_overlap,
    ):
        variant_name = f"{glyph_name}.size"
        glyph_order = [".notdef", glyph_name, variant_name]
        widths = {
            ".notdef": otRound(upm / 2),
            glyph_name: otRound(upm * 0.6),
            variant_name: otRound(upm * 0.8),
        }
        builder = FontBuilder(upm, isTTF=True)
        builder.setupGlyphOrder(glyph_order)
        builder.setupCharacterMap({codepoint: glyph_name})
        builder.setupGlyf(
            {
                name: cls._rectangle_glyph(max(width, 200), otRound(upm * 0.7))
                for name, width in widths.items()
            }
        )
        builder.setupHorizontalMetrics({name: (width, 0) for name, width in widths.items()})
        builder.setupHorizontalHeader(
            ascent=otRound(upm * 0.8), descent=-otRound(upm * 0.2)
        )
        builder.setupOS2(
            sTypoAscender=otRound(upm * 0.8),
            sTypoDescender=-otRound(upm * 0.2),
            usWinAscent=otRound(upm * 0.8),
            usWinDescent=otRound(upm * 0.2),
        )
        builder.setupNameTable(
            {
                "familyName": family,
                "styleName": "Regular",
                "uniqueFontIdentifier": f"MathRegression-{family}",
                "fullName": f"{family} Regular",
                "psName": family.replace(" ", "") + "-Regular",
            }
        )
        builder.setupPost()
        builder.setupMaxp()
        buildMathTable(
            builder.font,
            constants={
                "AxisHeight": axis_height,
                "DelimitedSubFormulaMinHeight": axis_height * 4,
                "DisplayOperatorMinHeight": axis_height * 8,
            },
            topAccentAttachments={glyph_name: top_accent},
            extendedShapes={glyph_name},
            minConnectorOverlap=min_connector_overlap,
            vertGlyphVariants={
                glyph_name: [
                    (glyph_name, upm),
                    (variant_name, otRound(upm * 1.5)),
                ]
            },
            vertGlyphAssembly={
                glyph_name: (
                    (
                        (
                            variant_name,
                            1,
                            otRound(upm * 0.1),
                            otRound(upm * 0.2),
                            otRound(upm * 0.5),
                        ),
                    ),
                    otRound(upm * 0.05),
                )
            },
        )
        builder.font.save(path)
        builder.font.close()

    @staticmethod
    def _write_cff_vorg_font(path):
        glyph_order = [".notdef", "han", "han.vert"]
        widths = {name: 1000 for name in glyph_order}
        heights = {".notdef": 500, "han": 700, "han.vert": 600}
        charstrings = {}
        for name in glyph_order:
            pen = T2CharStringPen(widths[name], None)
            pen.moveTo((100, 0))
            pen.lineTo((900, 0))
            pen.lineTo((900, heights[name]))
            pen.lineTo((100, heights[name]))
            pen.closePath()
            charstrings[name] = pen.getCharString()

        builder = FontBuilder(1000, isTTF=False)
        builder.setupGlyphOrder(glyph_order)
        builder.setupCharacterMap({0x4E00: "han"})
        builder.setupCFF(
            "VerticalCFF-Regular",
            {"FullName": "Vertical CFF Regular"},
            charstrings,
            {},
        )
        builder.setupHorizontalMetrics({name: (width, 100) for name, width in widths.items()})
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupVerticalMetrics(
            {
                ".notdef": (1000, 375),
                # Deliberately use the bbox-derived fallback values from a
                # less accurate CFF bbox calculation. VORG is authoritative.
                "han": (1000, 175),
                "han.vert": (1000, 305),
            }
        )
        builder.setupVerticalHeader(ascent=500, descent=-500)
        builder.setupNameTable(
            {
                "familyName": "Vertical CFF",
                "styleName": "Regular",
                "uniqueFontIdentifier": "VerticalCFF-Regular",
                "fullName": "Vertical CFF Regular",
                "psName": "VerticalCFF-Regular",
            }
        )
        builder.setupOS2(
            sTypoAscender=800,
            sTypoDescender=-200,
            usWinAscent=800,
            usWinDescent=200,
        )
        builder.setupPost()
        vorg = newTable("VORG")
        vorg.majorVersion = 1
        vorg.minorVersion = 0
        vorg.defaultVertOriginY = 880
        vorg.VOriginRecords = {"han.vert": 910}
        builder.font["VORG"] = vorg
        addOpenTypeFeaturesFromString(
            builder.font,
            """
            languagesystem DFLT dflt;
            languagesystem hani dflt;
            feature vert { sub han by han.vert; } vert;
            feature vrt2 { sub han by han.vert; } vrt2;
            """,
        )
        builder.font.save(path)
        builder.font.close()

    @staticmethod
    def _write_cff2_variable_font(path):
        glyph_order = [".notdef", "variable"]
        builder = FontBuilder(1000, isTTF=False)
        builder.setupGlyphOrder(glyph_order)
        builder.setupCharacterMap({0x2603: "variable"})
        builder.setupNameTable(
            {
                "familyName": "CFF2 Variable",
                "styleName": "Regular",
                "uniqueFontIdentifier": "CFF2Variable-Regular",
                "fullName": "CFF2 Variable Regular",
                "psName": "CFF2Variable-Regular",
            }
        )
        builder.setupFvar(
            [("wght", 100, 400, 900, "Weight")],
            [
                {"location": {"wght": 400}, "stylename": "Regular"},
                {"location": {"wght": 900}, "stylename": "Black"},
            ],
        )

        empty_pen = T2CharStringPen(None, None, CFF2=True)
        empty = empty_pen.getCharString()
        variable = T2CharString(
            program=[
                200,
                100,
                -100,
                0,
                2,
                "blend",
                "rmoveto",
                400,
                200,
                1,
                "blend",
                "hlineto",
                500,
                0,
                1,
                "blend",
                "vlineto",
                -400,
                -200,
                1,
                "blend",
                "hlineto",
            ]
        )
        builder.setupCFF2(
            {".notdef": empty, "variable": variable},
            regions=[{"wght": (0, 1, 1)}],
        )
        builder.setupHorizontalMetrics({name: (1000, 0) for name in glyph_order})
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupOS2(
            sTypoAscender=800,
            sTypoDescender=-200,
            usWinAscent=800,
            usWinDescent=200,
        )
        builder.setupPost()
        builder.font.save(path)
        builder.font.close()

    @staticmethod
    def _glyph_bounds(font, glyph_name):
        glyph_set = font.getGlyphSet()
        pen = BoundsPen(glyph_set)
        glyph_set[glyph_name].draw(pen)
        return pen.bounds

    @staticmethod
    def _single_substitution(font, feature_tag, glyph_name):
        feature_list = font["GSUB"].table.FeatureList.FeatureRecord
        lookup_list = font["GSUB"].table.LookupList.Lookup
        for feature_record in feature_list:
            if feature_record.FeatureTag != feature_tag:
                continue
            for lookup_index in feature_record.Feature.LookupListIndex:
                for subtable in lookup_list[lookup_index].SubTable:
                    if glyph_name in subtable.mapping:
                        return subtable.mapping[glyph_name]
        raise AssertionError(f"missing {feature_tag} substitution for {glyph_name}")

    def test_table_policy_always_rejects_unsafe_layout_technologies(self):
        font = TTFont()
        font["morx"] = newTable("morx")
        with self.assertRaisesRegex(FontMergerError, r"morx.*拒绝"):
            assess_table_policy(font, "unsafe.ttf")

    def test_warn_table_policy_reports_and_drops_unknown_and_legacy_kern(self):
        font = TTFont()
        font["kern"] = newTable("kern")
        font["ZZZZ"] = newTable("ZZZZ")
        with self.assertLogs(LOG, level="WARNING") as captured:
            tags, drops = assess_table_policy(font, "legacy.ttf")
        self.assertEqual(tags, {"kern", "ZZZZ"})
        self.assertEqual(drops, {"kern", "ZZZZ"})
        self.assertIn("kern", "\n".join(captured.output))
        self.assertIn("ZZZZ", "\n".join(captured.output))

    def test_strict_table_policy_rejects_unverified_tables(self):
        font = TTFont()
        font["BASE"] = newTable("BASE")
        with self.assertRaisesRegex(FontMergerError, r"strict.*BASE"):
            assess_table_policy(font, "advanced.ttf", "strict")

    def test_table_policy_summary_records_every_disposition(self):
        summary = summarize_table_policy(
            [
                {"BASE", "GSUB", "STAT", "VORG", "cmap"},
                {"GSUB", "cmap"},
            ],
            {"BASE", "GSUB", "cmap", "name"},
        )
        self.assertEqual(summary["merged"], ("GSUB",))
        self.assertEqual(summary["rebuilt"], ("VORG", "cmap", "name"))
        self.assertEqual(summary["dropped"], ("STAT",))
        self.assertEqual(summary["unverified"], ("BASE",))

    def test_standard_streams_are_configured_for_utf8_output(self):
        stdout = StringIO()
        stderr = StringIO()
        stdout.reconfigure = Mock()
        stderr.reconfigure = Mock()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            configure_standard_streams()
        stdout.reconfigure.assert_called_once_with(
            encoding="utf-8", errors="backslashreplace"
        )
        stderr.reconfigure.assert_called_once_with(
            encoding="utf-8", errors="backslashreplace"
        )

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

    def test_cff2_variable_font_requires_experimental_opt_in(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cff2-vf.otf"
            self._write_cff2_variable_font(path)
            with TTFont(path) as font:
                with self.assertRaisesRegex(FontMergerError, "实验"):
                    instantiate_if_variable(font, {})

    def test_cff2_variable_font_staticizes_default_and_custom_locations(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cff2-vf.otf"
            self._write_cff2_variable_font(path)

            observed = {}
            for location, expected_bounds in (
                ({}, (200, 100, 600, 600)),
                ({"wght": 900}, (100, 100, 700, 600)),
            ):
                with self.subTest(location=location), TTFont(path) as font:
                    used = instantiate_if_variable(
                        font,
                        location,
                        {"wght": 400},
                        experimental_cff2_staticize=True,
                        source_label="generated-cff2.otf",
                    )
                    self.assertEqual(used, set(location))
                    self.assertNotIn("CFF2", font)
                    self.assertNotIn("fvar", font)
                    self.assertIn("CFF ", font)
                    observed[tuple(location.items())] = self._glyph_bounds(
                        font, "variable"
                    )
                    self.assertEqual(
                        observed[tuple(location.items())], expected_bounds
                    )
            self.assertNotEqual(observed[()], observed[(("wght", 900),)])

    def test_cff2_staticization_rejects_an_incomplete_downgrade(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cff2-vf.otf"
            self._write_cff2_variable_font(path)
            with TTFont(path) as font, patch(
                "Font_Merger.instantiateVariableFont", return_value=font
            ):
                with self.assertRaisesRegex(
                    FontMergerError, "generated-cff2.otf.*仍含 CFF2"
                ):
                    instantiate_if_variable(
                        font,
                        {"wght": 900},
                        experimental_cff2_staticize=True,
                        source_label="generated-cff2.otf",
                    )

    def test_cff2_staticization_wraps_upstream_failure_with_diagnostics(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cff2-vf.otf"
            self._write_cff2_variable_font(path)
            with TTFont(path) as font, patch(
                "Font_Merger.instantiateVariableFont",
                side_effect=IndexError("bad VarStore"),
            ):
                with self.assertRaisesRegex(
                    FontMergerError,
                    r"generated-cff2\.otf.*wght=900.*fontTools [0-9.]+.*"
                    r"IndexError: bad VarStore",
                ):
                    instantiate_if_variable(
                        font,
                        {"wght": 900},
                        experimental_cff2_staticize=True,
                        source_label="generated-cff2.otf",
                    )

    def test_list_labels_a_standalone_font_as_font_not_face_zero(self):
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--list", str(LATIN)]), 0)
        self.assertTrue(output.getvalue().startswith("font\t"))
        self.assertNotIn("#0", output.getvalue())

    def test_diagnostics_report_runtime_and_dependency_versions(self):
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--diagnostics"]), 0)
        diagnostics = dict(
            line.split("=", 1) for line in output.getvalue().splitlines()
        )
        self.assertEqual(diagnostics["font_merger"], VERSION)
        self.assertRegex(diagnostics["python"], r"^\d+\.\d+\.\d+")
        self.assertRegex(diagnostics["fonttools"], r"^\d+\.\d+")
        self.assertIn(diagnostics["pointer_bits"], {"32", "64"})
        self.assertEqual(diagnostics["frozen"], "false")

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

    def test_math_multiple_sources_use_priority_globals_and_scale_each_source(self):
        with TemporaryDirectory() as directory:
            temp = Path(directory)
            primary_path = temp / "primary-math.ttf"
            secondary_path = temp / "secondary-math.ttf"
            output = temp / "merged-math.ttf"

            self._write_math_font(
                primary_path,
                family="Primary Math",
                upm=1000,
                codepoint=0x0041,
                glyph_name="primary",
                axis_height=250,
                top_accent=300,
                min_connector_overlap=50,
            )
            self._write_math_font(
                secondary_path,
                family="Secondary Math",
                upm=2048,
                codepoint=0x4E00,
                glyph_name="secondary",
                axis_height=768,
                top_accent=1024,
                min_connector_overlap=200,
            )

            merge_fonts(
                [FontSource(primary_path), FontSource(secondary_path)],
                output,
                family="Multi-source Math",
                priority="input",
                hinting_source="2",
            )

            with TTFont(output) as merged:
                self.assertEqual(merged["head"].unitsPerEm, 2048)
                math = merged["MATH"].table
                self.assertEqual(math.MathConstants.AxisHeight.Value, 512)
                self.assertEqual(
                    math.MathConstants.DelimitedSubFormulaMinHeight, 2048
                )
                self.assertEqual(math.MathConstants.DisplayOperatorMinHeight, 4096)
                self.assertEqual(math.MathVariants.MinConnectorOverlap, 102)

                cmap = merged.getBestCmap()
                primary_glyph = cmap[0x0041]
                secondary_glyph = cmap[0x4E00]
                accents = dict(
                    zip(
                        math.MathGlyphInfo.MathTopAccentAttachment.TopAccentCoverage.glyphs,
                        math.MathGlyphInfo.MathTopAccentAttachment.TopAccentAttachment,
                    )
                )
                self.assertEqual(accents[primary_glyph].Value, 614)
                self.assertEqual(accents[secondary_glyph].Value, 1024)
                self.assertEqual(
                    set(math.MathGlyphInfo.ExtendedShapeCoverage.glyphs),
                    {primary_glyph, secondary_glyph},
                )

                constructions = dict(
                    zip(
                        math.MathVariants.VertGlyphCoverage.glyphs,
                        math.MathVariants.VertGlyphConstruction,
                    )
                )
                self.assertEqual(
                    [
                        record.AdvanceMeasurement
                        for record in constructions[
                            primary_glyph
                        ].MathGlyphVariantRecord
                    ],
                    [2048, 3072],
                )
                primary_assembly = constructions[primary_glyph].GlyphAssembly
                self.assertEqual(primary_assembly.ItalicsCorrection.Value, 102)
                self.assertEqual(
                    [
                        (
                            record.StartConnectorLength,
                            record.EndConnectorLength,
                            record.FullAdvance,
                        )
                        for record in primary_assembly.PartRecords
                    ],
                    [(205, 410, 1024)],
                )
                self.assertEqual(
                    [
                        record.AdvanceMeasurement
                        for record in constructions[
                            secondary_glyph
                        ].MathGlyphVariantRecord
                    ],
                    [2048, 3072],
                )

    def test_cff_vorg_origins_survive_glyf_conversion_and_upm_scaling(self):
        with TemporaryDirectory() as directory:
            temp = Path(directory)
            cff_path = temp / "vertical-cff.otf"
            companion_path = temp / "companion.ttf"
            output = temp / "merged.ttf"
            self._write_cff_vorg_font(cff_path)
            self._write_math_font(
                companion_path,
                family="UPM 2048 Companion",
                upm=2048,
                codepoint=0x0041,
                glyph_name="latin",
                axis_height=512,
                top_accent=600,
                min_connector_overlap=100,
            )

            merge_fonts(
                [FontSource(cff_path), FontSource(companion_path)],
                output,
                priority="input",
                hinting_source="2",
            )

            with TTFont(output) as merged:
                self.assertEqual(merged["head"].unitsPerEm, 2048)
                self.assertIn("glyf", merged)
                self.assertNotIn("CFF ", merged)
                self.assertNotIn("VORG", merged)

                base = merged.getBestCmap()[0x4E00]
                vertical = self._single_substitution(merged, "vert", base)
                self.assertEqual(
                    self._single_substitution(merged, "vrt2", base), vertical
                )
                glyf = merged["glyf"]
                origins = {}
                for glyph_name in (base, vertical):
                    glyph = glyf[glyph_name]
                    glyph.recalcBounds(glyf)
                    origins[glyph_name] = (
                        glyph.yMax + merged["vmtx"][glyph_name][1]
                    )
                    self.assertEqual(merged["vmtx"][glyph_name][0], 2048)

                self.assertEqual(origins[base], otRound(880 * 2048 / 1000))
                self.assertEqual(origins[vertical], otRound(910 * 2048 / 1000))

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
