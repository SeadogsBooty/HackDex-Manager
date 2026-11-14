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

    def test_browser_stage_and_install_preserves_old_rom(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from database import Base
        from models import Hack, BaseRom, Rom
        from obtain_staging import stage_obtain, _hash_file
        from obtain_install import install_staged
        from patch_readiness import _patch_identity
        from contextlib import ExitStack

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base_path = root / "base.gba"
            new_path = root / "browser.gba"
            library = root / "library"
            library.mkdir()
            old_path = library / "Old.gba"
            save = library / "Old.sav"
            data = bytearray(1024)
            data[4:8] = bytes.fromhex("24FFAE51")
            data[0xB2] = 0x96
            base_path.write_bytes(data)
            data[0xC0] = 1
            old_path.write_bytes(data)
            data[0xC0] = 2
            new_path.write_bytes(data)
            save.write_bytes(b"existing save")
            original = old_path.read_bytes()
            engine = create_engine("sqlite://")
            Base.metadata.create_all(engine)
            factory = sessionmaker(bind=engine)
            with factory() as db:
                hack = Hack(slug="browser-test", title="Browser Test",
                            base_rom="test-base", platform="GBA", latest_version="2.0",
                            current_patch="1", current_patch_filename="test.bps",
                            current_patch_format="bps", current_patch_published=True,
                            current_patch_archived=False, patches_download_permission="None")
                db.add(hack)
                db.add(BaseRom(location_id=1, path=str(base_path), filename=base_path.name,
                               platform="GBA", detected_key="test-base", verification_status="VERIFIED",
                               **_hash_file(base_path)))
                old_hashes = _hash_file(old_path)
                db.add(Rom(filename=old_path.name, path=str(old_path), platform="GBA", library="test",
                           extension=".gba", installed_version="1.0", hackdex_slug="browser-test",
                           status="UPDATE_AVAILABLE", sha1=old_hashes["sha1"],
                           sha256=old_hashes["sha256"], size=old_hashes["size"]))
                db.commit()
                identity = _patch_identity(hack)

            with ExitStack() as stack:
                for mod in ("obtain_staging", "obtain_install", "patch_readiness"):
                    stack.enter_context(patch(mod + ".SessionLocal", factory))
                stack.enter_context(patch("obtain_staging.STAGING_ROOT", root / "staging"))
                stack.enter_context(patch("obtain_install.STAGING_ROOT", root / "staging"))
                stack.enter_context(patch("obtain_staging._configured_base_rom_root", return_value=root))
                stack.enter_context(patch("obtain_staging.get_settings", return_value={}))
                stack.enter_context(patch("obtain_install._configured_install_root", return_value=library))
                stack.enter_context(patch("obtain_install.backups_dir", return_value=root / "backups"))
                download = stack.enter_context(patch("obtain_staging._download_patch"))
                staged = stage_obtain("browser-test", "raw", browser_rom=new_path,
                                      expected_patch_identity=identity)
                self.assertTrue(staged["success"], staged)
                self.assertEqual(staged["status"], "STAGED_IMPORTED")
                self.assertEqual(old_path.read_bytes(), original)
                self.assertEqual(save.read_bytes(), b"existing save")
                download.assert_not_called()
                installed = install_staged("browser-test", staged["transaction_id"])
                self.assertTrue(installed["success"], installed)
                self.assertFalse(installed["version_verified"])
                self.assertEqual(Path(installed["destination"]).read_bytes(), new_path.read_bytes())
                self.assertEqual(Path(installed["retained_backups"][0]).read_bytes(), original)
                self.assertEqual(save.read_bytes(), b"existing save")
                self.assertFalse(old_path.exists())
            engine.dispose()

    def test_http_download_errors_are_classified(self):
        from datetime import datetime
        import httpx
        for status, expected in ((404, "PATCH_DOWNLOAD_UNAVAILABLE"), (429, "PATCH_DOWNLOAD_RATE_LIMITED")):
            with tempfile.TemporaryDirectory() as folder:
                hack = SimpleNamespace(slug="test", current_patch="123", current_patch_format="bps",
                                       current_patch_filename="test.bps", current_patch_updated_at=datetime.now(),
                                       patches_download_permission="All")
                with patch("patch_readiness.upstream_enabled", return_value=True), patch("patch_readiness.PATCH_CACHE", Path(folder)), patch("patch_readiness.httpx.Client") as client:
                    response = client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
                    response.status_code = status
                    with self.assertRaises(PatchDownloadError) as ctx:
                        _download_patch(hack)
                    self.assertEqual(ctx.exception.status, expected)
                    self.assertEqual(list(Path(folder).iterdir()), [])
