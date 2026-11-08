"""Script versions of Jar with Lid, Star Brackets and Box in a Row (all their geometry in the script): Star Brackets
and Box in a Row give exactly the built-in tools' solids, the jar's lid fits its thread; the Name field names what a
script makes; changed copies keep their family and never touch the original."""
import math
from pathlib import Path

import pytest

from omacad.model.document import Document
from omacad.scripting import folder as sfolder
from omacad.scripting import prompt as sprompt
from omacad.scripting.loader import read_info
from omacad.scripting.runner import check_report, run_script

EX = sfolder.EXAMPLES


def _solids(doc):
    return [(round(b.manifold.volume(), 1), [round(float(x), 3) for x in b.manifold.bounding_box()])
            for b in doc.bodies.values()]


@pytest.mark.parametrize("kw", [{}, dict(assembled=True, second_star=True, double_holes=True),
                                dict(outer_angle=50.0, inner_angle=122.0, post=True, reinforcement=False)])
def test_star_brackets_script_is_the_built_in_tool(kw):
    built = Document()
    built.add_star_brackets(**kw)
    script = Document()
    run_script(script, EX / "star_brackets.py", kw)
    for (va, ba), (vb, bb) in zip(_solids(built), _solids(script)):
        assert vb == pytest.approx(va, rel=1e-5) and bb == pytest.approx(ba, abs=1e-3)
    assert len(script.bodies) == len(built.bodies) == 3


@pytest.mark.parametrize("kw", [{}, dict(has_lid=True, honeycomb=True, outer_round=3),
                                dict(count=3, has_lid=True, outer_round=2, outer_round_kind="chamfer", inner_round=1,
                                     spacing=5)])
def test_box_in_a_row_script_is_the_built_in_tool(kw):
    built = Document()
    built.add_box_row(**kw)
    script = Document()
    run_script(script, EX / "box_in_a_row.py", kw)
    a, b = _solids(built), _solids(script)
    assert len(a) == len(b)
    for (va, ba), (vb, bb) in zip(a, b):
        assert vb == pytest.approx(va, rel=1e-5) and bb == pytest.approx(ba, abs=1e-3)
    if kw.get("has_lid"):
        lids = [bid for bid, body in script.bodies.items() if body.name.endswith("lid")]
        assert lids and set(lids) <= script.lids


@pytest.mark.parametrize("profile", ["trapezoidal_45", "round", "iso_60"])
def test_jar_script_lid_fits_and_the_model_stays_light(profile):
    doc = Document()
    run_script(doc, EX / "jar_with_lid.py", {"lid_beside": False, "profile": profile})
    jar, lid = [b.manifold for b in doc.bodies.values()]
    assert (jar ^ lid).volume() == pytest.approx(0.0, abs=1e-3)          # -0.2 mm tolerance: no clash anywhere
    assert jar.genus() == 0 and lid.genus() == 0
    assert jar.num_tri() < 20000 and lid.num_tri() < 20000
    bb = jar.bounding_box()
    assert [bb[2], bb[5]] == pytest.approx([0.0, 50.0]) and bb[3] - bb[0] == pytest.approx(40.0, abs=1e-3)


def test_jar_script_is_close_to_the_built_in_jar():
    from omacad.model.jar import JarSpec
    built = Document()
    ids = built.add_jar(JarSpec())
    script = Document()
    run_script(script, EX / "jar_with_lid.py")
    jar_s, lid_s = script.bodies.values()
    assert jar_s.manifold.volume() == pytest.approx(built.bodies[ids["jar"]].manifold.volume(), rel=0.03)
    assert lid_s.manifold.volume() == pytest.approx(built.bodies[ids["lid"]].manifold.volume(), rel=0.06)
    assert list(lid_s.manifold.bounding_box()) == pytest.approx(list(built.bodies[ids["lid"]].manifold.bounding_box()),
                                                                abs=1e-3)
    assert [jar_s.name, lid_s.name] == ["Jar", "Jar lid"]


def test_jar_script_refuses_what_the_built_in_refuses():
    ok, report = check_report(EX / "jar_with_lid.py", {"neck_diameter": 39.0})
    assert not ok and "lid's wall outside the thread" in report


