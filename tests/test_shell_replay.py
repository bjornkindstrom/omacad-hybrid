"""Shell right after other steps gives the same body as when the history is rebuilt (on reload): it reads the body's
history, which must be current when the step is added."""
import pytest

from omacad.model.document import Document

UP = dict(plane_normal=[0, 0, 1], plane_u=[1, 0, 0], plane_v=[0, 1, 0])


def test_shell_of_a_stacked_cylinder_survives_a_rebuild():
    doc = Document()
    jar = doc.add_cylinder(20, 40)
    neck = doc.add_cylinder(16, 10, plane_origin=[0, 0, 40], **UP)
    doc.combine_bodies(jar.body_id, neck.body_id, "join")
    doc.add_shell(jar.body_id, 2.0, open_faces=[{"normal": [0, 0, 1], "origin": [0, 0, 50], "body_id": jar.body_id}])
    added = doc.bodies[jar.body_id].manifold.volume()
    doc.timeline.recompute(doc)
    assert doc.bodies[jar.body_id].manifold.volume() == pytest.approx(added, rel=1e-9)
