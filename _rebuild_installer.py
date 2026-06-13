#!/usr/bin/env python3
"""Rebuild anduril_v2.py after a broken base64 regex edit."""
import base64
from pathlib import Path

ROOT = Path(__file__).parent
broken = (ROOT / "anduril_v2.py").read_text(encoding="utf-8")
app_src = (ROOT / "_app_source.py").read_text(encoding="utf-8")
guide_bytes = (ROOT / "guide.html").read_bytes()

# Prefix: everything before APP_CODE_B64
prefix = broken.split("APP_CODE_B64 = ", 1)[0]

# Suffix: print_summary body + main (from orphaned tail)
orphan = broken.split('"\n    pad = (61 - len(title)) // 2\n', 1)[1]
suffix = "    pad = (61 - len(title)) // 2\n" + orphan

guide_b64 = base64.b64encode(guide_bytes).decode("ascii")
app_b64 = base64.b64encode(app_src.encode("utf-8")).decode("ascii")

# Refresh GUIDE_B64 in prefix
import re
prefix = re.sub(
    r'^GUIDE_B64 = "[^"]*"\s*\n',
    f'GUIDE_B64 = "{guide_b64}"\n\n',
    prefix,
    count=1,
    flags=re.MULTILINE,
)

MIDDLE = '''
APP_CODE_B64 = "__APP_B64__"

def write_app():
    section("Writing Application Files")
    global _steps_total
    _steps_total += 4

    step("Decoding dashboard app")
    app_code = base64.b64decode(APP_CODE_B64).decode("utf-8")
    ast.parse(app_code)
    ok(f"app.py — {len(app_code.splitlines())} lines")

    step("Writing dashboard/app.py")
    app_path = DASH_DIR / "app.py"
    app_path.write_text(app_code, encoding="utf-8")
    ok(str(app_path))

    step("Writing guide.html")
    guide_dest = INSTALL_ROOT / "guide.html"
    local_guide = SCRIPT_DIR / "guide.html"
    if local_guide.exists():
        shutil.copy2(local_guide, guide_dest)
        ok(f"Copied {local_guide.name}")
    else:
        guide_dest.write_bytes(base64.b64decode(GUIDE_B64))
        ok("Written from embedded guide")

    step("Writing logo assets")
    (INSTALL_ROOT / "anduril_logo.svg").write_bytes(base64.b64decode(LOGO_B64))
    (INSTALL_ROOT / "anduril_logo.jpg").write_bytes(base64.b64decode(LOGO_JPG_B64))
    ok("Logo files written")

def write_launcher():
    section("Creating Launcher")
    global _steps_total
    _steps_total += 2

    step("Writing launch script")
    if IS_WIN:
        launch = INSTALL_ROOT / "launch.bat"
        launch.write_text(textwrap.dedent(f"""\
            @echo off
            call "{VENV_DIR / 'Scripts' / 'activate.bat'}"
            echo.
            echo   Anduril Trading Suite starting...
            echo   Opening browser at http://127.0.0.1:8050
            echo   Press Ctrl+C to stop.
            echo.
            timeout /t 2 /nobreak >nul
            start http://127.0.0.1:8050
            "{PYTHON_EXE}" "{DASH_DIR / 'app.py'}"
        """))
        ok(str(launch))
    else:
        launch = INSTALL_ROOT / "launch.sh"
        launch.write_text(textwrap.dedent(f"""\
            #!/usr/bin/env bash
            source "{VENV_DIR / 'bin' / 'activate'}"
            echo ""
            echo "  Anduril Trading Suite starting..."
            echo "  Opening browser at http://127.0.0.1:8050"
            echo "  Press Ctrl+C to stop.  |  Open guide: {INSTALL_ROOT / 'guide.html'}"
            echo ""
            sleep 1
            open "http://127.0.0.1:8050" 2>/dev/null || xdg-open "http://127.0.0.1:8050" 2>/dev/null || true
            python "{DASH_DIR / 'app.py'}"
        """))
        launch.chmod(0o755)
        ok(str(launch))

    step("Creating desktop shortcut")
    try:
        if IS_WIN:
            desktop = Path.home() / "Desktop" / "Anduril Trading.bat"
            shutil.copy2(launch, desktop)
        elif IS_MAC:
            cmd = INSTALL_ROOT / "Anduril Trading.command"
            cmd.write_text(textwrap.dedent(f"""\
                #!/usr/bin/env bash
                source "{VENV_DIR / 'bin' / 'activate'}"
                open "http://127.0.0.1:8050"
                python "{DASH_DIR / 'app.py'}"
            """))
            cmd.chmod(0o755)
            desktop = Path.home() / "Desktop" / "Anduril Trading.command"
            if desktop.exists():
                desktop.unlink()
            shutil.copy2(cmd, desktop)
        else:
            desktop = Path.home() / "Desktop" / "Anduril Trading.desktop"
            desktop.write_text(textwrap.dedent(f"""\
                [Desktop Entry]
                Name=Anduril Trading
                Comment=Personal Trading Dashboard
                Exec=bash {INSTALL_ROOT / 'launch.sh'}
                Icon={INSTALL_ROOT / 'anduril_logo.svg'}
                Terminal=true
                Type=Application
                Categories=Finance;
            """))
            desktop.chmod(0o755)
        ok(f"Desktop shortcut created")
    except Exception as e:
        warn(f"Desktop shortcut skipped: {e}")

def print_summary():
    print()
    title = "INSTALLATION COMPLETE"
    print(clr(C, "  " + "═" * 63))
    print(clr(C, "  ║") + " " * 63 + clr(C, "║"))
'''

middle = MIDDLE.replace("__APP_B64__", app_b64)

out = prefix + middle + suffix
out_path = ROOT / "anduril_v2.py"
out_path.write_text(out, encoding="utf-8")

# Verify syntax
compile(out, str(out_path), "exec")
print(f"Rebuilt {out_path} ({len(out.splitlines())} lines)")
print("Syntax OK")
