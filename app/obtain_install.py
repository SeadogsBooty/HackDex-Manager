import hashlib
import json
import os
import shutil

from pathlib import Path

from database import SessionLocal
from models import LibraryLocation
from platform_paths import staging_dir


STAGING_ROOT = staging_dir()

LEGACY_STAGING_ROOTS = (
    Path("/staging/hackdex-manager"),
    Path("/staging/obtain"),
)


def _configured_install_root(
    platform,
):
    """
    Resolve the actual enabled HackDex library location
    for the requested platform.

    Installation destinations come exclusively from
    LibraryLocation configuration; no synthetic
    /hack-library path is invented.
    """
    platform = str(
        platform
        or ""
    ).upper()

    db = SessionLocal()

    try:
        rows = (
            db.query(
                LibraryLocation
            )
            .filter(
                LibraryLocation.kind
                == "hack",

                LibraryLocation.enabled
                .is_(True),
            )
            .order_by(
                LibraryLocation.id
            )
            .all()
        )

        exact = [
            row
            for row in rows
            if str(
                row.platform
                or ""
            ).upper()
            == platform
        ]

        automatic = [
            row
            for row in rows
            if str(
                row.platform
                or ""
            ).upper()
            == "AUTO"
        ]

        candidates = (
            exact
            or automatic
        )

        for row in candidates:
            root = Path(
                row.path
            )

            if (
                root.exists()
                and root.is_dir()
                and os.access(
                    root,
                    os.W_OK,
                )
            ):
                return root

        if candidates:
            raise RuntimeError(
                "Configured "
                + platform
                + " hack library is not writable."
            )

        raise RuntimeError(
            "No enabled hack library location is "
            "configured for platform "
            + platform
            + "."
        )

    finally:
        db.close()


def _sha256_file(path):
    digest = hashlib.sha256()

    with Path(path).open(
        "rb"
    ) as handle:
        while True:
            chunk = handle.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def _safe_transaction(
    hack_slug,
    transaction_id,
):
    if not hack_slug:
        raise RuntimeError(
            "Missing hack slug."
        )

    if not transaction_id:
        raise RuntimeError(
            "Missing transaction ID."
        )

    slug = str(
        hack_slug
    ).strip()

    if (
        Path(slug).name != slug
        or slug in {".", ".."}
    ):
        raise RuntimeError(
            "Invalid hack slug."
        )

    def matching_manifest(
        transaction,
    ):
        transaction = Path(
            transaction
        )

        manifest_path = (
            transaction
            / "manifest.json"
        )

        if (
            not transaction.is_dir()
            or not manifest_path.is_file()
        ):
            return None

        try:
            manifest = json.loads(
                manifest_path.read_text(
                    encoding="utf-8"
                )
            )

        except Exception:
            return None

        if (
            str(
                manifest.get(
                    "transaction_id"
                )
                or ""
            )
            != str(transaction_id)
        ):
            return None

        return transaction.resolve()

    #
    # v0.9.9:
    # /staging/<platform>/<slug>/
    #
    for platform_name in (
        "gb",
        "gbc",
        "gba",
        "nds",
    ):
        matched = matching_manifest(
            STAGING_ROOT
            / platform_name
            / slug
        )

        if matched is not None:
            return matched

    #
    # v0.9.8:
    # /staging/<slug>/
    #
    matched = matching_manifest(
        STAGING_ROOT
        / slug
    )

    if matched is not None:
        return matched

    #
    # v0.9.7 and earlier:
    #
    # /staging/hackdex-manager/<slug>/<transaction>
    # /staging/obtain/<slug>/<transaction>
    #
    for legacy_root in LEGACY_STAGING_ROOTS:
        transaction = (
            legacy_root
            / slug
            / transaction_id
        )

        root = legacy_root.resolve()
        resolved = transaction.resolve()

        if (
            resolved == root
            or root not in resolved.parents
        ):
            continue

        if resolved.is_dir():
            return resolved

    raise RuntimeError(
        "Staging transaction does not exist "
        "or no longer matches this operation."
    )


def _write_manifest(
    manifest_path,
    manifest,
):
    manifest_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _cleanup_completed_transaction(
    transaction,
    manifest_path,
    manifest,
):
    """
    Successful installs retain only manifest.json.

    Base copies, patch files, patched raw ROMs, packages,
    rollback files and other staging material are removed.
    """
    transaction = Path(
        transaction
    )

    manifest_path = Path(
        manifest_path
    )

    removed = []

    for item in list(
        transaction.iterdir()
    ):
        if item == manifest_path:
            continue

        removed.append(
            item.name
        )

        if item.is_dir():
            shutil.rmtree(
                item
            )

        else:
            item.unlink(
                missing_ok=True
            )

    manifest[
        "staging_cleanup"
    ] = {
        "completed":
            True,

        "removed":
            sorted(
                removed
            ),

        "retained": [
            "manifest.json",
        ],
    }

    _write_manifest(
        manifest_path,
        manifest,
    )

    return {
        "completed":
            True,

        "removed":
            sorted(
                removed
            ),
    }



