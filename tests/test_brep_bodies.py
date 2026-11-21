"""Experimental B-rep bodies (step 1): plain Box/Cylinder as exact OpenCascade shapes behind the "brep_bodies"
setting; off = unchanged mesh bodies; any mesh write drops the shape."""
import math

import numpy as np
import pytest

from omacad.model import brep
from omacad.model.document import Document

pytestmark = pytest.mark.skipif(not brep.available(), reason="cadquery-ocp not installed")


@pytest.fixture
def brep_on():
    brep.set_enabled(True)
    yield
    brep.set_enabled(False)


def only_body(doc):
    (body,) = doc.bodies.values()
    return body


def bbox(body):
    b = body.manifold.bounding_box()
    return np.array(b[:3]), np.array(b[3:])


def test_setting_off_keeps_plain_mesh_bodies():
    doc = Document()
    doc.add_box(30, 20, 10)
    assert only_body(doc).brep is None


@pytest.mark.parametrize("center, lo", [(False, (0, 0, 0)), (True, (-15, -10, -5)), ("bottom_center", (-15, -10, 0))])
def test_box_is_exact_brep_placed_like_the_mesh(brep_on, center, lo):
    doc = Document()
    doc.add_box(30, 20, 10, center=center, translation=[1.0, 2.0, 3.0])
    body = only_body(doc)
    assert body.is_brep and brep.is_valid(body.brep)
    assert brep.volume(body.brep) == pytest.approx(6000, abs=1e-9)
    assert body.manifold.volume() == pytest.approx(6000, abs=1e-6)
    b0, b1 = bbox(body)
    np.testing.assert_allclose(b0, np.add(lo, (1, 2, 3)), atol=1e-9)
    np.testing.assert_allclose(b1 - b0, (30, 20, 10), atol=1e-9)
    assert len(body.faces) == 6 and len(body.edges) == 12      # face/edge analysis works on the tessellation


def test_cylinder_brep_volume_is_exact_and_mesh_has_the_curve_smoothness(brep_on):
    doc = Document()
    doc.add_cylinder(5, 12, translation=[10.0, 0.0, 0.0])
    body = only_body(doc)
    assert body.is_brep
    assert brep.volume(body.brep) == pytest.approx(math.pi * 25 * 12, rel=1e-12)
    n = 96
    polygon = 0.5 * n * 25 * math.sin(2 * math.pi / n) * 12          # what a 96-piece mesh cylinder holds
    assert body.manifold.volume() == pytest.approx(polygon, rel=2e-3)
    b0, b1 = bbox(body)
    np.testing.assert_allclose(b0[[2]], [0.0], atol=1e-9)
    np.testing.assert_allclose((b0 + b1)[:2] / 2, (10, 0), atol=1e-6)


def test_box_on_a_picked_plane_matches_the_mesh_placement(brep_on):
    doc_mesh, doc_brep = Document(), Document()
    kw = dict(plane_origin=[5, 5, 5], plane_normal=[1, 0, 0], plane_u=[0, 1, 0], plane_v=[0, 0, 1])
    brep.set_enabled(False)
    doc_mesh.add_box(8, 6, 4, **kw)
    brep.set_enabled(True)
    doc_brep.add_box(8, 6, 4, **kw)
    a, b = bbox(only_body(doc_mesh)), bbox(only_body(doc_brep))
    np.testing.assert_allclose(a[0], b[0], atol=1e-9)
    np.testing.assert_allclose(a[1], b[1], atol=1e-9)
    assert only_body(doc_brep).is_brep


def test_smart_box_options_stay_mesh_bodies(brep_on):
    doc = Document()
    doc.add_box(30, 20, 10, outer_round=2.0)
    assert only_body(doc).brep is None


def test_writing_a_mesh_drops_the_shape(brep_on):
    doc = Document()
    doc.add_box(10, 10, 10)
    body = only_body(doc)
    assert body.is_brep
    body.manifold = body.manifold.translate((1, 0, 0))
    assert body.brep is None


