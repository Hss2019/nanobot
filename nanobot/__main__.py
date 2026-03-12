"""
Entry point for running nanobot as a module: python -m nanobot
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from nanobot.cli.commands import app


def _write_crash_log(trace: str) -> Path | None:
    """Persist startup crash details for desktop launches."""
    try:
        from nanobot.config.paths import get_logs_dir

        logs_dir = get_logs_dir()
        path = logs_dir / f"cmclaw-crash-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
        path.write_text(trace, encoding="utf-8")
        return path
    except Exception:
        return None


def _show_windows_error(trace: str, log_path: Path | None) -> None:
    """Show a native Windows error dialog for windowed desktop launches."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        preview = "\n".join(trace.strip().splitlines()[-8:])
        message = "CMClaw 启动失败。\n\n"
        if log_path:
            message += f"崩溃日志：{log_path}\n\n"
        message += preview[:1500]
        ctypes.windll.user32.MessageBoxW(0, message, "CMClaw 启动失败", 0x10)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        app()
    except BaseException:
        trace = traceback.format_exc()
        log_path = _write_crash_log(trace)
        print("\nCMClaw startup failed.\n", file=sys.stderr)
        print(trace, file=sys.stderr)
        if log_path:
            print(f"Crash log saved to: {log_path}", file=sys.stderr)
        _show_windows_error(trace, log_path)
        raise
