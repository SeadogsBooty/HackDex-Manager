import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hackdex_access import upstream_enabled
from patch_readiness import _download_patch, automatic_patch_available, cached_patch_path, PatchDownloadError
from hackdex_provider import HackDexSupabaseProvider, sync_catalog
from base_rom_registry import sync_registry


class LocalOnlyTests(unittest.TestCase):
    def test_default_and_explicit_opt_in(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(upstream_enabled())
        for value in ("true", "1", "yes", "unknown"):
            with patch.dict("os.environ", {"HACKDEX_UPSTREAM_ACCESS": value}):
                self.assertFalse(upstream_enabled())
        with patch.dict("os.environ", {"HACKDEX_UPSTREAM_ACCESS": "authorized"}):
            self.assertTrue(upstream_enabled())

    def test_no_http_for_catalog_or_registry(self):
        with patch("hackdex_provider.upstream_enabled", return_value=False), patch("hackdex_provider.httpx.Client") as client:
            with self.assertRaises(RuntimeError):
                HackDexSupabaseProvider()
            client.assert_not_called()
        with patch("base_rom_registry.upstream_enabled", return_value=False), patch("base_rom_registry.load_registry", return_value={"roms": [{"id": "test"}]}), patch("base_rom_registry.httpx.get") as get:
            self.assertTrue(sync_registry()["success"])
            get.assert_not_called()

    def test_local_catalog_retained(self):
        with patch("hackdex_provider.upstream_enabled", return_value=False), patch("hackdex_provider.SessionLocal") as factory, patch("hackdex_provider.build_catalog") as build:
            factory.return_value.query.return_value.filter.return_value.count.return_value = 3
            result = sync_catalog()
            self.assertTrue(result["success"])
            self.assertFalse(result["changed"])
            self.assertEqual(result["imported"], 3)
            build.assert_not_called()

    def test_cached_permitted_patch_only(self):
        hack = SimpleNamespace(current_patch="1", current_patch_filename="test.bps", current_patch_format="bps", current_patch_updated_at=None, patches_download_permission="All")
        with tempfile.TemporaryDirectory() as folder, patch("patch_readiness.PATCH_CACHE", Path(folder)), patch("patch_readiness.upstream_enabled", return_value=False), patch("patch_readiness.httpx.Client") as client:
            self.assertFalse(automatic_patch_available(hack))
            with self.assertRaises(PatchDownloadError) as exc:
                _download_patch(hack)
            self.assertEqual(exc.exception.status, "BROWSER_REQUIRED")
            cache = cached_patch_path(hack)
            cache.write_bytes(b"synthetic")
            self.assertTrue(automatic_patch_available(hack))
            self.assertEqual(_download_patch(hack), cache)
            hack.patches_download_permission = "None"
            self.assertFalse(automatic_patch_available(hack))
            with self.assertRaises(PatchDownloadError):
                _download_patch(hack)
            client.assert_not_called()