def test_mesh_features_after_a_brep_body_still_work(brep_on):
    """Shell is still a mesh tool: the B-rep box becomes a mesh body with the right hollow volume."""
    from omacad.scripting.api import ScriptContext
    doc = Document()
    ctx = ScriptContext(doc)
    b = ctx.box(30, 20, 10)
    assert doc.bodies[b.id].is_brep
    ctx.shell(b, 2.0, open_top=True)
    body = doc.bodies[b.id]
    assert body.brep is None
    assert body.manifold.volume() == pytest.approx(30 * 20 * 10 - 26 * 16 * 8, rel=1e-6)


def test_switching_off_and_rebuilding_goes_back_to_mesh(brep_on):
    doc = Document()
    doc.add_box(10, 10, 10)
    assert only_body(doc).is_brep
    brep.set_enabled(False)
    doc.timeline.recompute(doc)
    assert only_body(doc).brep is None
    brep.set_enabled(True)
    doc.timeline.recompute(doc)
    assert only_body(doc).is_brep


def test_undo_and_save_roundtrip_with_brep_bodies(brep_on, tmp_path):
    from omacad.io.exporter import Exporter
    doc = Document()
    doc.add_box(10, 10, 10)
    doc.add_cylinder(3, 5, translation=[20.0, 0.0, 0.0])
    path = tmp_path / "b.omacad"
    assert Exporter.save_project(doc, str(path))
    doc.undo()
    assert len(doc.bodies) == 1 and only_body(doc).is_brep
    loaded = Exporter.load_project(str(path))
    assert len(loaded.bodies) == 2 and all(b.is_brep for b in loaded.bodies.values())


def test_unavailable_opencascade_means_inactive(monkeypatch):
    monkeypatch.setattr(brep, "_available", False)
    brep.set_enabled(True)
    try:
        assert not brep.active()
    finally:
        brep.set_enabled(False)


# ---- step 2: fillet / chamfer / combine / move on B-rep bodies ------------------------------------------------------
def rounded_box_volume(a, b, c, r):
    x, y, z = a - 2 * r, b - 2 * r, c - 2 * r
    return x * y * z + 2 * r * (x * y + y * z + x * z) + math.pi * r * r * (x + y + z) + 4 / 3 * math.pi * r ** 3


def line_edges(body, test):
    out = []
    for e in body.edges:
        if getattr(e, "kind", "line") == "line" and test(np.asarray(e.p0), np.asarray(e.p1)):
            out.append(e.ref())
    return out


def test_fillet_all_box_edges_is_exact_and_stays_brep(brep_on):
    doc = Document()
    doc.add_box(40, 30, 20)
    feat = doc.add_fillet([e.ref() for e in only_body(doc).edges], 3.0, "fillet")
    body = only_body(doc)
    assert body.is_brep and feat.skipped == 0
    assert brep.volume(body.brep) == pytest.approx(rounded_box_volume(40, 30, 20, 3), rel=1e-9)
    assert body.manifold.volume() == pytest.approx(rounded_box_volume(40, 30, 20, 3), rel=1e-4)


def test_two_distance_chamfer_puts_the_first_on_the_top_face_and_flip_swaps(brep_on):
    def chamfered(flip):
        doc = Document()
        doc.add_box(40, 30, 20)
        top_front = line_edges(only_body(doc), lambda a, b: a[1] == 0 and b[1] == 0 and a[2] == 20 and b[2] == 20)
        doc.add_fillet(top_front, 1.0, "chamfer", chamfer_type="two", size2=3.0, flip=flip)
        body = only_body(doc)
        assert body.is_brep
        assert brep.volume(body.brep) == pytest.approx(40 * 30 * 20 - 0.5 * 1.0 * 3.0 * 40, rel=1e-12)
        v = np.asarray(body.manifold.to_mesh().vert_properties)[:, :3]
        return float(v[np.abs(v[:, 2] - 20) < 1e-9][:, 1].min())     # where the top face now starts
    assert chamfered(False) == pytest.approx(1.0, abs=1e-9)
    assert chamfered(True) == pytest.approx(3.0, abs=1e-9)


