"""Problem reports: collect what the AI needs (screenshot, the document, the log, your note) into one folder and hand it
to the default coding agent of Omarchy (`omarchy agent prompt`), which reproduces the problem, fixes the code and adds a test."""
import json
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

from omacad import __version__, applog

FEEDBACK_DIR = Path.home() / ".local" / "share" / "omacad" / "feedback"


def repo_root() -> Path:
    """Where the source code lives (the agent works there)."""
    here = Path(__file__).resolve().parents[1]
    return here if (here / "omacad.md").exists() else Path.home() / "Work" / "omacad"


PROMPT = """# Problem report from Omacad

The user pressed "Report problem" in the running app and wrote:

> {note}

Everything about the moment is in this folder ({folder}):
- `screenshot_marked.png` (only if the user drew on the picture): the window screenshot with red marks showing WHERE the problem is. Look at it first.
- `screenshot_window.png` and `screenshot_view.png`: what the user saw (LOOK AT THEM FIRST)
- `document.json`: the whole document state (`Exporter.document_to_dict`) incl. the sketch being edited and the replay marker
- `document.omacad`: the same as a project file (open with `Exporter.load_project`)
- `report.json`: version, platform, camera, selection, the undo history labels
- `log.txt`: the last status messages, printed output and errors

## What to do
1. Read `{root}/omacad.md` first (architecture, rules, past solutions).
2. Look at the screenshots, then reproduce the problem in a script from `document.omacad` (see the testing section of omacad.md).
3. Find the root cause. Fix it in the code in `{root}`: lean, clean, no workaround on top of a workaround.
4. Add a regression test in `{root}/tests/` (use the document from this report when it is small enough).
5. Run `.venv/bin/python tools/pick_tests.py` (your new test plus the 3-4 test files that cover the change; not the whole suite, CI runs that on push). If a test fails, fix it or revert.
6. Add an entry to the "Solutions log" in `omacad.md` and a line in `CHANGELOG.md` (bump the patch version in `omacad/__init__.py`).
7. Commit (do not push). Then tell the user in one or two sentences what was wrong. The running app restarts itself on the new commit (work saved and restored), so only commit when the tests are green.

If the report is unclear, say what you need instead of guessing. Never delete the user's data.
"""


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def build_bundle(doc, note: str, images: Optional[Dict[str, bytes]] = None, extra: Optional[dict] = None,
                 base_dir: Optional[Path] = None) -> Path:
    """Writes a report folder and returns its path. `images` maps file name -> PNG bytes."""
    from omacad.io.exporter import Exporter
    folder = Path(base_dir or FEEDBACK_DIR) / _stamp()
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in (images or {}).items():
        (folder / name).write_bytes(data)
    snapshot = Exporter.document_to_dict(doc)
    (folder / "document.json").write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
    try:
        Exporter.save_project(doc, str(folder / "document.omacad"))
    except Exception as e:                       # the report must work even when the document is in a bad state
        applog.log("ERROR", f"could not save document.omacad: {e}")
    report = {
        "note": note,
        "version": __version__,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "bodies": {bid: {"name": b.name, "volume": round(float(b.manifold.volume()), 4)} for bid, b in doc.bodies.items()},
        "features": [f"{f.feature_type}: {f.name}" for f in doc.timeline.features],
        "undo_history": [doc._entry_label(e) for e in doc.undo_stack[-30:]],
        "active_sketch": doc.active_sketch.sketch_id if doc.active_sketch else None,
        "selected_bodies": list(doc.selected_body_ids),
    }
    report.update(extra or {})
    (folder / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    (folder / "log.txt").write_text(applog.tail(300), encoding="utf-8")
    (folder / "PROMPT.md").write_text(PROMPT.format(note=note.strip() or "(no text)", folder=folder, root=repo_root()), encoding="utf-8")
    return folder


def available_agents() -> list:
    """Returns a list of available AI agents found on the system."""
    agents = [("omarchy", "Omarchy default agent")]
    known = [
        ("agy", "Antigravity (agy)"),
        ("claude", "Claude Code"),
        ("gemini", "Gemini CLI"),
        ("codex", "Codex CLI"),
        ("cursor-agent", "Cursor Agent"),
        ("opencode", "OpenCode"),
    ]
    for key, name in known:
        if shutil.which(key):
            agents.append((key, name))
    return agents


def agent_command(folder: Path, agent_choice: Optional[str] = None) -> Optional[list]:
    """The command that opens the selected coding agent on this report, or None if the launcher is missing."""
    if agent_choice is None:
        try:
            from omacad.ui.settings import get_settings
            agent_choice = get_settings().get("ai_agent", "omarchy")
        except Exception:
            agent_choice = "omarchy"

    text = f"Read {folder}/PROMPT.md and follow it. It is a problem report from the running Omacad app."

    # 1. Antigravity CLI (agy)
    if agent_choice == "agy" and shutil.which("agy"):
        term = shutil.which("xdg-terminal-exec") or shutil.which("foot") or shutil.which("kitty")
        if term:
            return [term, "--", "agy", "-i", text]
        return ["agy", "-i", text]

    # 2. Specific standalone agents
    if agent_choice != "omarchy" and shutil.which(agent_choice):
        term = shutil.which("xdg-terminal-exec") or shutil.which("foot") or shutil.which("kitty")
        cmd_args = [agent_choice]
        if agent_choice == "claude":
            cmd_args.extend(["--permission-mode", "auto", "--", text])
        elif agent_choice == "gemini":
            cmd_args.extend(["--yolo", "--prompt-interactive", text])
        elif agent_choice == "codex":
            cmd_args.extend(["--approve-for-me", "--", text])
        else:
            cmd_args.append(text)
        if term:
            return [term, "--"] + cmd_args
        return cmd_args

    # 3. Default: Omarchy agent prompt
    if shutil.which("omarchy") is not None:
        return ["omarchy", "agent", "prompt", text]

    # Fallback to agy if installed and omarchy wasn't found
    if shutil.which("agy"):
        term = shutil.which("xdg-terminal-exec") or shutil.which("foot") or shutil.which("kitty")
        if term:
            return [term, "--", "agy", "-i", text]
        return ["agy", "-i", text]

    return None


def launch_agent(folder: Path, agent_choice: Optional[str] = None) -> bool:
    cmd = agent_command(folder, agent_choice)
    if cmd is None:
        applog.log("feedback", "no AI agent launcher found; report saved only")
        return False
    subprocess.Popen(cmd, cwd=str(repo_root()), start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    applog.log("feedback", f"agent ({agent_choice or 'default'}) launched on {folder}")
    return True
