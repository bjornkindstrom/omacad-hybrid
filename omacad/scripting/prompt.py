"""The instructions sent to an AI when the user asks for a new script: the user's wish, where to save the file, how
Omacad tests it, and the whole scripting guide."""
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence

from omacad.scripting.folder import GUIDE
from omacad.scripting.runner import check_file_for


def check_command(script, out=None) -> List[str]:
    """The command that test-runs a script without opening a window (the exe itself when frozen)."""
    args = ["--check-script", str(script)] + (["--out", str(out)] if out else [])
    if getattr(sys, "frozen", False):
        return [sys.executable] + args
    app = Path(__file__).resolve().parent.parent.parent / "app.py"
    return [sys.executable, str(app)] + args


def _shell_line(cmd: List[str]) -> str:
    if sys.platform == "win32":
        return subprocess.list2cmdline(cmd)
    import shlex
    return " ".join(shlex.quote(c) for c in cmd)


def guide_text() -> str:
    return GUIDE.read_text(encoding="utf-8")


def _pictures(images: Sequence[Path], for_agent: bool) -> List[str]:
    """The prompt section about the pictures the user added to explain what they mean."""
    if not images:
        return []
    if for_agent:
        lines = ["## Pictures from the user", "",
                 "The user added pictures to show what they mean. Open and look at every one before you start:", ""]
        lines += [f"- `{Path(p)}`" for p in images]
    else:
        n = len(images)
        lines = ["## Pictures from the user", "",
                 f"The user attaches {n} picture{'s' if n > 1 else ''} to this message to show what they mean. Look at "
                 f"{'them' if n > 1 else 'it'} before you answer (if none arrived, ask for {'them' if n > 1 else 'it'})."]
    return lines + [""]


def build_prompt(wish: str, folder: Path, file_name: str, for_agent: bool, images: Sequence[Path] = ()) -> str:
    """for_agent: the AI can write files (a coding agent) - else it is a chat that answers with the code."""
    folder = Path(folder)
    target = folder / file_name
    check = check_file_for(target)
    wish = wish.strip() or "(The user did not describe it: ask what the script should make.)"
    head = [
        "# Write an Omacad script",
        "",
        "Omacad is a parametric 3D CAD program. Write a Python script for it, following the guide below exactly.",
        "Reply in the same language as the user's request.",
        "",
        "## What the user wants",
        "",
        wish,
        "",
        *_pictures(images, for_agent),
        "## Where it goes and how it is tested",
        "",
    ]
    if for_agent:
        head += [
            f"1. Save the script as `{target}` (choose a better short file name in the same folder if that one is taken"
            " or does not fit; lower case, underscores, `.py`). Write only that file; do not touch other files there.",
            "2. Omacad is open and watches this folder: a few seconds after you save, it test-runs the script on an"
            f" empty model with the default PARAMS values and writes `{check.name}` next to it"
            " (`<script name>.check.txt`). Wait for that file to appear or change (poll every 2 seconds, up to 60 s).",
            "3. If it says `RESULT: FAILED`, read the error and the line number, fix the script, save again and wait for"
            " the new report. Repeat until it says `RESULT: OK`, and check that the bodies, sizes and volumes in it"
            " are what the user asked for.",
            "4. If no report appears within 60 s (Omacad closed), test it yourself with:",
            "",
            "   " + _shell_line(check_command(target)),
            "",
            "5. Finish with a short summary for the user: what the script makes, its parameters, and that it is in"
            " Omacad under Scripts (Shift+S).",
        ]
    else:
        head += [
            "Answer with the complete script in ONE ```python code block, then a short explanation of its parameters.",
            f"The user saves it in the Omacad scripts folder `{folder}` as a `.py` file (suggest a short file name,"
            f" e.g. `{file_name}`). Omacad then test-runs it automatically and shows the result; if it fails, the"
            " user pastes the error back to you - then send the whole corrected script again.",
        ]
    head += ["", "---", ""]
    return "\n".join(head) + guide_text()


