"""Every sketch tool the viewport handles must be in the registry, or it will be missing from the right-click menu."""
import re
from pathlib import Path

from omacad.ui.sketch_tools import SKETCH_TOOLS, NON_MENU_TOOLS


def test_all_viewport_tools_are_registered():
    vp_path = Path(__file__).parent.parent / "omacad" / "ui" / "viewport.py"
    if not vp_path.exists():
        vp_path = Path(__file__).parent.parent / "omacad" / "ui" / "viewport" / "viewport.py"
    src = vp_path.read_text()
    used = set(re.findall(r'sketch_tool (?:==|!=) "([A-Z_]+)"', src))
    for group in re.findall(r'sketch_tool (?:not )?in \(([^)]*)\)', src):
        used |= set(re.findall(r'"([A-Z_]+)"', group))
    missing = used - {t for t, *_ in SKETCH_TOOLS} - NON_MENU_TOOLS
    assert not missing, f"add to omacad/ui/sketch_tools.py: {sorted(missing)}"
