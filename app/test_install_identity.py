import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import Hack, HackMatch, Rom
from install_identity import bind_installed_rom
from parser import parse_filename
from matcher import run_matching
from catalog import get_catalog


class InstallIdentityTests(unittest.TestCase):
    def test_final_version(self):
        self.assertEqual(parse_filename("Pokémon Grape (Final 1.7).7z"),
                         {"title": "Pokémon Grape", "version": "Final 1.7", "variant": None})

    def test_exact_destination_and_persistent_match(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            destination = root / "Pokémon Grape (Final 1.7).7z"
            destination.write_bytes(b"synthetic")
            engine = create_engine("sqlite://")
            Base.metadata.create_all(engine)
            factory = sessionmaker(bind=engine)
            with factory() as db:
                db.add(Hack(slug="grape", title="Pokémon Grape", platform="GB", latest_version="Final 1.7",
                            approved=True, is_archive=False))
                old = Rom(filename="Pokémon Grape.7z", path=str(root / "Pokémon Grape.7z"),
                          platform="GB", library="test", status="MATCHED", hackdex_slug="grape")
                new = Rom(filename=destination.name, path=destination.name, platform="GB", library="test",
                          status="UNMATCHED", parsed_title="Pokémon Grape")
                other = Rom(filename=destination.name, path=str(root / "other" / destination.name),
                            platform="GB", library="other", status="UNMATCHED", parsed_title="Other")
                db.add_all([old, new, other])
                db.flush()
                db.add(HackMatch(hack_slug="grape", rom_id=old.id, match_score=100.0,
                                 match_method="auto:identity-v2.1", confirmed=True))
                db.commit()
                new_id = new.id
                with patch("install_identity.configured_rom_root", return_value=root):
                    self.assertEqual(bind_installed_rom(db, "grape", {
                        "destination": str(destination), "platform": "GB", "target_version": "Final 1.7",
                        "sha256": "test-hash"}), new_id)
                self.assertIsNone(other.hackdex_slug)
                self.assertEqual(new.installed_version, "Final 1.7")
            with patch("matcher.SessionLocal", factory), patch("matcher.get_settings", return_value={}):
                run_matching()
            with factory() as db:
                match = db.query(HackMatch).filter(HackMatch.rom_id == new_id).one()
                self.assertEqual(match.match_method, "installed")
                self.assertTrue(match.confirmed)
                self.assertEqual(db.get(Rom, new_id).status, "CURRENT")
            with patch("catalog.SessionLocal", factory), patch("catalog._rich_catalog_by_slug", return_value={}):
                item = get_catalog()[0]
                self.assertEqual(item["local_filename"], destination.name)
                self.assertEqual(item["installed_version"], "Final 1.7")
            engine.dispose()
