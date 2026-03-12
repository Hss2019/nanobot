"""Desktop application launcher: pywebview window + pystray system tray + uvicorn backend."""

from __future__ import annotations

import sys
import threading
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    pass


def start_desktop(
    *,
    app: object,
    host: str = "127.0.0.1",
    port: int = 18791,
    title: str = "Nanobot",
) -> None:
    """Launch the desktop application.

    Orchestrates three components:
    - uvicorn HTTP server in a background daemon thread
    - pystray system tray icon in a background daemon thread
    - pywebview native window on the main thread (required by Windows)
    """
    import uvicorn

    # --- 1. Start uvicorn in background thread ---
    server_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(server_config)

    server_thread = threading.Thread(target=server.run, daemon=True, name="uvicorn")
    server_thread.start()

    # Wait for server to be ready
    import time
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)

    url = f"http://{host}:{port}"
    logger.info("Backend ready at {}", url)

    # --- 2. Try to launch pywebview (native window) ---
    window = None
    tray = None

    try:
        import webview

        def _on_closing():
            """Minimize to tray instead of quitting (if tray is available)."""
            if tray and window:
                window.hide()
                return False  # prevent close
            return True  # allow close

        def _show_window():
            if window:
                window.show()
                window.restore()

        def _quit_app():
            if tray:
                tray.stop()
            if window:
                window.destroy()
            server.should_exit = True

        # --- 3. Try to set up system tray ---
        try:
            import pystray
            from PIL import Image, ImageDraw

            def _create_tray_icon() -> Image.Image:
                """Create a simple colored circle icon."""
                img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                draw.ellipse([4, 4, 60, 60], fill=(233, 69, 96, 255))
                draw.text((20, 18), "N", fill=(255, 255, 255, 255))
                return img

            menu = pystray.Menu(
                pystray.MenuItem("Open Nanobot", lambda: _show_window(), default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", lambda: _quit_app()),
            )
            tray = pystray.Icon("nanobot", _create_tray_icon(), "Nanobot", menu)

            tray_thread = threading.Thread(target=tray.run, daemon=True, name="tray")
            tray_thread.start()
            logger.info("System tray icon active")
        except ImportError:
            logger.info("pystray/Pillow not available — no system tray icon")

        # --- 4. Launch native window on main thread ---
        window = webview.create_window(
            title,
            url,
            width=900,
            height=700,
            min_size=(500, 400),
        )
        if tray:
            window.events.closing += _on_closing

        webview.start()

    except ImportError:
        logger.info("pywebview not available — falling back to browser")
        import webbrowser
        webbrowser.open(url)
        # Keep main thread alive
        try:
            server_thread.join()
        except KeyboardInterrupt:
            pass

    # Cleanup
    server.should_exit = True
    if tray:
        try:
            tray.stop()
        except Exception:
            pass
