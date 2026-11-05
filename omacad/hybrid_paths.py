"""State for the experiment is independent of the installed Omacad profile."""
import os
import sys
from pathlib import Path
from typing import Mapping, Optional


def state_dir(env: Optional[Mapping[str, str]] = None, frozen: Optional[bool] = None, platform: Optional[str] = None,
              source_root: Optional[Path] = None, home: Optional[Path] = None) -> Path:
    """Where settings, autosaves and unsent requests live. A checkout keeps them in its own `.state`. The one-file exe
    must not: its code runs from a temporary folder that is deleted when the app closes."""
    env = os.environ if env is None else env
    if env.get("OMACAD_HYBRID_STATE_DIR"):
        return Path(env["OMACAD_HYBRID_STATE_DIR"])
    if not (getattr(sys, "frozen", False) if frozen is None else frozen):
        return (source_root or Path(__file__).resolve().parent.parent) / ".state"
    home = home or Path.home()
    if (platform or sys.platform) == "win32":
        return Path(env.get("APPDATA") or home / "AppData" / "Roaming") / "Omacad Hybrid"
    return Path(env.get("XDG_STATE_HOME") or home / ".local" / "state") / "omacad-hybrid"


STATE_DIR = state_dir()
CONFIG_DIR = STATE_DIR / "config"
DATA_DIR = STATE_DIR / "data"
