"""PyInstaller build script for CMClaw Desktop on Windows.

Usage (run on Windows):
    pip install nanobot-ai[desktop] pyinstaller
    python scripts/build_windows.py

Output: dist/cmclaw/ directory containing cmclaw.exe
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
ENTRY = ROOT / "nanobot" / "__main__.py"
STATIC = ROOT / "nanobot" / "webui" / "static"
TEMPLATES = ROOT / "nanobot" / "templates"
SKILLS = ROOT / "nanobot" / "skills"
ICON_PNG = STATIC / "cmclaw.png"
ICON_ICO = ROOT / "scripts" / "cmclaw.ico"


def _ensure_windows_icon() -> Path | None:
    """Create a Windows .ico from the bundled PNG when Pillow is available."""
    if not ICON_PNG.exists():
        return None
    try:
        from PIL import Image

        img = Image.open(ICON_PNG).convert("RGBA")
        sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(ICON_ICO, format="ICO", sizes=sizes)
        return ICON_ICO
    except Exception as exc:
        print(f"Warning: failed to generate icon: {exc}")
        return None


def _run_smoke_test(exe_path: Path) -> None:
    """Fail fast on missing hidden imports before producing an installer."""
    print("\n运行构建后自检 ...")
    tests = [
        [str(exe_path), "desktop", "--help"],
        [str(exe_path), "status"],
    ]
    for cmd in tests:
        print(" ".join(cmd))
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=False,
            env=env,
        )
        if result.returncode != 0:
            stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            print(stdout)
            print(stderr)
            raise subprocess.CalledProcessError(result.returncode, cmd)

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

icon_path = _ensure_windows_icon()
if icon_path:
    cmd += ["--icon", str(icon_path)]

try:
    import litellm

    litellm_dir = Path(litellm.__file__).resolve().parent
    backup_map = litellm_dir / "model_prices_and_context_window_backup.json"
    tokenizers_dir = litellm_dir / "litellm_core_utils" / "tokenizers"
    if backup_map.exists():
        cmd += ["--add-data", f"{backup_map};litellm"]
    if tokenizers_dir.exists():
        cmd += ["--add-data", f"{tokenizers_dir};litellm/litellm_core_utils/tokenizers"]
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
    "--hidden-import", "litellm.litellm_core_utils",
    "--hidden-import", "litellm.litellm_core_utils.tokenizers",
    "--collect-submodules", "litellm.litellm_core_utils",
    # Console mode (shows logs; use --windowed for no console)
    "--console",
    str(ENTRY),
]

print("正在构建 cmclaw.exe ...")
print(" ".join(cmd))
subprocess.run(cmd, check=True)
_run_smoke_test(ROOT / "dist" / "cmclaw" / "cmclaw.exe")
print("\n完成！输出路径: dist/cmclaw/cmclaw.exe")
print("运行: dist\\cmclaw\\cmclaw.exe desktop")
