from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from database import Base


class Rom(Base):
    __tablename__ = "roms"

    id = Column(Integer, primary_key=True)

    filename = Column(String, nullable=False)
    path = Column(String, unique=True, nullable=False)

    platform = Column(String, nullable=False)
    library = Column(String, nullable=False)

    extension = Column(String)
    size = Column(BigInteger)

    sha1 = Column(String)
    sha256 = Column(String)

    parsed_title = Column(String, nullable=True)
    installed_version = Column(String, nullable=True)
    variant = Column(String, nullable=True)

    hackdex_id = Column(String, nullable=True)
    hackdex_slug = Column(String, nullable=True)
    latest_version = Column(String, nullable=True)

    status = Column(String, default="UNMATCHED")

    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    last_checked = Column(DateTime, nullable=True)


class Hack(Base):
    __tablename__ = "hacks"

    id = Column(Integer, primary_key=True)

    slug = Column(String, unique=True, nullable=False, index=True)
    title = Column(String, nullable=False, index=True)

    author = Column(String, nullable=True)
    summary = Column(Text, nullable=True)

    base_rom = Column(String, nullable=True)
    platform = Column(String, nullable=True)

    latest_version = Column(String, nullable=True)
    completion_status = Column(String, nullable=True)

    cover_url = Column(String, nullable=True)

    approved = Column(Boolean, default=True)
    is_archive = Column(Boolean, default=False)

    current_patch = Column(String, nullable=True)

    current_patch_filename = Column(String, nullable=True)
    current_patch_bucket = Column(String, nullable=True)
    current_patch_format = Column(String, nullable=True)
    current_patch_published = Column(Boolean, nullable=True)
    current_patch_archived = Column(Boolean, nullable=True)
    current_patch_updated_at = Column(DateTime, nullable=True)

    published_at = Column(DateTime, nullable=True)

    catalog_updated_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)


class HackMatch(Base):
    __tablename__ = "hack_matches"

    id = Column(Integer, primary_key=True)

    hack_slug = Column(
        String,
        ForeignKey("hacks.slug"),
        nullable=False,
        index=True,
    )

    rom_id = Column(
        Integer,
        ForeignKey("roms.id"),
        nullable=False,
        index=True,
    )

    match_score = Column(Float, nullable=False, default=0.0)
    match_method = Column(String, nullable=True)

    confirmed = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class MatchRejection(Base):
    __tablename__ = "match_rejections"

    id = Column(Integer, primary_key=True)

    rom_id = Column(
        Integer,
        ForeignKey("roms.id"),
        nullable=False,
        index=True,
    )

    hack_slug = Column(
        String,
        ForeignKey("hacks.slug"),
        nullable=False,
        index=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


class ReviewDecision(Base):
    """
    Persistent ROM-level review decisions that are not
    HackDex mappings themselves.

    Currently used for IGNORE.

    This keeps Ignore separate from:
      - HackMatch
      - MatchRejection
      - VersionDecision
    """

    __tablename__ = "review_decisions"

    id = Column(
        Integer,
        primary_key=True,
    )

    rom_id = Column(
        Integer,
        ForeignKey("roms.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    decision = Column(
        String,
        nullable=False,
    )

    context_hack_slug = Column(
        String,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )



class VersionDecision(Base):
    __tablename__ = "version_decisions"

    id = Column(Integer, primary_key=True)

    rom_id = Column(
        Integer,
        ForeignKey("roms.id"),
        nullable=False,
        index=True,
        unique=True,
    )

    hack_slug = Column(
        String,
        ForeignKey("hacks.slug"),
        nullable=False,
        index=True,
    )

    installed_version = Column(
        String,
        nullable=True,
    )

    remote_version = Column(
        String,
        nullable=True,
    )

    decision = Column(
        String,
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class LibraryLocation(Base):
    __tablename__ = "library_locations"

    id = Column(
        Integer,
        primary_key=True,
    )

    kind = Column(
        String,
        nullable=False,
        index=True,
    )

    label = Column(
        String,
        nullable=True,
    )

    path = Column(
        String,
        nullable=False,
    )

    platform = Column(
        String,
        nullable=False,
        default="AUTO",
    )

    enabled = Column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


class BaseRom(Base):
    __tablename__ = "base_roms"

    id = Column(
        Integer,
        primary_key=True,
    )

    location_id = Column(
        Integer,
        ForeignKey("library_locations.id"),
        nullable=False,
        index=True,
    )

    path = Column(
        String,
        nullable=False,
        unique=True,
        index=True,
    )

    filename = Column(
        String,
        nullable=False,
    )

    platform = Column(
        String,
        nullable=True,
        index=True,
    )

    size = Column(
        Integer,
        nullable=False,
    )

    mtime_ns = Column(
        Integer,
        nullable=True,
    )

    sha256 = Column(
        String,
        nullable=False,
        index=True,
    )

    sha1 = Column(
        String,
        nullable=True,
        index=True,
    )

    crc32 = Column(
        String,
        nullable=False,
        index=True,
    )

    detected_key = Column(
        String,
        nullable=True,
        index=True,
    )

    verification_status = Column(
        String,
        nullable=False,
        default="UNVERIFIED",
    )

    scanned_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


class PatchReadiness(Base):
    __tablename__ = "patch_readiness"

    id = Column(Integer, primary_key=True)

    hack_slug = Column(
        String,
        ForeignKey("hacks.slug"),
        nullable=False,
        unique=True,
        index=True,
    )

    patch_id = Column(
        String,
        nullable=False,
        index=True,
    )

    patch_format = Column(
        String,
        nullable=False,
    )

    patch_filename = Column(
        String,
        nullable=True,
    )

    base_rom_id = Column(
        Integer,
        ForeignKey("base_roms.id"),
        nullable=True,
        index=True,
    )

    base_key = Column(
        String,
        nullable=True,
        index=True,
    )

    status = Column(
        String,
        nullable=False,
        index=True,
    )

    detail = Column(
        Text,
        nullable=True,
    )

    patch_identity = Column(
        String,
        nullable=True,
        index=True,
    )

    patch_sha256 = Column(
        String,
        nullable=True,
        index=True,
    )

    base_sha256 = Column(
        String,
        nullable=True,
        index=True,
    )

    xdelta_has_checksums = Column(
        Boolean,
        nullable=True,
    )

    patch_crc32 = Column(
        String,
        nullable=True,
    )

    expected_source_crc32 = Column(
        String,
        nullable=True,
    )

    expected_source_size = Column(
        BigInteger,
        nullable=True,
    )

    checked_at = Column(
        DateTime,
        default=datetime.utcnow,
    )
