#!/usr/bin/env python3
"""Install only this experiment's per-user icon, command and app-menu entry."""
from datetime import datetime
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
launcher = Path.home() / ".local/bin/omacad-hybrid"
desktop = data / "applications/omacad-hybrid.desktop"
icon = data / "icons/hicolor/scalable/apps/omacad-hybrid.svg"
ET.parse(root / "assets/icon-hybrid.svg")


def write(path, content, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(path, path.with_name(path.name + ".bak." + stamp))
    path.write_text(content)
    path.chmod(0o755 if executable else 0o644)


# Exec fields have their own quoting rules; shell quoting belongs in the wrapper only.
def exec_quote(value):
    value = str(value).replace("%", "%%")
    for char in ["\\", '"', "`", "$"]:
        value = value.replace(char, "\\" + char)
    return '"' + value + '"'


write(launcher, "#!/usr/bin/env bash\nexec " + shlex.quote(str(root / "run.sh")) + ' --backend rust "$@"\n', executable=True)
write(icon, (root / "assets/icon-hybrid.svg").read_text())
write(desktop, f'''[Desktop Entry]
Type=Application
Name=Omacad Hybrid
GenericName=3D CAD Modeler
Comment=Omacad with experimental Rust viewport picking
Comment[sv]=Omacad med experimentell Rust-accelererad viewportplockning
Exec={exec_quote(launcher)}
TryExec={launcher}
Icon=omacad-hybrid
Terminal=false
Categories=Graphics;Engineering;3DGraphics;
StartupWMClass=omacad-hybrid
Keywords=CAD;Omacad;Hybrid;Rust;Python;3D;Modeling;
''')
if shutil.which("desktop-file-validate"):
    subprocess.run(["desktop-file-validate", str(desktop)], check=True)
if shutil.which("update-desktop-database"):
    subprocess.run(["update-desktop-database", str(desktop.parent)], check=True)
print(f"Installed Omacad Hybrid: {desktop}")
