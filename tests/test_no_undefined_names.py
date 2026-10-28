"""Modularizing a big file once left mixins without their imports (NameError at
runtime). Every name loaded in a module must be bound somewhere in that module."""
import ast
import builtins
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "omacad"


def _bound_names(tree):
    names = set(dir(builtins)) | {"__file__", "__name__"}
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            names.update((a.asname or a.name).split(".")[0] for a in n.names)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, ast.arg):
            names.add(n.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            names.update(n.names)
        elif isinstance(n, ast.MatchAs) and n.name:
            names.add(n.name)
    return names


def test_no_undefined_names():
    problems = []
    for path in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text())
        bound = _bound_names(tree)
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in bound:
                problems.append(f"{path.relative_to(ROOT)}:{n.lineno} {n.id}")
    assert not problems, "\n".join(problems)
