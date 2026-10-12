"""HackDex Manager Windows desktop launcher.

The desktop edition hosts the existing HackDex Manager web UI inside
a native Windows application window. The web server is loopback-only
and uses a dynamically selected local port.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path


def application_root() -> Path:
    """Return the root containing bundled HackDex resources."""

    if getattr(sys, "frozen", False):
        bundled_root = getattr(
            sys,
            "_MEIPASS",
            None,
        )

        if bundled_root:
            return Path(
                bundled_root
            ).resolve()

        return Path(
            sys.executable
        ).resolve().parent

    return Path(__file__).resolve().parents[2]


ROOT = application_root()
APP_DIR = ROOT / "app"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


# Desktop mode and writable application workspace must be
# established before importing any HackDex application module.
os.environ["HACKDEX_DESKTOP"] = "1"


def desktop_data_root() -> Path:
    """
    Frozen Windows application:
        use the directory containing HackDex Manager.exe.

    Development:
        use repository-local .desktop-runtime.

    HACKDEX_DATA_ROOT remains available as an explicit override.
    """

    explicit = str(
        os.environ.get(
            "HACKDEX_DATA_ROOT",
            "",
        )
        or ""
    ).strip()

    if explicit:
        return Path(
            explicit
        )

    if getattr(
        sys,
        "frozen",
        False,
    ):
        return (
            Path(sys.executable)
            .resolve()
            .parent
        )

    return (
        Path(__file__)
        .resolve()
        .parents[2]
        / ".desktop-runtime"
    )


os.environ[
    "HACKDEX_DATA_ROOT"
] = str(
    desktop_data_root()
)


# Desktop mode must be established before importing HackDex.

from platform_paths import ensure_runtime_directories  # noqa: E402

ensure_runtime_directories()

# Import the Windows desktop shell while the process is still rooted
# at the repository directory. PyWebView resolves its application base
# path during import.
import uvicorn  # noqa: E402
import webview  # noqa: E402

# HackDex historically runs with the app directory as its working
# directory. Preserve that behavior for templates/static assets before
# importing the FastAPI application.
os.chdir(APP_DIR)

from main import app  # noqa: E402


APP_TITLE = "HackDex Manager"
HOST = "127.0.0.1"



def _safe_update_url(
    value: str,
) -> bool:
    parsed = urllib.parse.urlparse(
        str(value or "").strip()
    )

    if parsed.scheme in {
        "https",
        "file",
    }:
        return True

    return (
        parsed.scheme == "http"
        and parsed.hostname
        in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
    )


def _powershell_literal(value) -> str:
    return (
        "'"
        + str(value).replace(
            "'",
            "''",
        )
        + "'"
    )


def _download_update(
    url: str,
    destination: Path,
) -> None:
    parsed = urllib.parse.urlparse(
        url
    )

    if parsed.scheme == "file":
        local = urllib.request.url2pathname(
            parsed.path
        )

        if parsed.netloc:
            local = (
                "//"
                + parsed.netloc
                + local
            )

        shutil.copy2(
            local,
            destination,
        )
        return

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "HackDex-Manager-Updater",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=60,
    ) as response:
        with destination.open("wb") as handle:
            shutil.copyfileobj(
                response,
                handle,
            )


class DesktopBridge:
    """Native functionality exposed only to the desktop WebView."""

    def install_update(
        self,
        url: str,
        sha256: str,
        version: str | None = None,
    ) -> dict:
        """Download, verify, apply, and relaunch a Windows installer."""

        try:
            if (
                os.name != "nt"
                or not getattr(
                    sys,
                    "frozen",
                    False,
                )
            ):
                return {
                    "success": False,
                    "error":
                        "Automatic installation is available only "
                        "in the packaged Windows edition.",
                }

            url = str(url or "").strip()
            expected = str(
                sha256 or ""
            ).strip().lower()

            if not _safe_update_url(url):
                return {
                    "success": False,
                    "error":
                        "The installer URL is not allowed.",
                }

            if (
                len(expected) != 64
                or any(
                    character
                    not in "0123456789abcdef"
                    for character in expected
                )
            ):
                return {
                    "success": False,
                    "error":
                        "The installer SHA-256 is invalid.",
                }

            work = (
                Path(tempfile.gettempdir())
                / "HackDexManagerUpdate"
            )

            work.mkdir(
                parents=True,
                exist_ok=True,
            )

            installer = (
                work
                / "HackDex.Manager.Setup.exe"
            )

            _download_update(
                url,
                installer,
            )

            digest = hashlib.sha256()

            with installer.open("rb") as handle:
                for chunk in iter(
                    lambda: handle.read(
                        1024 * 1024
                    ),
                    b"",
                ):
                    digest.update(chunk)

            actual = digest.hexdigest()

            if actual != expected:
                installer.unlink(
                    missing_ok=True
                )

                return {
                    "success": False,
                    "error":
                        "Installer verification failed. "
                        "The downloaded SHA-256 did not match.",
                }

            current_exe = (
                Path(sys.executable)
                .resolve()
            )

            helper = (
                work
                / "apply-update.ps1"
            )

            helper.write_text(
                "\n".join([
                    "$ErrorActionPreference = 'Stop'",
                    (
                        "$installer = "
                        + _powershell_literal(
                            installer
                        )
                    ),
                    (
                        "$currentExe = "
                        + _powershell_literal(
                            current_exe
                        )
                    ),
                    (
                        "$pidToWait = "
                        + str(os.getpid())
                    ),
                    (
                        "while (Get-Process -Id $pidToWait "
                        "-ErrorAction SilentlyContinue) { "
                        "Start-Sleep -Milliseconds 250 }"
                    ),
                    (
                        "$process = Start-Process -FilePath $installer "
                        "-ArgumentList @('/VERYSILENT', "
                        "'/SUPPRESSMSGBOXES', '/NORESTART', '/SP-') "
                        "-Wait -PassThru"
                    ),
                    (
                        "if ($process.ExitCode -ne 0) { "
                        "exit $process.ExitCode }"
                    ),
                    (
                        "if (Test-Path $currentExe) { "
                        "Start-Process -FilePath $currentExe }"
                    ),
                ]),
                encoding="utf-8",
            )

            creationflags = (
                getattr(
                    subprocess,
                    "DETACHED_PROCESS",
                    0,
                )
                | getattr(
                    subprocess,
                    "CREATE_NEW_PROCESS_GROUP",
                    0,
                )
            )

            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(helper),
                ],
                close_fds=True,
                creationflags=creationflags,
            )

            def close_application():
                try:
                    if webview.windows:
                        webview.windows[0].destroy()
                except Exception:
                    pass

            threading.Timer(
                0.8,
                close_application,
            ).start()

            return {
                "success": True,
                "version": str(
                    version or ""
                ),
                "sha256": actual,
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }


    def select_folder(
        self,
        directory: str | None = None,
    ) -> dict:
        """Open the native Windows folder picker."""
        try:
            if not webview.windows:
                return {
                    "selected": False,
                    "path": "",
                    "error":
                        "Desktop window is not available.",
                }

            window = webview.windows[0]

            result = (
                window.create_file_dialog(
                    webview.FileDialog.FOLDER,
                    directory=directory or "",
                    allow_multiple=False,
                )
            )

            if not result:
                return {
                    "selected": False,
                    "path": "",
                    "error": "",
                }

            if isinstance(
                result,
                (tuple, list),
            ):
                selected = (
                    str(result[0])
                    if result
                    else ""
                )
            else:
                selected = str(result)

            return {
                "selected":
                    bool(selected),

                "path":
                    selected,

                "error":
                    "",
            }

        except Exception as exc:
            return {
                "selected": False,
                "path": "",
                "error": str(exc),
            }

def reserve_port() -> int:
    """Ask Windows for a currently unused loopback TCP port."""
    with contextlib.closing(
        socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )
    ) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def wait_for_backend(
    url: str,
    timeout: float = 30.0,
) -> None:
    """Wait until HackDex's HTTP endpoint responds."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(
                f"{url}/health",
                timeout=1.0,
            ) as response:
                if response.status == 200:
                    return

        except Exception as exc:
            last_error = exc

        time.sleep(0.15)

    raise RuntimeError(
        "HackDex Manager backend did not become ready."
    ) from last_error


class DesktopServer:
    def __init__(self) -> None:
        self.port = reserve_port()
        self.url = f"http://{HOST}:{self.port}"

        config = uvicorn.Config(
            app,
            host=HOST,
            port=self.port,
            log_level="warning",
            access_log=False,
        )

        self.server = uvicorn.Server(config)

        self.thread = threading.Thread(
            target=self.server.run,
            name="HackDexBackend",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()
        wait_for_backend(self.url)

    def stop(self) -> None:
        self.server.should_exit = True

        if self.thread.is_alive():
            self.thread.join(timeout=5.0)


def main() -> int:
    server = DesktopServer()

    try:
        server.start()

        bridge = DesktopBridge()

        window = webview.create_window(
            APP_TITLE,
            server.url,
            width=1500,
            height=950,
            min_size=(1100, 700),
            resizable=True,
            text_select=True,
            js_api=bridge,
        )

        webview.start(
            gui="edgechromium",
            debug=False,
        )

        return 0

    finally:
        server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
