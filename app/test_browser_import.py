import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from obtain_staging import _validate_browser_rom
from patch_readiness import direct_download_allowed, _download_patch, PatchDownloadError


class BrowserImportTests(unittest.TestCase):
    def test_permissions(self):
        for permission in ("All", "Current"):
            self.assertTrue(direct_download_allowed(SimpleNamespace(patches_download_permission=permission)))
        for permission in ("None", None, "unexpected"):
            hack = SimpleNamespace(patches_download_permission=permission)
            self.assertFalse(direct_download_allowed(hack))
            with patch("patch_readiness.httpx.Client") as client:
                with self.assertRaises(PatchDownloadError):
                    _download_patch(hack)
                client.assert_not_called()

    def test_bad_rom_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.nds"
            path.write_bytes(bytes(1024))
            with self.assertRaisesRegex(ValueError, "header"):
                _validate_browser_rom(path, "NDS", {"sha256": "not-a-hash"})

    def test_unmodified_base_rejected(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.gba"
            data = bytearray(1024)
            data[4:8] = bytes.fromhex("24FFAE51")
            data[0xB2] = 0x96
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "unmodified"):
                _validate_browser_rom(path, "GBA", {"sha256": hashlib.sha256(data).hexdigest()})

    def test_plausible_gba_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.gba"
            data = bytearray(1024)
            data[4:8] = bytes.fromhex("24FFAE51")
            data[0xB2] = 0x96
            path.write_bytes(data)
            _validate_browser_rom(path, "GBA", {"sha256": "different"})
