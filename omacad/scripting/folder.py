"""Where the user's scripts live, the bundled example, and which script versions the user has said they trust."""
import hashlib
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from omacad.scripting.loader import ScriptInfo, read_info

HERE = Path(__file__).resolve().parent
GUIDE = HERE / "GUIDE.md"
EXAMPLES = HERE / "examples"
EXAMPLES_MARKER = ".omacad-examples"      # once written, a deleted example is not put back


def default_folder(platform: Optional[str] = None, env: Optional[Mapping[str, str]] = None,
                   home: Optional[Path] = None) -> Path:
    """Linux: ~/.config/omacad/scripts (XDG_CONFIG_HOME honoured); Windows: %APPDATA%\\Omacad\\scripts."""
    env = os.environ if env is None else env
    home = home or Path.home()
    if (platform or sys.platform) == "win32":
        return Path(env.get("APPDATA") or home / "AppData" / "Roaming") / "Omacad" / "scripts"
    return Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "omacad" / "scripts"


def resolve_folder(setting: Optional[str]) -> Path:
    """The configured folder ("" or None = the default for this machine), created if missing, with the example."""
    folder = Path(setting).expanduser() if setting else default_folder()
    folder.mkdir(parents=True, exist_ok=True)
    install_examples(folder)
    return folder


def install_examples(folder: Path) -> List[Path]:
    """Copies each bundled example into the folder once (never over a file the user has). The marker lists what was
    copied, so a deleted example stays deleted and a new one in a later version still arrives."""
    marker = folder / EXAMPLES_MARKER
    done = set()
    if marker.exists():
        lines = marker.read_text(encoding="utf-8").splitlines()
        done = {ln.strip() for ln in lines if ln.strip().endswith(".py")}
        if not done:                     # the first version's marker (only the gear generator existed then)
            done = {"gear_generator.py"}
    made = []
    for src in sorted(EXAMPLES.glob("*.py")):
        if src.name in done:
            continue
        dst = folder / src.name
        if not dst.exists():
            shutil.copyfile(src, dst)
            made.append(dst)
        done.add(src.name)
    text = ("# Omacad examples already copied here (delete a line to get that one back):\n"
            + "".join(f"{n}\n" for n in sorted(done)))
    if not marker.exists() or marker.read_text(encoding="utf-8") != text:
        marker.write_text(text, encoding="utf-8")
    return made


def family_scripts(folder: Path, family: str) -> List[ScriptInfo]:
    """Scripts that are versions of a built-in tool (FAMILY = "jar" ...): the bundled one first, then by name."""
    bundled = {p.name for p in EXAMPLES.glob("*.py")}
    found = [i for i in list_scripts(folder) if i.family == family]
    return sorted(found, key=lambda i: (i.path.name not in bundled, i.name.lower()))


def is_bundled(path) -> bool:
    return (EXAMPLES / Path(path).name).exists()


def list_scripts(folder: Path) -> List[ScriptInfo]:
    return [read_info(p) for p in sorted(Path(folder).glob("*.py"), key=lambda p: p.name.lower())
            if not p.name.startswith(("_", "."))]


def file_hash(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def is_trusted(trusted: Dict[str, str], path) -> bool:
    """True when the user allowed exactly this content of this file before."""
    try:
        return trusted.get(str(Path(path).resolve())) == file_hash(path)
    except OSError:
        return False


def trust(trusted: Dict[str, str], path) -> Dict[str, str]:
    out = dict(trusted)
    out[str(Path(path).resolve())] = file_hash(path)
    return out


def safe_file_name(text: str) -> str:
    """A script file name from free text: lower case, letters/digits/underscores, ends in .py."""
    import re
    stem = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "my_script"
    if stem[0].isdigit():
        stem = "script_" + stem
    return stem + ".py"


def is_own(path) -> bool:
    """A script the user (or their AI) made, not one Omacad copied in: only these can be deleted."""
    return not is_bundled(path)


def rename_script(path, new_name: str) -> None:
    """Sets the script's NAME (what the menus show); the file name stays. A script without NAME gets one after its
    docstring. Raises ValueError for an empty name."""
    import ast
    import re
    new_name = " ".join(str(new_name).split())
    if not new_name:
        raise ValueError("The name can't be empty.")
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    line = f"NAME = {new_name!r}"
    out, n = re.subn(r'^NAME\s*=\s*(["\']).*?\1[ \t]*$', lambda _m: line, text, count=1, flags=re.M)
    if not n:
        lines = text.splitlines(keepends=True)
        at = 0
        try:
            body = ast.parse(text).body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                at = body[0].end_lineno
        except SyntaxError:
            pass
        lines.insert(at, line + "\n")
        out = "".join(lines)
    path.write_text(out, encoding="utf-8")


def delete_script(path) -> bool:
    """Moves one of the user's own scripts (and its test report) to the trash, or deletes it where there is none.
    Refuses Omacad's bundled scripts. Returns True when the script is gone."""
    from omacad.scripting.runner import check_file_for
    path = Path(path)
    if not is_own(path):
        raise ValueError("Omacad's own scripts can't be deleted.")
    for p in (path, check_file_for(path)):
        if p.exists() and not _to_trash(p):
            p.unlink()
    return not path.exists()


def _to_trash(path: Path) -> bool:
    try:
        from PySide6.QtCore import QFile
        ok = QFile.moveToTrash(str(path))
        return bool(ok[0] if isinstance(ok, tuple) else ok)
    except Exception:
        return False


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def save_images(images, folder, stem: str) -> List[Path]:
    """Puts the pictures for the AI in `<folder>/.omacad-ai/images/<stem>-<time>/` (file paths are copied, QImages
    saved as PNG) and returns their paths, in order."""
    import time
    if not images:
        return []
    out = Path(folder) / ".omacad-ai" / "images" / f"{Path(stem).stem}-{time.strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, img in enumerate(images, 1):
        if isinstance(img, (str, Path)):
            src = Path(img)
            dst = out / f"{i}{src.suffix.lower() or '.png'}"
            shutil.copyfile(src, dst)
        else:
            dst = out / f"{i}.png"
            if not img.save(str(dst), "PNG"):
                continue
        saved.append(dst)
    return saved