def _failure(
    status,
    message,
    hack_slug,
    transaction_id,
    **extra,
):
    result = {
        "success": False,
        "status": status,
        "hack": hack_slug,
        "transaction_id":
            transaction_id,
        "message": message,
        "library_write_performed":
            False,
    }

    result.update(extra)

    return result


def _restore_destination(
    destination,
    backup_path,
):
    destination = Path(destination)

    if (
        backup_path
        and Path(backup_path).exists()
    ):
        restore_temp = (
            destination.parent
            / (
                ".hackdex-rollback-"
                + destination.name
            )
        )

        restore_temp.unlink(
            missing_ok=True
        )

        shutil.copy2(
            backup_path,
            restore_temp,
        )

        os.replace(
            restore_temp,
            destination,
        )

    else:
        destination.unlink(
            missing_ok=True
        )


def install_staged(
    hack_slug,
    transaction_id,
    replace=False,
):
    temp_destination = None

    try:
        transaction = _safe_transaction(
            hack_slug,
            transaction_id,
        )

        manifest_path = (
            transaction
            / "manifest.json"
        )

        if not manifest_path.exists():
            raise RuntimeError(
                "Transaction manifest is missing."
            )

        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )

        if (
            manifest.get("status")
            != "STAGED_VERIFIED"
        ):
            raise RuntimeError(
                "Transaction is not "
                "STAGED_VERIFIED."
            )

        hack = (
            manifest.get("hack")
            or {}
        )

        if (
            hack.get("slug")
            != hack_slug
        ):
            raise RuntimeError(
                "Manifest hack slug mismatch."
            )

        platform = str(
            hack.get("platform")
            or ""
        ).upper()

        destination_root = (
            _configured_install_root(
                platform
            )
        )

        artifact = (
            manifest.get("artifact")
            or {}
        )

        install = (
            manifest.get("install")
            or {}
        )

        update = (
            manifest.get("update")
            or {}
        )

        is_update = bool(
            update.get("is_update")
        )

        previous_version = (
            update.get(
                "installed_version"
            )
        )

        target_version = (
            update.get(
                "target_version"
            )
            or hack.get("version")
        )

        old_rom_id = (
            update.get(
                "existing_rom_id"
            )
        )

        artifact_path = Path(
            artifact.get("path")
            or ""
        )

        expected_sha256 = str(
            artifact.get("sha256")
            or ""
        ).lower()

        final_filename = str(
            install.get("filename")
            or ""
        ).strip()

        if not final_filename:
            raise RuntimeError(
                "Manifest has no final "
                "install filename."
            )

        if (
            Path(final_filename).name
            != final_filename
        ):
            raise RuntimeError(
                "Unsafe install filename."
            )

        if not artifact_path.exists():
            raise RuntimeError(
                "Staged artifact no longer exists."
            )

        artifact_resolved = (
            artifact_path.resolve()
        )

        if (
            transaction
            not in artifact_resolved.parents
        ):
            raise RuntimeError(
                "Artifact is outside the "
                "staging transaction."
            )

        actual_sha256 = _sha256_file(
            artifact_resolved
        )

        if (
            not expected_sha256
            or actual_sha256
            != expected_sha256
        ):
            raise RuntimeError(
                "Staged artifact SHA-256 "
                "does not match manifest."
            )

        destination_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        destination = (
            destination_root
            / final_filename
        )

        old_path = None
        old_expected_sha256 = ""
        old_filename = ""
        in_place_update = False

        #
        # Validate the currently installed ROM
        # BEFORE writing anything.
        #
        if is_update:
            old_filename = str(
                update.get(
                    "existing_filename"
                )
                or ""
            ).strip()

            old_expected_sha256 = str(
                update.get(
                    "existing_sha256"
                )
                or ""
            ).lower()

            existing_path = str(
                update.get(
                    "existing_path"
                )
                or ""
            )

            if not old_filename:
                return _failure(
                    "UPDATE_SOURCE_INVALID",
                    (
                        "Update transaction has "
                        "no existing ROM filename."
                    ),
                    hack_slug,
                    transaction_id,
                )

            if (
                Path(old_filename).name
                != old_filename
            ):
                return _failure(
                    "UPDATE_SOURCE_INVALID",
                    (
                        "Existing ROM filename "
                        "is unsafe."
                    ),
                    hack_slug,
                    transaction_id,
                )

            if (
                existing_path
                and Path(existing_path).name
                != old_filename
            ):
                return _failure(
                    "UPDATE_SOURCE_INVALID",
                    (
                        "Existing ROM path and "
                        "filename do not agree."
                    ),
                    hack_slug,
                    transaction_id,
                )

            if not old_expected_sha256:
                return _failure(
                    "UPDATE_SOURCE_UNVERIFIED",
                    (
                        "Existing ROM has no "
                        "recorded SHA-256."
                    ),
                    hack_slug,
                    transaction_id,
                )

            old_path = (
                destination_root
                / old_filename
            )

            if not old_path.exists():
                return _failure(
                    "UPDATE_SOURCE_MISSING",
                    (
                        "The currently installed "
                        "ROM is no longer present."
                    ),
                    hack_slug,
                    transaction_id,
                    old_filename=
                        old_filename,
                )

            old_actual_sha256 = (
                _sha256_file(
                    old_path
                )
            )

            if (
                old_actual_sha256
                != old_expected_sha256
            ):
                return _failure(
                    "UPDATE_SOURCE_CHANGED",
                    (
                        "The currently installed "
                        "ROM changed since staging. "
                        "Update was cancelled."
                    ),
                    hack_slug,
                    transaction_id,
                    old_filename=
                        old_filename,
                    expected_sha256=
                        old_expected_sha256,
                    actual_sha256=
                        old_actual_sha256,
                )

            in_place_update = (
                old_path.resolve()
                == destination.resolve()
            )

        destination_existed = (
            destination.exists()
        )

        #
        # A same-name update is allowed because
        # the old file was just hash verified.
        #
        if (
            destination_existed
            and not replace
            and not (
                is_update
                and in_place_update
            )
        ):
            return {
                "success": False,
                "status":
                    "DESTINATION_EXISTS",
                "hack":
                    hack_slug,
                "transaction_id":
                    transaction_id,
                "destination":
                    str(destination),
                "message":
                    "A file with the intended "
                    "library filename already exists.",
                "replace_required":
                    True,
                "library_write_performed":
                    False,
            }

        #
        # If we're replacing anything in place,
        # keep a verified rollback copy inside
        # the staging transaction.
        #
        rollback_backup = None

        if destination_existed:
            rollback_backup = (
                transaction
                / (
                    "rollback-library-artifact"
                    + destination.suffix
                )
            )

            rollback_backup.unlink(
                missing_ok=True
            )

            shutil.copy2(
                destination,
                rollback_backup,
            )

            original_destination_hash = (
                _sha256_file(
                    destination
                )
            )

            backup_hash = _sha256_file(
                rollback_backup
            )

            if (
                backup_hash
                != original_destination_hash
            ):
                rollback_backup.unlink(
                    missing_ok=True
                )

                return _failure(
                    "ROLLBACK_BACKUP_FAILED",
                    (
                        "Could not verify rollback "
                        "copy before installation."
                    ),
                    hack_slug,
                    transaction_id,
                )

        temp_destination = (
            destination_root
            / (
                ".hackdex-install-"
                + transaction_id
                + ".tmp"
            )
        )

        temp_destination.unlink(
            missing_ok=True
        )

        shutil.copy2(
            artifact_resolved,
            temp_destination,
        )

        copied_sha256 = (
            _sha256_file(
                temp_destination
            )
        )

        if (
            copied_sha256
            != expected_sha256
        ):
            temp_destination.unlink(
                missing_ok=True
            )

            raise RuntimeError(
                "Copied library artifact "
                "failed SHA-256 verification."
            )

        #
        # Atomic final placement.
        #
        os.replace(
            temp_destination,
            destination,
        )

        final_sha256 = _sha256_file(
            destination
        )

        if (
            final_sha256
            != expected_sha256
        ):
            _restore_destination(
                destination,
                rollback_backup,
            )

            return _failure(
                "FINAL_VERIFY_FAILED",
                (
                    "Installed library artifact "
                    "failed final SHA-256 "
                    "verification. Original file "
                    "was restored when possible."
                ),
                hack_slug,
                transaction_id,
            )

        old_file_retired = False

        #
        # Different-name update:
        #
        # New file is now fully verified.
        # Re-check the old file immediately
        # before removing it.
        #
        if (
            is_update
            and not in_place_update
        ):
            if not old_path.exists():
                _restore_destination(
                    destination,
                    rollback_backup,
                )

                return _failure(
                    "UPDATE_SOURCE_DISAPPEARED",
                    (
                        "Old ROM disappeared "
                        "during update. New install "
                        "was rolled back."
                    ),
                    hack_slug,
                    transaction_id,
                )

            old_final_sha256 = (
                _sha256_file(
                    old_path
                )
            )

            if (
                old_final_sha256
                != old_expected_sha256
            ):
                _restore_destination(
                    destination,
                    rollback_backup,
                )

                return _failure(
                    "UPDATE_SOURCE_CHANGED",
                    (
                        "Old ROM changed during "
                        "the update. New install "
                        "was rolled back."
                    ),
                    hack_slug,
                    transaction_id,
                )

            try:
                old_path.unlink()

            except Exception as exc:
                _restore_destination(
                    destination,
                    rollback_backup,
                )

                return _failure(
                    "OLD_ROM_RETIRE_FAILED",
                    (
                        "New ROM verified, but "
                        "the old ROM could not be "
                        "retired. New install was "
                        "rolled back: "
                        + str(exc)
                    ),
                    hack_slug,
                    transaction_id,
                )

            old_file_retired = True

        update_result = {
            "is_update":
                is_update,
            "previous_version":
                previous_version,
            "target_version":
                target_version,
            "old_filename":
                old_filename
                if is_update
                else None,
            "old_file_retired":
                old_file_retired,
            "in_place_update":
                bool(
                    is_update
                    and in_place_update
                ),
            "retired_rom_id":
                (
                    old_rom_id
                    if (
                        is_update
                        and old_file_retired
                    )
                    else None
                ),
        }

        manifest["status"] = (
            "INSTALLED_VERIFIED"
        )

        manifest[
            "library_write_performed"
        ] = True

        manifest[
            "install_result"
        ] = {
            "filename":
                final_filename,
            "destination":
                str(destination),
            "sha256":
                final_sha256,
            "replaced":
                destination_existed,
        }

        manifest[
            "update_result"
        ] = update_result

        manifest_warning = None
        cleanup_result = None

        try:
            _write_manifest(
                manifest_path,
                manifest,
            )

        except Exception as exc:
            #
            # The library transaction has
            # succeeded already. Do not report
            # it as a failed ROM update merely
            # because transaction history could
            # not be persisted.
            #
            manifest_warning = (
                "Install succeeded but "
                "manifest update failed: "
                + str(exc)
            )

        if manifest_warning is None:
            try:
                cleanup_result = (
                    _cleanup_completed_transaction(
                        transaction,
                        manifest_path,
                        manifest,
                    )
                )

            except Exception as exc:
                manifest_warning = (
                    "Install succeeded but "
                    "staging cleanup failed: "
                    + str(exc)
                )

        cleanup_warning = None

        if manifest_warning is None:

            cleanup_errors = (
                _cleanup_completed_transaction(
                    transaction,
                    manifest_path,
                    manifest,
                )
            )

            if cleanup_errors:
                manifest[
                    "cleanup"
                ] = {
                    "status":
                        "WARNING",

                    "kept":
                        [
                            "manifest.json"
                        ],

                    "errors":
                        cleanup_errors,
                }

                cleanup_warning = (
                    "Install succeeded, but some "
                    "temporary staging files could "
                    "not be removed."
                )

            else:
                manifest[
                    "cleanup"
                ] = {
                    "status":
                        "COMPLETE",

                    "kept":
                        [
                            "manifest.json"
                        ],
                }

            try:
                _write_manifest(
                    manifest_path,
                    manifest,
                )

            except Exception as exc:
                cleanup_warning = (
                    (
                        cleanup_warning
                        + " "
                    )
                    if cleanup_warning
                    else ""
                ) + (
                    "Cleanup completed, but the "
                    "cleanup state could not be "
                    "written to the manifest: "
                    + str(exc)
                )

        return {
            "success": True,
            "status":
                "INSTALLED_VERIFIED",
            "hack":
                hack_slug,
            "transaction_id":
                transaction_id,
            "platform":
                platform,
            "filename":
                final_filename,
            "destination":
                str(destination),
            "sha256":
                final_sha256,
            "replaced":
                destination_existed,
            "library_write_performed":
                True,

            "updated":
                is_update,
            "previous_version":
                previous_version,
            "target_version":
                target_version,
            "old_filename":
                old_filename
                if is_update
                else None,
            "old_file_retired":
                old_file_retired,
            "in_place_update":
                bool(
                    is_update
                    and in_place_update
                ),
            "retired_rom_id":
                (
                    old_rom_id
                    if (
                        is_update
                        and old_file_retired
                    )
                    else None
                ),
            "staging_cleanup":
                cleanup_result,

            "manifest_warning":
                manifest_warning,
            "cleanup_warning":
                cleanup_warning,
        }

    except Exception as exc:
        if temp_destination:
            Path(
                temp_destination
            ).unlink(
                missing_ok=True
            )

        return _failure(
            "INSTALL_FAILED",
            str(exc),
            hack_slug,
            transaction_id,
        )
