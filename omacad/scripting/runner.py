"""Running a user script on a document (one undo step, rolled back on any error) and the headless test run that writes
`<script>.check.txt` for the AI that wrote it."""
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from omacad.scripting.api import ScriptContext
from omacad.scripting.loader import ScriptError, load_module, read_info, resolve_values


@dataclass
class RunResult:
    ok: bool
    name: str
    messages: List[str] = field(default_factory=list)
    error: str = ""              # short: what went wrong and where
    details: str = ""            # the full traceback for the AI
    line: Optional[int] = None   # line in the script the error came from
    seconds: float = 0.0
    values: Dict[str, Any] = field(default_factory=dict)


class ScriptRunError(Exception):
    def __init__(self, result: RunResult):
        super().__init__(result.error)
        self.result = result


def _describe(exc: BaseException, path: Path) -> (str, str, Optional[int]):
    """(short message, full traceback, script line) for an error raised while the script ran."""
    tb = traceback.extract_tb(exc.__traceback__)
    script = str(Path(path).resolve())
    frames = [f for f in tb if str(Path(f.filename).resolve()) == script]
    line = frames[-1].lineno if frames else getattr(exc, "lineno", None) if isinstance(exc, SyntaxError) else None
    kind = "" if isinstance(exc, ScriptError) else f"{type(exc).__name__}: "
    where = f"line {line}: " if line else ""
    code = f"\n    {frames[-1].line}" if frames and frames[-1].line else ""
    short = f"{where}{kind}{exc}{code}"
    return short, "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)), line


def run_script(doc, path, values: Optional[Dict[str, Any]] = None, log: Optional[Callable[[str], None]] = None,
               checking: bool = False, name: Optional[str] = None) -> RunResult:
    """Runs the script's run(ctx, params) on `doc` as one undo step "Script: <NAME>". Any error puts the document back
    exactly as it was and raises ScriptRunError (its .result says what and where)."""
    from omacad.model.document import undoable
    path = Path(path)
    info = read_info(path)
    result = RunResult(ok=False, name=info.name)
    if info.error:
        result.error = info.error
        result.line = _line_of(info.error)
        raise ScriptRunError(result)
    params = resolve_values(info.params, values)
    result.values = dict(params)
    ctx = ScriptContext(doc, log=log, checking=checking, name=(name or "").strip() or info.default_name)
    start = time.monotonic()

    def body(_doc):
        module = load_module(path)
        module.run(ctx, dict(params))
        ctx.finish()

    try:
        undoable(f"Script: {info.name}")(body)(doc)
    except Exception as e:
        result.error, result.details, result.line = _describe(e, path)
        result.messages = list(ctx.messages)
        result.seconds = time.monotonic() - start
        raise ScriptRunError(result) from e
    result.ok = True
    result.messages = list(ctx.messages)
    result.seconds = time.monotonic() - start
    return result


def preview_solid(path, values: Optional[Dict[str, Any]] = None, name: Optional[str] = None):
    """What the script would make with these values, as one solid for the viewport's preview (None: nothing). It runs on
    a private empty document on this thread, so the model is never touched. Raises ScriptRunError like run_script."""
    import manifold3d as m3d
    from omacad import busy
    from omacad.model.document import Document
    doc = Document()
    with busy.inline():
        run_script(doc, path, values, name=name)
    parts = [b.manifold for b in doc.bodies.values() if b.manifold is not None and not b.manifold.is_empty()]
    return m3d.Manifold.compose(parts) if parts else None


def _line_of(message: str) -> Optional[int]:
    import re
    m = re.search(r"line (\d+)", message)
    return int(m.group(1)) if m else None


def check_file_for(path) -> Path:
    path = Path(path)
    return path.with_name(path.stem + ".check.txt")


def check_report(path, values: Optional[Dict[str, Any]] = None) -> (bool, str):
    """Test-runs the script on an empty model with its default values. Returns (ok, report text)."""
    from omacad.model.document import Document
    path = Path(path)
    doc = Document()
    lines = [f"Omacad script check: {path.name}", f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    try:
        res = run_script(doc, path, values, checking=True)
    except ScriptRunError as e:
        r = e.result
        lines += ["RESULT: FAILED", f"Script name: {r.name}", f"Error: {r.error}"]
        if r.values:
            lines.append(f"Values used: {r.values}")
        if r.messages:
            lines += ["ctx.log output:"] + [f"  {m}" for m in r.messages]
        if r.details:
            lines += ["", "Traceback:", r.details.rstrip()]
        lines += ["", "Fix the script and save it again; Omacad tests it again automatically."]
        return False, "\n".join(lines) + "\n"
    bodies = list(doc.bodies.values())
    lines += ["RESULT: OK", f"Script name: {res.name}", f"Values used: {res.values}", f"Run time: {res.seconds:.2f} s",
              f"Timeline steps: {len(doc.timeline.features)} ({', '.join(f.name for f in doc.timeline.features)})",
              f"Bodies: {len(bodies)}"]
    objects = [o.name for o in doc.object_history.objects.values() if o.body_ids]
    lines.append(f"Objects (browser names): {', '.join(objects) if objects else '(none)'}")
    for b in bodies:
        bb = b.manifold.bounding_box()
        size = [round(float(bb[i + 3] - bb[i]), 3) for i in range(3)]
        lines.append(f"  {b.name}: volume {float(b.manifold.volume()):.3f} mm3, size X×Y×Z {size[0]} × {size[1]} × {size[2]} mm")
    if not bodies:
        lines.append("  warning: the script made no bodies (fine only if it is meant to make sketches).")
    if res.messages:
        lines += ["ctx.log output:"] + [f"  {m}" for m in res.messages]
    return True, "\n".join(lines) + "\n"


def check_script(path, out=None) -> int:
    """`omacad --check-script <file.py> [--out <file>]`: writes the report (default `<script>.check.txt`), exit 0 = OK."""
    try:
        ok, text = check_report(path)
    except Exception:                       # the checker itself must always leave a report
        ok, text = False, "Omacad script check\nRESULT: FAILED\nThe checker crashed:\n" + traceback.format_exc()
    target = Path(out) if out else check_file_for(path)
    try:
        target.write_text(text, encoding="utf-8")
    except OSError:
        sys.stdout.write(text)
    return 0 if ok else 1
