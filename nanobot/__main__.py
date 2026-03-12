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
        if sys.platform == "win32":
            try:
                input("\nPress Enter to close this window...")
            except EOFError:
                pass
        raise
