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


def _safe_stderr_print(*parts: object) -> None:
    """Best-effort stderr/stdout print that tolerates windowed mode streams being absent."""
    stream = getattr(sys, "stderr", None) or getattr(sys, "stdout", None)
    if stream is None:
        return
    try:
        print(*parts, file=stream)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        if getattr(sys, "frozen", False) and sys.platform == "win32" and len(sys.argv) == 1:
            sys.argv.append("desktop")
        app()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 0
        if code in (0, None):
            pass
        else:
            trace = traceback.format_exc()
            log_path = _write_crash_log(trace)
            _safe_stderr_print("\nCMClaw startup failed.\n")
            _safe_stderr_print(trace)
            if log_path:
                _safe_stderr_print(f"Crash log saved to: {log_path}")
            _show_windows_error(trace, log_path)
            raise
    except Exception:
        trace = traceback.format_exc()
        log_path = _write_crash_log(trace)
        _safe_stderr_print("\nCMClaw startup failed.\n")
        _safe_stderr_print(trace)
        if log_path:
            _safe_stderr_print(f"Crash log saved to: {log_path}")
        _show_windows_error(trace, log_path)
        raise