def test_cylinder_rim_fillet_matches_pappus(brep_on):
    doc = Document()
    doc.add_cylinder(10, 20)
    rim = [e.ref() for e in only_body(doc).edges if getattr(e, "kind", "") == "circle" and e.center[2] > 19]
    doc.add_fillet(rim, 2.0, "fillet")
    body = only_body(doc)
    r, R = 2.0, 10.0
    area, xbar = (1 - math.pi / 4) * r * r, (10 - 3 * math.pi) / (3 * (4 - math.pi)) * r
    assert body.is_brep
    assert brep.volume(body.brep) == pytest.approx(math.pi * R * R * 20 - 2 * math.pi * (R - xbar) * area, rel=1e-9)


@pytest.mark.parametrize("fast_view", [False, True])
def test_pipe_saddle_edge_is_rounded_on_brep(brep_on, fast_view):
    """The curved intersection edge of a T-joint: the mesh tools skip it, OpenCascade rounds it. With fast view (72
    pieces) the mesh splits the saddle into two creases; each still finds the one B-rep edge."""
    from omacad.model import quality
    from omacad.scripting.api import ScriptContext
    quality.set_fast_view(fast_view, 72)
    try:
        _pipe_saddle()
    finally:
        quality.set_fast_view(False, 72)


def _pipe_saddle():
    from omacad.scripting.api import ScriptContext
    doc = Document()
    ctx = ScriptContext(doc)
    main = ctx.cylinder(10, 60)
    ctx.move(main, dz=-30)
    ctx.move(main, ry=90)
    ctx.combine(main, ctx.cylinder(6, 20), "join")
    body = doc.bodies[main.id]
    assert body.is_brep
    before = brep.volume(body.brep)
    saddle = [e.ref() for e in body.edges if getattr(e, "kind", "") == "curve"]
    assert saddle
    feat = doc.add_fillet(saddle, 2.0, "fillet")
    body = doc.bodies[main.id]
    assert body.is_brep and feat.skipped == 0
    assert brep.volume(body.brep) > before + 10            # a concave fillet adds material all round the joint


def test_combine_cut_of_two_brep_bodies_is_exact(brep_on):
    from omacad.scripting.api import ScriptContext
    doc = Document()
    ctx = ScriptContext(doc)
    plate = ctx.box(40, 40, 10)
    ctx.combine(plate, ctx.cylinder(6, 12, at=(20, 20, -1)), "cut")
    body = doc.bodies[plate.id]
    assert body.is_brep
    assert brep.volume(body.brep) == pytest.approx(40 * 40 * 10 - math.pi * 36 * 10, rel=1e-12)


def test_move_and_move_copy_keep_the_shape(brep_on):
    from omacad.scripting.api import ScriptContext
    doc = Document()
    ctx = ScriptContext(doc)
    b = ctx.box(10, 10, 10)
    ctx.move(b, dx=5, rz=30)
    c = ctx.move(b, dx=20, copy=True)
    for bid in (b.id, c.id):
        body = doc.bodies[bid]
        assert body.is_brep and brep.volume(body.brep) == pytest.approx(1000, rel=1e-12)
        lo, hi = bbox(body)
        sb = brep.to_manifold(body.brep).bounding_box()
        np.testing.assert_allclose(lo, sb[:3], atol=1e-6)


