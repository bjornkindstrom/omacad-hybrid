"""User scripts (omacad.scripting): the stable API, one undo step per run, full rollback on errors, the headless test
run that writes <script>.check.txt, the AI prompt and the bundled gear generator, checked against exact geometry."""
import math
import re
import textwrap
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from omacad.model.document import Document
from omacad.scripting import folder as sfolder
from omacad.scripting import prompt as sprompt
from omacad.scripting.api import ScriptContext
from omacad.scripting.loader import ScriptError, parse_params, read_info, resolve_values
from omacad.scripting.runner import ScriptRunError, check_file_for, check_report, check_script, run_script

GEAR = sfolder.EXAMPLES / "gear_generator.py"


def _script(tmp_path, body, name="s.py"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def _gear_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("gear_example", GEAR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- the gear generator example ---------------------------------------------------------------------------------

def test_gear_outline_is_a_clean_involute_gear():
    g = _gear_module()
    for teeth, module in ((6, 1.0), (20, 2.0), (57, 0.8)):
        outline, pitch_r, tip_r, root_r = g.gear_outline(teeth, module, 20.0, 0.1)
        poly = Polygon(outline)
        assert poly.is_valid and poly.exterior.is_simple, teeth
        assert math.isclose(pitch_r, module * teeth / 2)
        radii = [math.hypot(x, y) for x, y in outline]
        assert math.isclose(max(radii), tip_r, rel_tol=1e-9) and math.isclose(tip_r, pitch_r + module)
        assert math.isclose(min(radii), root_r, rel_tol=1e-9)
        tips = sum(1 for r in radii if abs(r - tip_r) < 1e-9)
        assert tips == 2 * teeth                       # every tooth ends in two tip points


def test_gear_script_volume_is_outline_area_times_thickness_and_one_undo_step():
    g = _gear_module()
    doc = Document()
    res = run_script(doc, GEAR, {"teeth": 24, "module": 1.5, "thickness": 6, "bore": 0})
    assert res.ok and res.name == "Gear generator"
    outline, *_ = g.gear_outline(24, 1.5, 20.0, 0.1)
    (body,) = doc.bodies.values()
    assert body.manifold.volume() == pytest.approx(Polygon(outline).area * 6, rel=1e-6)   # float32 mesh
    assert body.name == "Gear"                                   # the Name field's default (OUTPUT_NAME)
    assert [o.name for o in doc.object_history.objects.values() if o.body_ids] == ["Gear"]
    assert [e[1] for e in doc.undo_stack if e[0] == "doc"] == ["Script: Gear generator"]
    assert doc.undo() == "Script: Gear generator"
    assert not doc.bodies and not doc.timeline.features
    doc.redo()
    assert len(doc.bodies) == 1


def test_gear_with_hub_and_bore():
    g = _gear_module()
    doc = Document()
    run_script(doc, GEAR, {"teeth": 16, "module": 2, "thickness": 5, "bore": 0, "hub": True, "hub_diameter": 12,
                           "hub_height": 4})
    outline, *_ = g.gear_outline(16, 2.0, 20.0, 0.1)
    (body,) = doc.bodies.values()
    hub = body.manifold.volume() - Polygon(outline).area * 5
    assert hub == pytest.approx(math.pi * 36 * 4, rel=2e-3)       # tessellated circle
    (lo, hi) = body.manifold.bounding_box()[2], body.manifold.bounding_box()[5]
    assert (lo, hi) == pytest.approx((0.0, 9.0))


def test_gear_refuses_a_bore_too_big_and_leaves_the_model_alone():
    doc = Document()
    doc.add_box(5, 5, 5)
    before = doc.snapshot()
    with pytest.raises(ScriptRunError) as e:
        run_script(doc, GEAR, {"teeth": 10, "module": 1, "bore": 9})
    assert "too big" in e.value.result.error and e.value.result.line
    assert doc.snapshot() == before and len(doc.undo_stack) == 1


# ---- running, rollback, errors ----------------------------------------------------------------------------------

def test_an_error_rolls_everything_back_and_names_the_line(tmp_path):
    p = _script(tmp_path, '''
        NAME = "Broken"
        def run(ctx, params):
            ctx.box(10, 10, 10)
            s = ctx.sketch("XY")
            s.circle((0, 0), 3)
            x = 1 / 0
    ''')
    doc = Document()
    with pytest.raises(ScriptRunError) as e:
        run_script(doc, p)
    r = e.value.result
    assert r.line == 7 and "ZeroDivisionError" in r.error and "x = 1 / 0" in r.error
    assert not doc.bodies and not doc.timeline.features and not doc.sketches and not doc.undo_stack


def test_api_misuse_gives_a_plain_message(tmp_path):
    p = _script(tmp_path, '''
        def run(ctx, params):
            s = ctx.sketch("XY")
            s.line((0, 0), (10, 0))
            ctx.extrude(s, 5)
    ''')
    with pytest.raises(ScriptRunError) as e:
        run_script(Document(), p)
    assert e.value.result.error.startswith("line 5: Sketch") and "no closed profile" in e.value.result.error


def test_read_info_without_running_and_its_errors(tmp_path):
    marker = tmp_path / "ran"
    p = _script(tmp_path, f'''
        open({str(marker)!r}, "w").write("x")
        NAME = "Hello"
        DESCRIPTION = "Says hello"
        PARAMS = [{{"name": "n", "type": "int", "default": 3, "min": 1, "max": 5}}]
        def run(ctx, params):
            pass
    ''')
    info = read_info(p)
    assert (info.name, info.description, [q.name for q in info.params], info.error) == ("Hello", "Says hello", ["n"], "")
    assert not marker.exists()
    assert "def run" in read_info(_script(tmp_path, "NAME = 'x'\n", "a.py")).error
    assert read_info(_script(tmp_path, "def run(ctx, params):\n  return (\n", "b.py")).error.startswith("Syntax error on line")
    assert "plain data" in read_info(_script(tmp_path, "PARAMS = [dict(name='a', default=1)]\ndef run(c,p): pass\n",
                                             "c.py")).error


@pytest.mark.parametrize("raw, words", [
    ({"name": "a"}, "list of dicts"),
    ([{"name": "a"}], "default"),
    ([{"name": "1a", "default": 1}], "identifier"),
    ([{"name": "a", "default": 1, "colour": 3}], "unknown keys"),
    ([{"name": "a", "type": "choice", "default": 1, "choices": [2, 3]}], "not one of"),
    ([{"name": "a", "default": 1}, {"name": "a", "default": 2}], "twice"),
    ([{"name": "a", "default": 1, "min": 5, "max": 2}], "min is larger"),
])
def test_bad_params_are_explained(raw, words):
    with pytest.raises(ScriptError, match=words):
        parse_params(raw)


def test_values_are_coerced_and_clamped():
    params = parse_params([{"name": "n", "type": "int", "default": 3, "min": 1, "max": 5},
                           {"name": "f", "default": 2.5, "min": 0.0},
                           {"name": "b", "type": "bool", "default": False},
                           {"name": "c", "type": "choice", "default": "x", "choices": ["x", "y"]}])
    assert resolve_values(params, {}) == {"n": 3, "f": 2.5, "b": False, "c": "x"}
    assert resolve_values(params, {"n": 9.6, "f": -4, "b": "yes", "c": "z"}) == {"n": 5, "f": 0.0, "b": True, "c": "x"}
    assert resolve_values(params, {"n": "junk"})["n"] == 3


# ---- the API ----------------------------------------------------------------------------------------------------

def test_primitives_combine_and_profiles_have_exact_volumes():
    doc = Document()
    ctx = ScriptContext(doc)
    a = ctx.box(20, 10, 5, at=(1, 2, 3))
    assert a.bounds == ((1, 2, 3), (21, 12, 8)) and a.volume == pytest.approx(1000)
    c = ctx.box(4, 4, 4, center=True, at=(50, 0, 0))
    assert c.bounds == ((48, -2, -2), (52, 2, 2))
    tool = ctx.box(5, 10, 5, at=(1, 2, 3))
    ctx.combine(a, tool, "cut")
    assert a.volume == pytest.approx(750) and not tool.exists
    s = ctx.sketch("XY", offset=20)
    s.circle((100, 0), 10).circle((100, 0), 4)                  # a washer: "outer" extrudes the ring, not the disc
    ring = ctx.extrude(s, 2)
    assert ring.bounds[0][2] == pytest.approx(20)
    expected = Polygon(s.profiles[0].outline, s.profiles[0].holes).area * 2
    assert ring.volume == pytest.approx(expected, rel=1e-6)
    assert ring.volume == pytest.approx(math.pi * (100 - 16) * 2, rel=3e-3)


def test_a_sketch_ignores_body_edges_in_its_plane():
    """A box with a side in the XZ plane would otherwise add its face as a second profile."""
    doc = Document()
    ctx = ScriptContext(doc)
    ctx.box(20, 10, 5)
    s = ctx.sketch("XZ")
    s.polyline([(0, 0), (10, 0), (12, 20), (0, 20)])
    assert len(s.profiles) == 1
    vase = ctx.revolve(s, axis="v")
    assert vase.volume == pytest.approx(math.pi * 20 / 3 * (100 + 120 + 144), rel=2e-3)
    assert [*vase.bounds[0], *vase.bounds[1]] == pytest.approx([-12, -12, 0, 12, 12, 20], abs=1e-6)
    doc.timeline.recompute(doc)                                 # still one profile after a rebuild
    assert len(doc.sketches[s.id].profiles) == 1


def test_fillet_shell_pattern_move_and_parameters():
    doc = Document()
    ctx = ScriptContext(doc)
    shell = ctx.box(30, 30, 20)
    ctx.shell(shell, 2)
    assert shell.volume == pytest.approx(30 * 30 * 20 - 26 * 26 * 18)
    plate = ctx.box(40, 40, 4, at=(0, 100, 0))
    s = ctx.sketch("XY", offset=4)
    s.circle((5, 105), 2)
    hole = ctx.extrude(s, -4, operation="cut")
    one = 6400 - plate.volume
    ctx.pattern([hole], kind="linear", count=3, spacing=10, axis="x")
    assert 6400 - plate.volume == pytest.approx(3 * one, rel=1e-6)
    cube = ctx.box(10, 10, 10, at=(-50, 0, 0))
    ctx.fillet(cube, 1, edges="top")
    r = 1.0
    assert cube.volume == pytest.approx(1000 - 4 * 10 * r * r * (1 - math.pi / 4), rel=2e-3)
    copy = ctx.move(cube, dz=15, copy=True)
    assert copy.id != cube.id and copy.bounds[0][2] == pytest.approx(15)
    ctx.parameter("width", 12, "from a script")
    assert [(p.name, p.expr) for p in doc.parameters] == [("width", "12")]


def test_every_call_in_the_guide_exists():
    """The guide is all the AI sees: each ctx./s./body method it names must be real."""
    from omacad.scripting.api import Body, Sketch
    text = sfolder.GUIDE.read_text(encoding="utf-8")
    ctx = ScriptContext(Document())
    for name in set(re.findall(r"`ctx\.(\w+)", text)):
        assert hasattr(ctx, name), name
    for name in set(re.findall(r"`s\.(\w+)", text)):
        assert hasattr(Sketch, name), name
    for name in ("name", "volume", "bounds", "edges", "exists", "rename"):
        assert hasattr(Body, name)
    assert Body(ctx, "body_x").id == "body_x"


def test_the_guide_example_passes_the_check(tmp_path):
    text = sfolder.GUIDE.read_text(encoding="utf-8")
    code = text.split("## Complete example", 1)[1].split("```python", 1)[1].split("```", 1)[0]
    p = _script(tmp_path, code, "flange.py")
    ok, report = check_report(p)
    assert ok, report
    assert "Flange: volume" in report and "60.0 × 60.0 × 6.0 mm" in report


# ---- the test run for the AI --------------------------------------------------------------------------------------

def test_check_script_writes_ok_and_failed_reports(tmp_path):
    good = tmp_path / "gear.py"
    good.write_bytes(GEAR.read_bytes())
    assert check_script(good) == 0
    report = check_file_for(good).read_text(encoding="utf-8")
    assert "RESULT: OK" in report and "Bodies: 1" in report and "Pitch diameter 40.00 mm" in report
    bad = _script(tmp_path, "def run(ctx, params):\n    ctx.cylinder(0, 5)\n", "bad.py")
    assert check_script(bad, tmp_path / "out.txt") == 1
    report = (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert "RESULT: FAILED" in report and "line 2: radius must be larger than 0" in report and "Traceback" in report


def test_prompt_has_the_wish_the_target_file_the_test_and_the_guide(tmp_path):
    agent = sprompt.build_prompt("En kugghjulsgenerator", tmp_path, "gear.py", for_agent=True)
    assert "En kugghjulsgenerator" in agent and str(tmp_path / "gear.py") in agent
    assert "gear.check.txt" in agent and "--check-script" in agent and "RESULT: OK" in agent
    assert agent.endswith(sfolder.GUIDE.read_text(encoding="utf-8"))
    chat = sprompt.build_prompt("x", tmp_path, "gear.py", for_agent=False)
    assert "ONE ```python code block" in chat and "--check-script" not in chat.split("---")[0]
    path = sprompt.write_agent_prompt("x", tmp_path, "gear.py")
    assert path.parent.name == ".omacad-ai" and path.read_text(encoding="utf-8").startswith("# Write an Omacad script")
    assert str(path) in sprompt.agent_instruction(path)


def test_check_command_runs_the_app_headless(tmp_path):
    import subprocess
    p = tmp_path / "gear.py"
    p.write_bytes(GEAR.read_bytes())
    out = tmp_path / "r.txt"
    done = subprocess.run(sprompt.check_command(p, out), capture_output=True, timeout=240)
    assert done.returncode == 0, done.stderr[-2000:]
    assert "RESULT: OK" in out.read_text(encoding="utf-8")


# ---- folder, examples, trust --------------------------------------------------------------------------------------

def test_default_folder_per_platform(tmp_path):
    assert sfolder.default_folder("win32", {"APPDATA": r"C:\Users\a\AppData\Roaming"}) == \
        Path(r"C:\Users\a\AppData\Roaming") / "Omacad" / "scripts"
    assert sfolder.default_folder("linux", {}, home=tmp_path) == tmp_path / ".config" / "omacad" / "scripts"
    assert sfolder.default_folder("linux", {"XDG_CONFIG_HOME": str(tmp_path)}) == tmp_path / "omacad" / "scripts"


def test_examples_are_copied_once_and_trust_follows_the_content(tmp_path):
    folder = sfolder.resolve_folder(str(tmp_path / "scripts"))
    assert sorted(p.name for p in folder.glob("*.py")) == ["box_in_a_row.py", "gear_generator.py", "jar_with_lid.py",
                                                            "star_brackets.py"]
    (folder / "gear_generator.py").unlink()
    sfolder.resolve_folder(str(folder))
    assert not (folder / "gear_generator.py").exists()            # a deleted example stays deleted
    p = _script(folder, "def run(ctx, params): pass\n", "mine.py")
    trusted = sfolder.trust({}, p)
    assert sfolder.is_trusted(trusted, p)
    p.write_text("def run(ctx, params):\n    pass\n", encoding="utf-8")
    assert not sfolder.is_trusted(trusted, p)
    assert sfolder.safe_file_name("En kugg-generator!") == "en_kugg_generator.py"
    assert sfolder.safe_file_name("3D text") == "script_3d_text.py"
