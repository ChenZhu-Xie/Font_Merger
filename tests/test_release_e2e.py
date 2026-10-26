import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

from fontTools.ttLib import TTFont

from scripts.font_qa import run_qa
from scripts.release_e2e import create_inputs, run_source


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "data" / "shaping-corpus.json"


def feature_tags(font: TTFont, table_tag: str) -> set[str]:
    table = font[table_tag].table
    return {record.FeatureTag for record in table.FeatureList.FeatureRecord}


class ReleaseE2ETests(TestCase):
    def test_source_cli_e2e_reports_non_frozen(self):
        with TemporaryDirectory(prefix="source e2e ") as temporary:
            work_dir = Path(temporary)

            run_source(ROOT / "Font_Merger.py", work_dir)

            self.assertTrue((work_dir / "e2e-merged.ttf").is_file())
            report = (work_dir / "success.txt").read_text(encoding="utf-8")
            self.assertIn("frozen=false", report)

    def test_synthetic_inputs_compile_expected_layout_features(self):
        with TemporaryDirectory() as temporary:
            latin_path, _ = create_inputs(Path(temporary))
            with TTFont(latin_path) as font:
                self.assertTrue(
                    {
                        "f",
                        "i",
                        "f_i",
                        "acutecomb",
                        "beh",
                        "beh.init",
                        "beh.medi",
                        "beh.fina",
                        "ka",
                        "virama",
                        "ssa",
                        "kssa",
                    }.issubset(font.getGlyphOrder())
                )
                self.assertEqual(
                    feature_tags(font, "GSUB"),
                    {"fina", "init", "liga", "medi", "rlig"},
                )
                self.assertEqual(feature_tags(font, "GPOS"), {"mark"})

    @skipUnless(
        shutil.which("hb-shape") and shutil.which("ots-sanitize"),
        "requires hb-shape and ots-sanitize",
    )
    def test_merged_fixture_passes_real_harfbuzz_corpus(self):
        with TemporaryDirectory(prefix="font qa integration ") as temporary:
            work_dir = Path(temporary)
            latin, cjk = create_inputs(work_dir)
            output = work_dir / "merged fixture.ttf"
            command = [
                sys.executable,
                str(ROOT / "Font_Merger.py"),
                str(latin),
                str(cjk),
                "--priority",
                "input",
                "--hinting-source",
                "1",
                "--family",
                "QA Merged",
                "--style",
                "Regular",
                "--table-policy",
                "strict",
                "--output",
                str(output),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)

            run_qa(output, work_dir / "qa logs", CORPUS)


if __name__ == "__main__":
    import unittest

    unittest.main()
