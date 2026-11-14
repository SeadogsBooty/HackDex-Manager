"""Persist the exact identity of a successful install, without fuzzy matching."""
from pathlib import Path

from models import Hack, HackMatch, Rom, ReviewDecision, VersionDecision
from matcher import compare_versions
from scanner import configured_rom_root


def bind_installed_rom(db, hack_slug, result):
    destination = Path(result["destination"])
    if not destination.is_file():
        raise ValueError("Installed destination is missing.")
    root = configured_rom_root()
    try:
        key = str(destination.relative_to(root))
    except ValueError:
        key = str(destination)

    # Scanner uses the configured path, not a basename. Never bind a
    # different file with the same name in another library.
    rom = db.query(Rom).filter(Rom.path == key).first()
    hack = db.query(Hack).filter(Hack.slug == hack_slug).first()
    if rom is None or hack is None:
        raise ValueError("Installed destination or catalog hack not found after scan.")
    if rom.filename != destination.name or rom.platform.upper() != str(result["platform"]).upper():
        raise ValueError("Installed inventory identity does not match destination.")
    version = result.get("target_version")
    rom.hackdex_slug = hack.slug
    rom.latest_version = hack.latest_version
    rom.installed_version = version
    rom.status = compare_versions(version, hack.latest_version)
    rom.size = destination.stat().st_size
    rom.sha256 = result.get("sha256")
    rom.sha1 = None
    db.query(HackMatch).filter(HackMatch.rom_id == rom.id).delete(synchronize_session=False)
    db.query(ReviewDecision).filter(ReviewDecision.rom_id == rom.id).delete(synchronize_session=False)
    db.query(VersionDecision).filter(VersionDecision.rom_id == rom.id).delete(synchronize_session=False)
    db.add(HackMatch(hack_slug=hack.slug, rom_id=rom.id, match_score=100.0,
                     match_method="installed", confirmed=True))
    db.commit()
    return rom.id
