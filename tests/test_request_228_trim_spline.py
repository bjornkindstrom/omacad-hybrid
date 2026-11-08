"""#228: Trim works with splines - the stubs where an offset line and an offset spline cross can be removed."""
import math
from pathlib import Path

from omacad.model.sketch_trim import trim_plan, apply_trim

DATA = Path(__file__).parent / "data" / "request_228_offset_spline.json"


def _sketch():
    """Lennart's sketch from the request (a feedback file keeps the open sketch only in its "sketches" list)."""
    import json
    from omacad.model.sketch import Sketch
    from omacad.model.sketch_entities import SketchLine, SketchPlane, SketchSpline
    data = json.loads(DATA.read_text())["sketches"][0]
    sk = Sketch("s", "Sketch 1", SketchPlane.create_named("XZ"))
    for e in data["entities"]:
        sk.entities.append((SketchLine if e["entity_type"] == "line" else SketchSpline).from_dict(e))
    return sk


def _ent(sk, eid):
    return next(e for e in sk.entities if e.entity_id == eid)


def test_trim_line_stub_past_spline_and_spline_stub_below_line():
    sk = _sketch()
    sp = _ent(sk, "spline_3")
    shape_before = sp.get_points(samples_per_span=64)
    # the line's stub beyond the crossing with the offset spline
    plan = trim_plan(sk, 19.8, 2.0, 0.2)
    assert plan is not None and plan[0].entity_id == "line_4"
    apply_trim(sk, plan)
    line = next(e for e in sk.entities if e.entity_type == "line" and abs(e.p1[1] - 2.0) < 1e-9)
    xs = sorted((line.p1[0], line.p2[0]))
    assert xs[0] == 0.0 and 18.6 < xs[1] < 19.9
    cross = (xs[1], 2.0)
    # the spline's stub below the line
    plan = trim_plan(sk, 18.7, 1.55, 0.2)
    assert plan is not None and plan[0].entity_id == "spline_3"
    apply_trim(sk, plan)
    new = [e for e in sk.entities if e.entity_type == "spline" and e.entity_id != "spline_2"]
    assert len(new) == 1 and new[0].control_points
    pts = new[0].get_points(samples_per_span=64)
    assert math.dist(pts[0], cross) < 1e-6           # meets the trimmed line exactly
    assert math.dist(pts[-1], shape_before[-1]) < 1e-9
    # the kept part keeps its shape
    far = [q for q in shape_before if q[1] > 3.0]
    worst = max(min(math.dist(q, p) for p in pts) for q in far[::8])
    assert worst < 0.05


def test_spline_cuts_a_line_and_fit_spline_is_trimmed():
    from omacad.model.sketch import Sketch
    from omacad.model.sketch_entities import SketchPlane, SketchSpline
    sk = Sketch("s", "S", SketchPlane.create_named("XY"))
    sk.add_line((0.0, 5.0), (20.0, 5.0))
    sk.entities.append(SketchSpline("spline_9", [(2.0, 0.0), (8.0, 10.0), (14.0, 0.0), (18.0, 10.0)]))
    plan = trim_plan(sk, 10.0, 5.0, 0.3)            # the line between the two spline crossings
    assert plan is not None and plan[0].entity_type == "line" and len(plan[2]) == 2
    plan = trim_plan(sk, 2.3, 0.6, 0.6)              # the fit spline's start below the line
    assert plan is not None and plan[0].entity_id == "spline_9"
    apply_trim(sk, plan)
    sp = next(e for e in sk.entities if e.entity_type == "spline")
    assert not sp.control_points and abs(sp.points[0][1] - 5.0) < 1e-6
    assert (8.0, 10.0) in sp.points and sp.points[-1] == (18.0, 10.0)
