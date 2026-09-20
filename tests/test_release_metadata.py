import re
from pathlib import Path
from unittest import TestCase

from Font_Merger import VERSION


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(TestCase):
    def test_pyproject_version_matches_runtime_version(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        project_section = pyproject.split("[project]", 1)[1].split("\n[", 1)[0]
        match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', project_section, re.MULTILINE)
        self.assertIsNotNone(match, "[project].version is missing from pyproject.toml")
        self.assertEqual(match.group(1), VERSION)