def test_the_name_field_names_what_a_script_makes():
    doc = Document()
    run_script(doc, EX / "box_in_a_row.py", {"count": 2, "has_lid": True}, name="Skruvlåda")
    names = [o.name for o in doc.object_history.objects.values() if o.body_ids]
    assert names == ["Skruvlåda 1", "Skruvlåda 1 lid", "Skruvlåda 2", "Skruvlåda 2 lid"]
    assert [g["name"] for g in doc.object_groups] == ["Skruvlåda"]
    doc.undo()
    assert not doc.bodies and not doc.object_groups


def test_unnamed_objects_get_the_name_numbered(tmp_path):
    p = tmp_path / "two.py"
    p.write_text("def run(ctx, params):\n    ctx.box(5, 5, 5)\n    ctx.cylinder(2, 4, at=(20, 0, 0))\n"
                 "    s = ctx.sketch('XY'); s.circle((50, 0), 3); ctx.extrude(s, 2)\n", encoding="utf-8")
    doc = Document()
    run_script(doc, p, name="Del")
    assert sorted(o.name for o in doc.object_history.objects.values() if o.body_ids) == ["Del", "Del 2", "Del 3"]
    doc2 = Document()
    run_script(doc2, p)                                           # no Name given: the file's NAME (from its name)
    assert sorted(o.name for o in doc2.object_history.objects.values() if o.body_ids)[0] == "Two"


def test_family_scripts_and_their_copies(tmp_path):
    folder = sfolder.resolve_folder(str(tmp_path / "s"))
    assert [i.name for i in sfolder.family_scripts(folder, "jar")] == ["Jar with Lid (script)"]
    original = (folder / "jar_with_lid.py").read_text(encoding="utf-8")
    copy = sprompt.make_copy(folder / "jar_with_lid.py", folder, "jar_tall.py", "Make it taller please")
    info = read_info(copy)
    assert (info.family, info.name) == ("jar", "Jar with Lid – Make it taller please")
    assert (folder / "jar_with_lid.py").read_text(encoding="utf-8") == original
    assert [i.path.name for i in sfolder.family_scripts(folder, "jar")] == ["jar_with_lid.py", "jar_tall.py"]
    for name, family in (("star_brackets.py", "star_brackets"), ("box_in_a_row.py", "box_row")):
        assert read_info(folder / name).family == family and sfolder.is_bundled(folder / name)


def test_modify_prompt_protects_the_original(tmp_path):
    base, target = EX / "jar_with_lid.py", tmp_path / "jar_tall.py"
    agent = sprompt.build_modify_prompt("Högre burk", tmp_path, base, target, for_agent=True)
    assert "Högre burk" in agent and f"The original is `{base}`. NEVER change it." in agent
    assert str(target) in agent and "jar_tall.check.txt" in agent and "Keep the script's `FAMILY`" in agent
    chat = sprompt.build_modify_prompt("Högre burk", tmp_path, base, target, for_agent=False)
    assert "def thread_solid(" in chat and "as `jar_tall.py`" in chat


def test_new_examples_reach_a_folder_from_the_first_version(tmp_path):
    folder = tmp_path / "old"
    folder.mkdir()
    (folder / sfolder.EXAMPLES_MARKER).write_text("The Omacad examples were copied here once; delete this file to "
                                                  "get them back.\n", encoding="utf-8")
    sfolder.install_examples(folder)
    assert sorted(p.name for p in folder.glob("*.py")) == ["box_in_a_row.py", "jar_with_lid.py", "star_brackets.py"]


def test_preview_never_touches_the_model():
    from omacad.scripting.runner import ScriptRunError, preview_solid
    solid = preview_solid(EX / "gear_generator.py", {})
    assert solid is not None and solid.volume() > 0
    star = preview_solid(EX / "star_brackets.py", {"assembled": True})
    built = Document()
    built.add_star_brackets(assembled=True)
    assert star.volume() == pytest.approx(sum(b.manifold.volume() for b in built.bodies.values()), rel=1e-4)
    with pytest.raises(ScriptRunError):
        preview_solid(EX / "jar_with_lid.py", {"neck_diameter": 39.0})
