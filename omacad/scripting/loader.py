"""Reading user scripts: their NAME / DESCRIPTION / PARAMS without running them, loading the module, and turning the
values typed in the parameter panel into the dict `run(ctx, params)` gets."""
import ast
import importlib.util
import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PARAM_TYPES = ("float", "int", "bool", "choice", "str")
_counter = itertools.count(1)


class ScriptError(Exception):
    """A problem the script author can fix (bad PARAMS, a missing profile ...). The message says what to change."""


@dataclass
class Param:
    name: str
    type: str = "float"
    default: Any = 0.0
    label: str = ""
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    decimals: Optional[int] = None
    unit: str = ""
    choices: List[Any] = field(default_factory=list)
    help: str = ""

    @property
    def title(self) -> str:
        return self.label or self.name.replace("_", " ").capitalize()

    def coerce(self, value: Any) -> Any:
        """`value` as this parameter's type, kept inside min/max; the default when it can't be read."""
        try:
            if self.type == "bool":
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "yes", "on")
                return bool(value)
            if self.type == "str":
                return "" if value is None else str(value)
            if self.type == "choice":
                return value if value in self.choices else self.default
            v = int(round(float(value))) if self.type == "int" else float(value)
        except (TypeError, ValueError):
            return self.default
        if self.min is not None and v < self.min:
            v = type(v)(self.min)
        if self.max is not None and v > self.max:
            v = type(v)(self.max)
        return v


@dataclass
class ScriptInfo:
    path: Path
    name: str
    description: str = ""
    params: List[Param] = field(default_factory=list)
    error: str = ""          # why the script can't be run as it is ("" = fine)
    family: str = ""         # a built-in tool it is a version of ("jar", "star_brackets", "box_row"): its submenu
    output_name: str = ""    # default for the Name field (what the made things are called); "" = NAME

    @property
    def default_name(self) -> str:
        return self.output_name or self.name


def parse_params(raw: Any) -> List[Param]:
    """PARAMS (a list of dicts) as Param objects. Raises ScriptError saying exactly what is wrong."""
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise ScriptError("PARAMS must be a list of dicts, e.g. [{\"name\": \"length\", \"type\": \"float\", \"default\": 20}].")
    out, seen = [], set()
    allowed = set(Param.__dataclass_fields__)
    for i, d in enumerate(raw):
        if not isinstance(d, dict):
            raise ScriptError(f"PARAMS[{i}] must be a dict.")
        unknown = set(d) - allowed
        if unknown:
            raise ScriptError(f"PARAMS[{i}] has unknown keys {sorted(unknown)}; allowed: {sorted(allowed)}.")
        name = d.get("name")
        if not isinstance(name, str) or not name.isidentifier():
            raise ScriptError(f"PARAMS[{i}] needs a \"name\" that is a Python identifier (got {name!r}).")
        if name in seen:
            raise ScriptError(f"PARAMS has the name {name!r} twice.")
        seen.add(name)
        ptype = d.get("type", "float")
        if ptype not in PARAM_TYPES:
            raise ScriptError(f"PARAMS {name!r}: type must be one of {list(PARAM_TYPES)} (got {ptype!r}).")
        if "default" not in d:
            raise ScriptError(f"PARAMS {name!r} needs a \"default\" value.")
        p = Param(**d)
        if ptype == "choice":
            if not p.choices:
                raise ScriptError(f"PARAMS {name!r}: a choice needs a non-empty \"choices\" list.")
            if p.default not in p.choices:
                raise ScriptError(f"PARAMS {name!r}: default {p.default!r} is not one of the choices.")
        elif ptype in ("float", "int"):
            for key in ("default", "min", "max", "step"):
                v = getattr(p, key)
                if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
                    raise ScriptError(f"PARAMS {name!r}: {key} must be a number (got {v!r}).")
            if p.min is not None and p.max is not None and p.min > p.max:
                raise ScriptError(f"PARAMS {name!r}: min is larger than max.")
        out.append(p)
    return out


def _literal(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        for t in targets:
            if isinstance(t, ast.Name) and t.id == name:
                try:
                    return ast.literal_eval(value)
                except ValueError:
                    raise ScriptError(f"{name} must be plain data (numbers, strings, lists, dicts), not computed.")
    return None


def read_info(path) -> ScriptInfo:
    """NAME, DESCRIPTION and PARAMS read from the source without running it (safe for listing a folder)."""
    path = Path(path)
    info = ScriptInfo(path=path, name=path.stem.replace("_", " ").capitalize())
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        info.error = f"Syntax error on line {e.lineno}: {e.msg}"
        return info
    except (OSError, UnicodeDecodeError) as e:
        info.error = f"Can't read the file: {e}"
        return info
    try:
        name = _literal(tree, "NAME")
        if isinstance(name, str) and name.strip():
            info.name = name.strip()
        desc = _literal(tree, "DESCRIPTION")
        if isinstance(desc, str):
            info.description = desc.strip()
        family = _literal(tree, "FAMILY")
        if isinstance(family, str):
            info.family = family.strip()
        out_name = _literal(tree, "OUTPUT_NAME")
        if isinstance(out_name, str):
            info.output_name = out_name.strip()
        info.params = parse_params(_literal(tree, "PARAMS"))
    except ScriptError as e:
        info.error = str(e)
        return info
    if not any(isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body):
        info.error = "The script needs a top-level function `def run(ctx, params):`."
    return info


def load_module(path):
    """Runs the script file as a fresh module (top-level code only) and returns it."""
    path = Path(path)
    spec = importlib.util.spec_from_file_location(f"omacad_user_script_{next(_counter)}", str(path))
    if spec is None or spec.loader is None:
        raise ScriptError(f"Can't load {path.name}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "run", None)):
        raise ScriptError("The script needs a top-level function `def run(ctx, params):`.")
    return module


def resolve_values(params: List[Param], values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Defaults, overridden by `values` (what the panel or the last run had), each checked against its Param."""
    values = values or {}
    return {p.name: p.coerce(values[p.name]) if p.name in values else p.coerce(p.default) for p in params}
