"""PyInstaller build script for CMClaw Desktop on Windows.

Usage (run on Windows):
    pip install nanobot-ai[desktop] pyinstaller
    python scripts/build_windows.py

Output: dist/cmclaw/ directory containing cmclaw.exe
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
ENTRY = ROOT / "nanobot" / "__main__.py"
STATIC = ROOT / "nanobot" / "webui" / "static"
TEMPLATES = ROOT / "nanobot" / "templates"
SKILLS = ROOT / "nanobot" / "skills"

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--name", "cmclaw",
    "--noconfirm",
    # Include static web UI files
    "--add-data", f"{STATIC};nanobot/webui/static",
]

# Include templates and skills if they exist
if TEMPLATES.exists():
    cmd += ["--add-data", f"{TEMPLATES};nanobot/templates"]
if SKILLS.exists():
    cmd += ["--add-data", f"{SKILLS};nanobot/skills"]

try:
    import litellm

    litellm_dir = Path(litellm.__file__).resolve().parent
    backup_map = litellm_dir / "model_prices_and_context_window_backup.json"
    if backup_map.exists():
        cmd += ["--add-data", f"{backup_map};litellm"]
except Exception:
    pass

cmd += [
    # Hidden imports that PyInstaller may miss
    "--hidden-import", "nanobot.cli.commands",
    "--hidden-import", "nanobot.channels.web",
    "--hidden-import", "nanobot.webui.server",
    "--hidden-import", "nanobot.desktop.app",
    "--hidden-import", "uvicorn",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols",
    "--hidden-import", "uvicorn.protocols.http",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan",
    "--hidden-import", "uvicorn.lifespan.on",
    "--hidden-import", "fastapi",
    "--hidden-import", "webview",
    "--hidden-import", "pystray",
    "--hidden-import", "tiktoken_ext.openai_public",
    "--hidden-import", "tiktoken_ext",
    # Console mode (shows logs; use --windowed for no console)
    "--console",
    str(ENTRY),
]

print("正在构建 cmclaw.exe ...")
print(" ".join(cmd))
subprocess.run(cmd, check=True)
print("\n完成！输出路径: dist/cmclaw/cmclaw.exe")
print("运行: dist\\cmclaw\\cmclaw.exe desktop")
