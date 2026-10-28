"""Pick the 3-4 test files that matter for the current change and run them.

    .venv/bin/python tools/pick_tests.py            # uncommitted changes (incl. new files)
    .venv/bin/python tools/pick_tests.py HEAD       # the changes of one commit
    .venv/bin/python tools/pick_tests.py --list     # only print the choice

Changed test files always run. Other tests are ranked by what they share with the change:
the changed functions/classes named in the test (strongest), words of the changed module in
the test's file name, and importing the changed module. The full suite runs on push (CI)."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
MAX_FILES = 4


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def changed(commit=None):
    revs = [f"{commit}~1", commit] if commit else ["HEAD"]
    files = set(git("diff", "--name-only", *revs).split())
    if not commit:
        files |= set(git("ls-files", "--others", "--exclude-standard", "omacad", "tests").split())
    files = {f for f in files if f.endswith(".py") and (ROOT / f).exists()}
    names = set()
    app = False   # only names from the app's own code count (not tools/, video/, tests/)
    for line in git("diff", "-U0", *revs).splitlines():
        if line.startswith("diff --git"):
            app = " a/omacad/" in line
        elif not app:
            continue
        elif line.startswith("@@"):
            names.update(re.findall(r"(?:def|class) (\w+)", line))
        elif line.startswith("+") and not line.startswith("+++"):
            names.update(re.findall(r"^\+\s*(?:def|class) (\w+)", line))
    for f in files:
        if not commit and f.startswith("omacad/") and git("ls-files", f) == "":   # a new module: all its functions are new
            names.update(re.findall(r"^\s*(?:def|class) (\w+)", (ROOT / f).read_text(encoding="utf-8"), re.M))
    names = {n for n in names if not n.startswith("test") and n not in ("__init__", "setUp")}
    return files, names


def words(path: str):
    return {w for w in re.split(r"[_\W]+", Path(path).stem.lower()) if len(w) > 2 and w not in ("test", "tests", "mixin")}


def pick(commit=None):
    files, names = changed(commit)
    picked = sorted(f for f in files if f.startswith("tests/test_"))
    modules = [f for f in files if f.startswith("omacad/")]
    if not modules and not names:
        return picked[:MAX_FILES]
    scores = {}
    for test in sorted(TESTS.glob("test_*.py")):
        rel = f"tests/{test.name}"
        if rel in picked:
            continue
        src = test.read_text(encoding="utf-8")
        score = 0.0
        score += 5 * sum(1 for n in names if re.search(rf"\b{re.escape(n)}\b", src))
        for mod in modules:
            dotted = mod[:-3].replace("/", ".")
            score += 3 * len(words(mod) & words(rel))
            if dotted in src or Path(mod).stem in src:
                score += 1
        if score > 0:
            scores[rel] = score
    ranked = sorted(scores, key=lambda r: (-scores[r], (ROOT / r).stat().st_size))
    return (picked + ranked)[:max(MAX_FILES, len(picked))]


def main(argv):
    only_list = "--list" in argv
    args = [a for a in argv if a != "--list"]
    chosen = pick(args[0] if args else None)
    if not chosen:
        print("No changed Python files: nothing to test.")
        return 0
    print("Tests:", " ".join(chosen))
    if only_list:
        return 0
    try:
        import xdist  # noqa: F401
        spread = ["-n", "auto", "--dist", "loadfile"] if len(chosen) > 2 else []
    except ImportError:
        spread = []
    return subprocess.run([sys.executable, "-m", "pytest", *chosen, "-q", "--tb=short", "-p", "no:cacheprovider", *spread],
                          cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
