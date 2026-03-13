"""Desktop application launcher: pywebview window + pystray system tray + uvicorn backend."""

from __future__ import annotations

import atexit
import os
import signal
import sys
import threading
import time
from pathlib import Path

from loguru import logger


def start_desktop(
    *,
    app: object,
    host: str = "127.0.0.1",
    port: int = 18791,
    title: str = "CMClaw",
) -> None:
    """Launch the desktop application.

    Orchestrates three components:
    - uvicorn HTTP server in a background daemon thread
    - pystray system tray icon in a background daemon thread
    - pywebview native window on the main thread (required by Windows)

    On quit (tray menu, window close without tray, Ctrl+C, or SIGTERM)
    all threads are stopped and the process exits cleanly.
    """
    import uvicorn

    uvicorn_kwargs = {
        "host": host,
        "port": port,
        "log_level": "info",
        "loop": "asyncio",
        # Prefer wsproto for desktop webview compatibility and fewer
        # protocol-specific handshake edge cases.
        "ws": "wsproto",
    }
    if getattr(sys, "stdout", None) is None or getattr(sys, "stderr", None) is None:
        uvicorn_kwargs["log_config"] = None
        uvicorn_kwargs["access_log"] = False

    server_config = uvicorn.Config(app, **uvicorn_kwargs)
    server = uvicorn.Server(server_config)

    # Track components for cleanup
    _tray = None
    _window = None
    _shutdown_called = threading.Event()

    def _shutdown():
        """Forcefully shut down all components."""
        if _shutdown_called.is_set():
            return
        _shutdown_called.set()
        logger.info("Shutting down desktop app...")

        server.should_exit = True

        if _tray:
            try:
                _tray.stop()
            except Exception:
                pass

        if _window:
            try:
                _window.destroy()
            except Exception:
                pass

        # Give threads 2s to finish, then force exit
        def _force_exit():
            time.sleep(2)
            if not _shutdown_called.is_set():
                return
            logger.debug("Force exit")
            os._exit(0)

        threading.Thread(target=_force_exit, daemon=True).start()

    # Register cleanup handlers
    atexit.register(_shutdown)

    def _signal_handler(sig, frame):
        _shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # --- 1. Start uvicorn in background thread ---
    server_thread = threading.Thread(target=server.run, daemon=True, name="uvicorn")
    server_thread.start()

    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)

    if not server.started:
        server.should_exit = True
        raise RuntimeError(f"Desktop backend failed to start on http://{host}:{port}")

    url = f"http://{host}:{port}"
    logger.info("Backend ready at {}", url)

    # --- 2. Try pywebview (native window) ---
    try:
        import webview

        # --- 3. Try system tray ---
        try:
            import pystray
            from PIL import Image, ImageDraw

            def _create_icon() -> Image.Image:
                logo_path = Path(__file__).resolve().parent.parent / "webui" / "static" / "cmclaw.png"
                if logo_path.exists():
                    return Image.open(logo_path).convert("RGBA").resize((64, 64), Image.LANCZOS)

                img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                draw.ellipse([4, 4, 60, 60], fill=(60, 135, 251, 255))
                draw.text((16, 18), "C", fill=(255, 255, 255, 255))
                return img

            def _show():
                if _window:
                    _window.show()
                    _window.restore()

            menu = pystray.Menu(
                pystray.MenuItem("打开 CMClaw", lambda: _show(), default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", lambda: _shutdown()),
            )
            _tray = pystray.Icon("cmclaw", _create_icon(), "CMClaw", menu)
            threading.Thread(target=_tray.run, daemon=True, name="tray").start()
            logger.info("System tray icon active")
        except ImportError:
            logger.info("pystray/Pillow not available — no tray icon")

        # --- 4. Native window on main thread ---
        _window = webview.create_window(
            title, url,
            width=1100, height=750,
            min_size=(600, 450),
            text_select=True,
        )

        def _on_closing():
            """When tray exists: minimize to tray. Otherwise: quit."""
            if _tray:
                _window.hide()
                return False
            _shutdown()
            return True

        _window.events.closing += _on_closing

        webview.start()

    except ImportError:
        logger.info("pywebview not available — opening browser")
        import webbrowser
        webbrowser.open(url)
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass

    _shutdown()
