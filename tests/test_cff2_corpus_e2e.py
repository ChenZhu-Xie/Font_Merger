import hashlib
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase

from fontTools.ttLib import TTFont

from scripts.cff2_corpus_e2e import (
    download_verified,
    run_corpus,
    validate_cff2_source,
    validate_static_output,
)
from scripts.release_e2e import create_inputs


ROOT = Path(__file__).resolve().parents[1]
LATIN = ROOT / "Inconsolata-Medium.ttf"


class CFF2CorpusE2ETests(TestCase):
    def test_script_help_runs_as_a_direct_entry_point(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "cff2_corpus_e2e.py"),
                "--help",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--work-dir", result.stdout)

    def test_download_verified_rejects_bad_checksum_without_destination(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.bin"
            destination = root / "downloaded.bin"
            source.write_bytes(b"verified fixture")

            with self.assertRaisesRegex(ValueError, "SHA-256"):
                download_verified(source.as_uri(), destination, "0" * 64)

            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_suffix(".bin.part").exists())

    def test_validate_cff2_source_rejects_a_non_cff2_font(self):
        with self.assertRaisesRegex(AssertionError, "CFF2.*fvar"):
            validate_cff2_source(LATIN)

    def test_local_cff2_corpus_runner_produces_static_glyf_output(self):
        with TemporaryDirectory(prefix="cff2 corpus test ") as temporary:
            root = Path(temporary)
            fixture_dir = root / "fixture"
            fixture_dir.mkdir()
            source, _cjk = create_inputs(fixture_dir)
            checksum = hashlib.sha256(source.read_bytes()).hexdigest()

            output = run_corpus(
                ROOT / "Font_Merger.py",
                root / "run",
                source_url=source.as_uri(),
                source_sha256=checksum,
                external_qa=False,
            )

            validate_static_output(output)
            with TTFont(output) as font:
                self.assertIn(0x0041, font.getBestCmap())
                self.assertIn(0x4E00, font.getBestCmap())
                self.assertEqual(font["OS/2"].usWeightClass, 700)


if __name__ == "__main__":
    import unittest

    unittest.main()