def make_copy(base: Path, folder: Path, file_name: str, wish: str) -> Path:
    """Copies the script to modify into `file_name` (the original is never changed) and marks its NAME as a copy, so
    it is told apart in the menus until the AI gives it a better name."""
    import re
    import shutil
    base, folder = Path(base), Path(folder)
    target = folder / file_name
    text = base.read_text(encoding="utf-8")
    label = " ".join(wish.split()[:5]).strip(" .,") or "copy"
    text, n = re.subn(r'^NAME\s*=\s*(["\'])(.*?)\1', lambda m: f'NAME = {(m.group(2).replace(" (script)", "") + " – " + label)!r}',
                      text, count=1, flags=re.M)
    target.write_text(text, encoding="utf-8")
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        img = base.with_suffix(ext)
        if img.exists():
            tgt_img = target.with_suffix(ext)
            if not tgt_img.exists():
                shutil.copyfile(img, tgt_img)
            break
    return target


def build_modify_prompt(wish: str, folder: Path, base: Path, target: Path, for_agent: bool,
                        images: Sequence[Path] = ()) -> str:
    """Instructions to change a copy of an existing script (a built-in tool's script or one of the user's)."""
    folder, base, target = Path(folder), Path(base), Path(target)
    wish = wish.strip() or "(The user did not describe the change: ask what to change.)"
    head = [
        "# Change an Omacad script",
        "",
        "Omacad is a parametric 3D CAD program. The user wants a changed version of one of its scripts.",
        "Reply in the same language as the user's request.",
        "",
        "## The change the user wants",
        "",
        wish,
        "",
        *_pictures(images, for_agent),
        "## Rules",
        "",
        f"- The original is `{base}`. NEVER change it.",
        "- Keep the script's `FAMILY` line as it is, so the copy stays in the same menu.",
        "- Give the copy a `NAME` that says what is different (short), and update `DESCRIPTION`.",
        "- Change only what the request needs; keep everything else working as before. Add a PARAMS entry for any"
        " new value the user may want to set.",
        "",
    ]
    if for_agent:
        check = check_file_for(target)
        head += [
            "## Where and how it is tested",
            "",
            f"1. The copy to change is `{target}` (already made from the original). Edit only that file.",
            "2. Omacad is open and watches the folder: a few seconds after you save, it test-runs the script on an empty"
            f" model with the default PARAMS values and writes `{check.name}` next to it. Wait for that file to"
            " appear or change (poll every 2 seconds, up to 60 s).",
            "3. If it says `RESULT: FAILED`, fix the error at the given line and save again, until `RESULT: OK`;"
            " check that the bodies, sizes and volumes in it fit the request.",
            "4. If no report appears within 60 s (Omacad closed), test it yourself with:",
            "",
            "   " + _shell_line(check_command(target)),
            "",
            "5. Finish with a short summary for the user of what changed, and that the copy is in the tool's menu and"
            " under Scripts (Shift+S).",
        ]
    else:
        head += [
            "## How to answer",
            "",
            "Answer with the complete changed script in ONE ```python code block, then a short summary of what changed.",
            f"The user saves it in the Omacad scripts folder `{folder}` as `{target.name}`. Omacad then test-runs it"
            " automatically; if it fails, the user pastes the error back to you - then send the whole corrected script"
            " again.",
            "",
            "## The current script",
            "",
            "```python",
            base.read_text(encoding="utf-8").rstrip(),
            "```",
        ]
    head += ["", "---", ""]
    return "\n".join(head) + guide_text()


def write_agent_prompt(wish: str, folder: Path, file_name: str, text: Optional[str] = None,
                       images: Sequence[Path] = ()) -> Path:
    """Writes the prompt into `<folder>/.omacad-ai/` (hidden from the script list) and returns its path."""
    out_dir = Path(folder) / ".omacad-ai"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"PROMPT-{time.strftime('%Y%m%d-%H%M%S')}.md"
    path.write_text(text if text is not None else build_prompt(wish, folder, file_name, for_agent=True, images=images),
                    encoding="utf-8")
    return path


def agent_instruction(prompt_path: Path) -> str:
    return f"Read {prompt_path} and follow it. It asks you to write or change a script for the Omacad CAD app."


def error_for_ai(script_name: str, report: str) -> str:
    """What "Copy error for AI" puts on the clipboard."""
    return (f"Omacad test-ran my script `{script_name}` and it failed. Here is Omacad's report; please send the whole "
            f"corrected script again.\n\n```\n{report.strip()}\n```\n")
