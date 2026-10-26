import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.font_qa import find_tool, run_external, validate_shape


class FontQATests(TestCase):
    def test_missing_tool_names_executable(self):
        with self.assertRaisesRegex(FileNotFoundError, "missing-font-qa-tool"):
            find_tool("missing-font-qa-tool")

    def test_ots_failure_preserves_diagnostics(self):
        with TemporaryDirectory(prefix="font qa ") as temporary:
            root = Path(temporary)
            program = root / "reject_font.py"
            program.write_text(
                "import sys\n"
                "print('OTS rejected fixture', file=sys.stderr)\n"
                "raise SystemExit(7)\n",
                encoding="utf-8",
            )
            log_path = root / "ots.log"

            with self.assertRaisesRegex(RuntimeError, r"exited with 7"):
                run_external([sys.executable, str(program)], log_path)

            diagnostics = log_path.read_text(encoding="utf-8")
            self.assertIn("exit_code: 7", diagnostics)
            self.assertIn("OTS rejected fixture", diagnostics)

    def test_invalid_harfbuzz_json_names_case(self):
        case = {
            "name": "broken-json-case",
            "expect": {"glyphs": ["A"]},
        }
        with self.assertRaisesRegex(AssertionError, r"broken-json-case.*JSON"):
            validate_shape(case, {"g": "A"})

    def test_glyph_sequence_is_checked(self):
        case = {
            "name": "latin-ligature",
            "expect": {"glyphs": ["f_i"]},
        }
        payload = [
            {"g": "f", "cl": 0, "dx": 0, "dy": 0, "ax": 500, "ay": 0},
            {"g": "i", "cl": 1, "dx": 0, "dy": 0, "ax": 300, "ay": 0},
        ]
        with self.assertRaisesRegex(AssertionError, r"latin-ligature.*glyphs"):
            validate_shape(case, payload)

    def test_glyph_ids_are_checked_for_post_format_three_output(self):
        case = {
            "name": "latin-ligature",
            "expect": {"gids": [4]},
        }
        payload = [
            {"g": "gid5", "cl": 0, "dx": 0, "dy": 0, "ax": 650, "ay": 0}
        ]

        with self.assertRaisesRegex(AssertionError, r"latin-ligature.*gids"):
            validate_shape(case, payload, {"glyph00004": 4, "acutecomb": 5})

    def test_rtl_clusters_are_checked(self):
        case = {
            "name": "arabic-joining",
            "expect": {
                "glyphs": ["beh.fina", "beh.medi", "beh.init"],
                "clusters": [2, 1, 0],
            },
        }
        payload = [
            {"g": "beh.fina", "cl": 0, "dx": 0, "dy": 0, "ax": 500},
            {"g": "beh.medi", "cl": 1, "dx": 0, "dy": 0, "ax": 500},
            {"g": "beh.init", "cl": 2, "dx": 0, "dy": 0, "ax": 500},
        ]
        with self.assertRaisesRegex(AssertionError, r"arabic-joining.*clusters"):
            validate_shape(case, payload)

    def test_mark_position_predicate_is_checked(self):
        case = {
            "name": "combining-mark",
            "expect": {
                "glyphs": ["A", "acutecomb"],
                "positions": {
                    "acutecomb": {"dx_nonzero": True, "dy_nonzero": True}
                },
            },
        }
        payload = [
            {"g": "A", "cl": 0, "dx": 0, "dy": 0, "ax": 600, "ay": 0},
            {
                "g": "acutecomb",
                "cl": 0,
                "dx": 0,
                "dy": 0,
                "ax": 0,
                "ay": 0,
            },
        ]
        with self.assertRaisesRegex(
            AssertionError, r"combining-mark.*acutecomb.*dx_nonzero"
        ):
            validate_shape(case, payload)

    def test_exact_mark_position_rejects_harfbuzz_fallback(self):
        case = {
            "name": "combining-mark",
            "expect": {
                "gids": [1, 5],
                "positions": {"acutecomb": {"dx": -400, "dy": 200}},
            },
        }
        payload = [
            {"g": "gid1", "cl": 0, "dx": 0, "dy": 0, "ax": 600, "ay": 0},
            {
                "g": "gid5",
                "cl": 0,
                "dx": -350,
                "dy": 762,
                "ax": 0,
                "ay": 0,
            },
        ]

        with self.assertRaisesRegex(
            AssertionError, r"combining-mark.*acutecomb.*dx.*expected -400.*got -350"
        ):
            validate_shape(case, payload, {"A": 1, "acutecomb": 5})


if __name__ == "__main__":
    import unittest

    unittest.main()
