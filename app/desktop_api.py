"""FastAPI routes used by the HackDex Manager desktop shell."""

from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter

from desktop_storage import (
    describe_windows_location,
    desktop_mode,
    validate_library_location,
)
from platform_paths import (
    data_dir,
    staging_dir,
)


router = APIRouter(
    prefix="/api/desktop",
    tags=["desktop"],
)


class PathValidationRequest(
    BaseModel
):
    path: str
    require_write: bool = False
    probe: bool = True


@router.get("/status")
def desktop_status():
    return {
        "desktop_mode":
            desktop_mode(),
        "data_dir":
            str(data_dir()),
        "staging_dir":
            str(staging_dir()),
        "supports": {
            "local_drives": True,
            "mapped_drives": True,
            "unc_shares": True,
        },
    }


@router.post("/path/validate")
def desktop_validate_path(
    payload: PathValidationRequest,
):
    return validate_library_location(
        payload.path,
        require_write=(
            payload.require_write
        ),
        probe=payload.probe,
    )


@router.post("/path/describe")
def desktop_describe_path(
    payload: PathValidationRequest,
):
    return describe_windows_location(
        payload.path
    )