def test_negative_and_oversized_fillets_fall_back_to_the_mesh_tools(brep_on):
    doc = Document()
    doc.add_box(40, 30, 4)
    feat = doc.add_fillet([e.ref() for e in only_body(doc).edges], 2.5, "fillet")   # > half the thickness
    body = only_body(doc)
    assert body.brep is None and not body.manifold.is_empty()
    doc2 = Document()
    doc2.add_box(20, 20, 20)
    top = line_edges(only_body(doc2), lambda a, b: a[2] == 20 and b[2] == 20)
    doc2.add_fillet(top, -2.0, "fillet")                                              # cove = mesh tool
    assert only_body(doc2).brep is None and only_body(doc2).manifold.volume() < 8000


# ---- step 3: extrude / revolve from sketches ------------------------------------------------------------------------
def _ring(cx, cy, r, n=96, a0=0.0, sweep=360.0, closed=True):
    count = n if closed else n + 1
    return [(cx + r * math.cos(math.radians(a0 + sweep * k / n)), cy + r * math.sin(math.radians(a0 + sweep * k / n)))
            for k in range(count)]


def test_round_parts_of_a_profile_polygon_become_arcs_and_circles():
    from omacad.model.brep.sketch_solids import ring_pieces
    kinds = lambda pts: [p[0] for p in ring_pieces(np.round(np.array(pts), 4))]   # profiles are rounded to 4 decimals
    assert kinds(_ring(0, 0, 6)) == ["circle"]
    assert kinds(_ring(0, 0, 10, n=6)) == ["line"] * 6                             # a hexagon stays a hexagon
    slot = _ring(20, 0, 5, n=24, a0=-90, sweep=180, closed=False) + _ring(0, 0, 5, n=24, a0=90, sweep=180, closed=False)
    assert kinds(slot) == ["arc", "line", "arc", "line"]
    corners = []
    for cx, cy, a0 in ((28, 2, -90), (28, 18, 0), (2, 18, 90), (2, 2, 180)):
        corners += _ring(cx, cy, 2, n=18, a0=a0, sweep=90, closed=False)            # fast view: 72 per circle
    assert kinds(corners) == ["arc", "line"] * 4


def _volumes(doc):
    return {b.name: (b.is_brep, brep.volume(b.brep) if b.is_brep else b.manifold.volume()) for b in doc.bodies.values()}


def test_extrude_join_and_cut_from_sketches_are_exact(brep_on):
    from omacad.scripting.api import ScriptContext
    doc = Document()
    ctx = ScriptContext(doc)
    sk = ctx.sketch("XY")
    sk.rect((0, 0), (40, 30))
    sk.circle((20, 15), 6)
    ctx.extrude(sk, 10)
    (is_brep, v), = _volumes(doc).values()
    assert is_brep and v == pytest.approx(40 * 30 * 10 - math.pi * 36 * 10, rel=1e-6)
    top = ctx.sketch("XY", offset=10)
    top.circle((20, 15), 10)
    ctx.extrude(top, 5, operation="join")
    (is_brep, v), = _volumes(doc).values()
    assert is_brep and v == pytest.approx(40 * 30 * 10 - math.pi * 36 * 10 + math.pi * 100 * 5, rel=1e-6)
    hole = ctx.sketch("XY", offset=15)
    hole.circle((8, 8), 3)
    ctx.extrude(hole, -20, operation="cut")
    (is_brep, v2), = _volumes(doc).values()
    assert is_brep and v2 == pytest.approx(v - math.pi * 9 * 10, rel=1e-6)


def test_rounded_rect_and_hexagon_extrudes(brep_on):
    from omacad.scripting.api import ScriptContext
    from omacad.model.brep import rounding
    doc = Document()
    ctx = ScriptContext(doc)
    sk = ctx.sketch("XY")
    sk.rounded_rect((0, 0), (30, 20), 3)
    ctx.extrude(sk, 5)
    hexa = ctx.sketch("XY")
    hexa.polygon((60, 10), 8, 6)
    ctx.extrude(hexa, 5)
    vols = list(_volumes(doc).values())
    assert all(b for b, _ in vols)
    assert vols[0][1] == pytest.approx((30 * 20 - (4 - math.pi) * 9) * 5, rel=1e-6)
    hex_body = [b for b in doc.bodies.values()][1]
    assert len(rounding.faces(hex_body.brep)) == 8                     # 6 flat sides + top + bottom


