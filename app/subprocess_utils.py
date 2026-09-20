from __future__ import annotations

import os
import subprocess


def hidden_subprocess_kwargs():
    """Hide child console programs in the Windows desktop app."""

    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()

    startupinfo.dwFlags |= (
        subprocess.STARTF_USESHOWWINDOW
    )

    startupinfo.wShowWindow = (
        subprocess.SW_HIDE
    )

    return {
        "startupinfo": startupinfo,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }
