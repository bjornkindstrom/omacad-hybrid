"""
Omacad - Safe arithmetic expressions for numeric fields.

Accepts things like  10-1,  2x(3+5),  2*3.5,  (12+8)/4,  sqrt(16)+2,  50%  is not supported.
`x`, `X` and `×` mean multiplication, `÷` division, `,` a decimal comma and `^` a power.
Only numbers, + - * / ** and a few named functions are allowed - nothing is ever exec'd.
"""

import ast
import math
import operator
import re

_BIN = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "min": min, "max": max, "round": round,
          "sin": lambda a: math.sin(math.radians(a)), "cos": lambda a: math.cos(math.radians(a)),
          "tan": lambda a: math.tan(math.radians(a))}
_NAMES = {"pi": math.pi, "e": math.e}

ALLOWED_CHARS = set("0123456789.,;+-*/()^%xX×÷ ")

# Names usable in formulas: the document's parameters (set by the Document whenever they change)
_VARIABLES = {}
RESERVED = set(_FUNCS) | set(_NAMES) | {"x", "X"}  # cannot be used as parameter names

_TOKEN = re.compile(r"\s*(\d+(?:[.,]\d+)?|[^\W\d]\w*|\*\*|.)", re.UNICODE)


def set_variables(values) -> None:
    global _VARIABLES
    _VARIABLES = dict(values)


def get_variables() -> dict:
    return dict(_VARIABLES)


def is_valid_name(name: str) -> bool:
    return name.isidentifier() and name not in RESERVED


def normalize(text: str, variables=None) -> str:
    """Tokenises so that a standalone x/X/× means multiply (2x(3+5), 3x4) without touching names
    such as width, x1 or box_x that the user defined."""
    names = _VARIABLES if variables is None else variables
    out = []
    for tok in _TOKEN.findall(text.strip()):
        if tok in ("x", "X", "×") and tok not in names:
            out.append("*")
        elif tok == "÷":
            out.append("/")
        elif tok == "^":
            out.append("**")
        elif tok == ";":
            out.append(",")  # separates function arguments
        elif re.fullmatch(r"\d+,\d+", tok):
            out.append(tok.replace(",", "."))
        elif tok == ",":
            out.append(".")  # decimal comma written without digits around it
        elif re.fullmatch(r"[xX]\d+", tok) and tok not in names:
            out.append("*" + tok[1:])  # 3x4
        else:
            out.append(tok)
    return " ".join(out)


def is_plain_number(text: str) -> bool:
    try:
        float(text.strip().replace(",", "."))
        return True
    except ValueError:
        return False


def evaluate(text: str, variables=None) -> float:
    """Value of the expression. Raises ValueError if it is empty, malformed or not allowed."""
    names = _VARIABLES if variables is None else variables
    t = normalize(text, names)
    if not t:
        raise ValueError("empty")
    try:
        tree = ast.parse(t, mode="eval")
    except SyntaxError as e:
        raise ValueError(str(e)) from None
    value = _eval(tree.body, names)
    if not math.isfinite(value):
        raise ValueError("not finite")
    return float(value)


def names_in(text: str) -> set:
    """Identifiers used by an expression (for dependency checks)."""
    try:
        tree = ast.parse(normalize(text, {}), mode="eval")
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in _NAMES and n.id not in _FUNCS}


def _eval(node, names) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        a, b = _eval(node.left, names), _eval(node.right, names)
        if isinstance(node.op, ast.Pow) and abs(b) > 64:
            raise ValueError("exponent too large")
        try:
            value = _BIN[type(node.op)](a, b)
            if isinstance(value, complex):          # (-8)^(1/3)
                raise ValueError("not a real number")
            return float(value)                     # a huge int ((64^64)^64) overflows here, not later
        except (ZeroDivisionError, OverflowError):
            raise ValueError("math error") from None
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, names))
    if isinstance(node, ast.Name):
        if node.id in names:
            return names[node.id]
        if node.id in _NAMES:
            return _NAMES[node.id]
        raise ValueError(f"unknown name '{node.id}'")
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS
            and not node.keywords):
        try:
            return _FUNCS[node.func.id](*[_eval(a, names) for a in node.args])
        except (ValueError, TypeError, OverflowError):
            raise ValueError("math error") from None
    raise ValueError("not allowed")


def is_expression_text(text: str) -> bool:
    """Cheap filter used while typing: only characters an expression can contain."""
    t = text.strip()
    return all(c.isalnum() or c in ALLOWED_CHARS or c == "_" for c in t)