@pytest.mark.parametrize("angle", [360, 90])
def test_revolve_is_exact_and_placed_like_the_mesh(brep_on, angle):
    from omacad.scripting.api import ScriptContext
    doc = Document()
    ctx = ScriptContext(doc)
    sk = ctx.sketch("XZ")
    sk.rect((5, 0), (10, 20))
    ctx.revolve(sk, axis="v", angle=angle)
    body = only_body(doc)
    assert body.is_brep
    assert brep.volume(body.brep) == pytest.approx(math.pi * (100 - 25) * 20 * angle / 360, rel=1e-9)
    brep.set_enabled(False)
    mesh_doc = Document()
    mctx = ScriptContext(mesh_doc)
    msk = mctx.sketch("XZ")
    msk.rect((5, 0), (10, 20))
    mctx.revolve(msk, axis="v", angle=angle)
    brep.set_enabled(True)
    np.testing.assert_allclose(bbox(body)[0], bbox(only_body(mesh_doc))[0], atol=2e-3)
    np.testing.assert_allclose(bbox(body)[1], bbox(only_body(mesh_doc))[1], atol=2e-3)


def test_sketch_extrude_then_fillet_its_rim_stays_exact(brep_on):
    from omacad.scripting.api import ScriptContext
    doc = Document()
    ctx = ScriptContext(doc)
    sk = ctx.sketch("XY")
    sk.circle((0, 0), 10)
    ctx.extrude(sk, 20)
    rim = [e.ref() for e in only_body(doc).edges if getattr(e, "kind", "") == "circle" and e.center[2] > 19]
    doc.add_fillet(rim, 2.0, "fillet")
    body = only_body(doc)
    r, R = 2.0, 10.0
    area, xbar = (1 - math.pi / 4) * r * r, (10 - 3 * math.pi) / (3 * (4 - math.pi)) * r
    assert body.is_brep      # the sketch circle is rebuilt from points rounded to 4 decimals: ~1e-6 off
    assert brep.volume(body.brep) == pytest.approx(math.pi * R * R * 20 - 2 * math.pi * (R - xbar) * area, rel=5e-6)


def test_twisted_extrude_and_joins_onto_mesh_bodies_stay_mesh(brep_on):
    from omacad.scripting.api import ScriptContext
    doc = Document()
    ctx = ScriptContext(doc)
    sk = ctx.sketch("XY")
    sk.rect((0, 0), (10, 10))
    b = ctx.extrude(sk, 10)
    doc.timeline.features[-1].twist = 45.0
    doc.timeline.recompute(doc)
    assert only_body(doc).brep is None
    doc2 = Document()
    ctx2 = ScriptContext(doc2)
    ctx2.box(20, 20, 10).rename("Rounded")
    doc2.timeline.features[-1].outer_round = 2.0
    doc2.timeline.recompute(doc2)
    top = ctx2.sketch("XY", offset=10)
    top.circle((10, 10), 4)
    ctx2.extrude(top, 5, operation="join")
    assert only_body(doc2).brep is None and only_body(doc2).manifold.volume() > 20 * 20 * 10 - 100


