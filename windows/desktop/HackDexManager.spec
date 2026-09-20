# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
)


ROOT = Path(SPECPATH).resolve().parents[1]
ICON_PATH = ROOT / "windows" / "assets" / "HackDexManager.ico"
APP = ROOT / "app"

xdelta_binary = (
    ROOT
    / "windows"
    / "third_party"
    / "xdelta3"
    / "xdelta3.exe"
)


webview_datas, webview_binaries, webview_hidden = (
    collect_all("webview")
)


datas = [
    (
        str(APP / "templates"),
        "app/templates",
    ),
    (
        str(APP / "static"),
        "app/static",
    ),
]

datas += webview_datas

datas += [
    (
        str(
            ROOT
            / "windows"
            / "third_party"
            / "xdelta3"
            / "LICENSE-xdelta.txt"
        ),
        "third_party/xdelta3",
    ),
    (
        str(
            ROOT
            / "windows"
            / "third_party"
            / "xdelta3"
            / "README-xdelta.txt"
        ),
        "third_party/xdelta3",
    ),
]


# Include generic application data files if the repository gains
# any later. Runtime databases and user data are intentionally not
# bundled.
for pattern in (
    "*.json",
    "*.yaml",
    "*.yml",
    "*.txt",
):
    for item in APP.glob(pattern):
        if item.is_file():
            datas.append(
                (
                    str(item),
                    "app",
                )
            )


hiddenimports = []

hiddenimports += webview_hidden

hiddenimports += collect_submodules(
    "uvicorn"
)

hiddenimports += collect_submodules(
    "apscheduler"
)

hiddenimports += collect_submodules(
    "py7zr"
)

hiddenimports += collect_submodules(
    "sqlalchemy.dialects.sqlite"
)


a = Analysis(
    [
        str(
            ROOT
            / "windows"
            / "desktop"
            / "launcher.py"
        )
    ],
    pathex=[
        str(ROOT),
        str(APP),
    ],
    binaries=(
        webview_binaries
        + [
            (
                str(xdelta_binary),
                "tools",
            )
        ]
    ),
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)


pyz = PYZ(
    a.pure
)


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HackDex Manager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    icon=str(ICON_PATH),
    console=False,
    disable_windowed_traceback=False,
)


coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HackDex Manager",
)
