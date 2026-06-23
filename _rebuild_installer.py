#!/usr/bin/env python3
"""Rebuild anduril_v2.py after a broken base64 regex edit."""
import base64
from pathlib import Path

ROOT = Path(__file__).parent
broken = (ROOT / "anduril_v2.py").read_text(encoding="utf-8")
app_src = (ROOT / "_app_source.py").read_text(encoding="utf-8")
guide_bytes = (ROOT / "guide.html").read_bytes()
options_guide_bytes = (ROOT / "options_guide.html").read_bytes()

# Prefix: everything before APP_CODE_B64; suffix: write_launcher onward
prefix = broken.split("APP_CODE_B64 = ", 1)[0]
suffix = "def write_launcher():" + broken.split("def write_launcher():", 1)[1]

guide_b64 = base64.b64encode(guide_bytes).decode("ascii")
options_guide_b64 = base64.b64encode(options_guide_bytes).decode("ascii")
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
if re.search(r'^OPTIONS_GUIDE_B64 = ', prefix, flags=re.MULTILINE):
    prefix = re.sub(
        r'^OPTIONS_GUIDE_B64 = "[^"]*"\s*\n',
        f'OPTIONS_GUIDE_B64 = "{options_guide_b64}"\n\n',
        prefix,
        count=1,
        flags=re.MULTILINE,
    )
else:
    prefix = re.sub(
        r'(^GUIDE_B64 = "[^"]*"\s*\n\n)',
        f'\\1OPTIONS_GUIDE_B64 = "{options_guide_b64}"\n\n',
        prefix,
        count=1,
        flags=re.MULTILINE,
    )

MIDDLE = '''
APP_CODE_B64 = "__APP_B64__"

def write_app():
    section("Writing Application Files")
    global _steps_total
    _steps_total += 5

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

    step("Writing options_guide.html")
    og_dest = INSTALL_ROOT / "options_guide.html"
    local_og = SCRIPT_DIR / "options_guide.html"
    if local_og.exists():
        shutil.copy2(local_og, og_dest)
        ok(f"Copied {local_og.name}")
    else:
        og_dest.write_bytes(base64.b64decode(OPTIONS_GUIDE_B64))
        ok("Written from embedded options guide")

    step("Writing logo assets")
    (INSTALL_ROOT / "anduril_logo.svg").write_bytes(base64.b64decode(LOGO_B64))
    local_pngs = _logo_png_sources()
    if local_pngs:
        for src in local_pngs:
            shutil.copy2(src, INSTALL_ROOT / src.name)
        ok(f"Logo PNGs → {', '.join(p.name for p in local_pngs)}")
    else:
        (INSTALL_ROOT / LOGO_PNG_NAME).write_bytes(base64.b64decode(LOGO_PNG_B64))
        ok(f"Logo written → {LOGO_PNG_NAME}")

'''

middle = MIDDLE.replace("__APP_B64__", app_b64)

out = prefix + middle + suffix
out_path = ROOT / "anduril_v2.py"
out_path.write_text(out, encoding="utf-8")

# Verify syntax
compile(out, str(out_path), "exec")
print(f"Rebuilt {out_path} ({len(out.splitlines())} lines)")
print("Syntax OK")