# ---- step 4: exact STEP export --------------------------------------------------------------------------------------
def _read_step(path):
    """[(name, surface kinds, volume)] of the free shapes in a STEP file, read back with OpenCascade."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.collections import Sequence_TDF_Label
    from omacad.model.brep import rounding
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.ReadFile(str(path))
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    reader.Transfer(doc)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    labels = Sequence_TDF_Label()
    tool.GetFreeShapes(labels)
    out = []
    for i in range(1, labels.Length() + 1):
        label = labels.Value(i)
        shape = tool.GetShape_s(label)
        name = TDataStd_Name()
        text = name.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(), name) else ""
        kinds = {str(BRepAdaptor_Surface(f).GetType()).split(".")[-1].replace("GeomAbs_", "")
                 for f in rounding.faces(shape)}
        out.append((text, kinds, brep.volume(shape)))
    return out


def test_step_export_writes_brep_bodies_exactly_with_names(brep_on, tmp_path):
    from omacad.io.exporter import Exporter
    from omacad.scripting.api import ScriptContext
    doc = Document()
    ctx = ScriptContext(doc)
    b = ctx.box(40, 30, 20, name="Låda")
    ctx.fillet(b, 3, "all")
    ctx.box(20, 20, 10, at=(60, 0, 0), name="Mesh")
    doc.timeline.features[-1].outer_round = 2.0            # a rounded box option: stays a mesh body
    doc.timeline.recompute(doc)
    path = tmp_path / "mix.step"
    assert Exporter.export_all_to_step(doc, str(path))
    assert path.read_bytes().isascii()                     # å written as \X2\00E5\X0\
    shapes = {name: (kinds, vol) for name, kinds, vol in _read_step(path)}
    kinds, vol = shapes["Låda"]
    assert kinds == {"Plane", "Cylinder", "Sphere"}
    assert vol == pytest.approx(rounded_box_volume(40, 30, 20, 3), rel=1e-9)
    kinds, vol = shapes["Mesh"]
    assert kinds == {"Plane"}                              # polyhedral solid, one flat face per triangle
    mesh_body = next(x for x in doc.bodies.values() if x.name == "Mesh")
    assert vol == pytest.approx(mesh_body.manifold.volume(), rel=1e-5)


def test_step_export_without_brep_bodies_or_when_it_fails_uses_the_mesh_writer(tmp_path, monkeypatch):
    from omacad.io import step_brep
    from omacad.io.exporter import Exporter
    doc = Document()
    doc.add_box(10, 10, 10)
    path = tmp_path / "mesh.step"
    assert Exporter.export_all_to_step(doc, str(path))
    assert "Omacad STEP AP214 Export" in path.read_text()
    brep.set_enabled(True)
    try:
        doc2 = Document()
        doc2.add_box(10, 10, 10)
        monkeypatch.setattr(step_brep, "write", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        path2 = tmp_path / "fallback.step"
        assert Exporter.export_all_to_step(doc2, str(path2))
        assert "Omacad STEP AP214 Export" in path2.read_text()
    finally:
        brep.set_enabled(False)


@pytest.mark.skipif(__import__("shutil").which("freecadcmd") is None, reason="FreeCAD not installed")
def test_freecad_reads_the_exact_step(brep_on, tmp_path):
    """An independent reader: FreeCAD finds one valid solid with true cylinders and spheres and the exact volume."""
    import subprocess
    from omacad.io.exporter import Exporter
    doc = Document()
    doc.add_box(40, 30, 20)
    doc.add_fillet([e.ref() for e in only_body(doc).edges], 3.0, "fillet")
    path = tmp_path / "box.step"
    assert Exporter.export_all_to_step(doc, str(path))
    script = tmp_path / "check.py"
    script.write_text("import Part, sys\ns = Part.Shape(); s.read(sys.argv[-1])\n"
                      "print('RESULT', len(s.Solids), s.isValid(), round(s.Solids[0].Volume, 6),\n"
                      "      sorted({type(f.Surface).__name__ for f in s.Solids[0].Faces}))\n")
    out = subprocess.run(["freecadcmd", str(script), str(path)], capture_output=True, text=True, timeout=120).stdout
    line = next(l for l in out.splitlines() if l.startswith("RESULT"))
    assert line == f"RESULT 1 True {round(rounded_box_volume(40, 30, 20, 3), 6)} ['Cylinder', 'Plane', 'Sphere']"
