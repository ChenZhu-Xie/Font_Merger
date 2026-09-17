import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from urllib.error import URLError

from scripts.fetch_gui_font import download_verified_asset


class FetchGUIFontTests(TestCase):
    def test_transient_download_failure_is_retried(self):
        calls = 0

        def open_url(_url, timeout):
            nonlocal calls
            calls += 1
            self.assertEqual(timeout, 120)
            if calls == 1:
                raise URLError("connection reset")
            return BytesIO(b"font data")

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "font.download"
            download_verified_asset(
                "https://example.test/font.ttf",
                destination,
                hashlib.sha256(b"font data").hexdigest(),
                attempts=3,
                open_url=open_url,
                sleep=lambda _seconds: None,
            )
            self.assertEqual(destination.read_bytes(), b"font data")
        self.assertEqual(calls, 2)

    def test_truncated_download_is_retried_before_replacing_existing_file(self):
        calls = 0

        def open_url(_url, timeout):
            nonlocal calls
            calls += 1
            self.assertEqual(timeout, 120)
            return BytesIO(b"truncated" if calls == 1 else b"complete font")

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "font.ttf"
            destination.write_bytes(b"existing valid font")
            download_verified_asset(
                "https://example.test/font.ttf",
                destination,
                hashlib.sha256(b"complete font").hexdigest(),
                attempts=3,
                open_url=open_url,
                sleep=lambda _seconds: None,
            )
            self.assertEqual(destination.read_bytes(), b"complete font")
        self.assertEqual(calls, 2)


if __name__ == "__main__":
    import unittest

    unittest.main()
