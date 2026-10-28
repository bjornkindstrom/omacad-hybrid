"""State for the experiment is independent of the installed Omacad profile."""
import os
from pathlib import Path

STATE_DIR = Path(os.environ.get("OMACAD_HYBRID_STATE_DIR", Path(__file__).resolve().parent.parent / ".state"))
CONFIG_DIR = STATE_DIR / "config"
DATA_DIR = STATE_DIR / "data"
