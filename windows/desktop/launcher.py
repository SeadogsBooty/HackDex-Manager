"""HackDex Manager Windows desktop launcher.

The desktop edition hosts the existing HackDex Manager web UI inside
a native Windows application window. The web server is loopback-only
and uses a dynamically selected local port.
"""

from __future__ import annotations

import contextlib
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[2]


ROOT = application_root()
APP_DIR = ROOT / "app"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


# Desktop mode must be established before importing HackDex.
os.environ["HACKDEX_DESKTOP"] = "1"

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

        window = webview.create_window(
            APP_TITLE,
            server.url,
            width=1500,
            height=950,
            min_size=(1100, 700),
            resizable=True,
            text_select=True,
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
