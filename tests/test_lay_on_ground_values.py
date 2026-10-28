"""The Move panel's 'Lay a face on the ground': the numbers it fills in put the chosen face on z = 0."""
import numpy as np
import pytest
import manifold3d as m3d

from omacad.model.geometry import lay_on_ground_values


@pytest.mark.parametrize("about_centre", [True, False])
@pytest.mark.parametrize("normal,point", [((1, 0, 0), (5, 0, 0)), ((0, 1, 0), (0, 3, 0)), ((1, 1, 0), (2.5, 2.5, 0)), ((0, 0, 1), (0, 0, 4))])
def test_face_ends_up_on_the_ground(normal, point, about_centre):
    body = m3d.Manifold.cube((10, 6, 8), True).translate((7, 3, 9))
    bb = body.bounding_box()
    centre = (np.array(bb[:3]) + np.array(bb[3:])) / 2
    # a slanted face on a cube turned 45 degrees about z so (1,1,0) really is a face
    if normal == (1, 1, 0):
        body = body.rotate((0, 0, 45))
        bb = body.bounding_box()
        centre = (np.array(bb[:3]) + np.array(bb[3:])) / 2
    n = np.array(normal, float) / np.linalg.norm(normal)
    face_pt = centre + n * 1000.0   # not used for position, only to find the face below
    # the face: the extreme point of the body along n
    mesh = body.to_mesh()
    verts = mesh.vert_properties[:, :3]
    origin = verts[np.argmax(verts @ n)]
    dx, dy, dz, rx, ry, rz = lay_on_ground_values(n, origin, centre, about_centre)
    m = body
    if about_centre:
        m = m.translate(tuple(-centre)).rotate((rx, ry, rz)).translate(tuple(centre))
    else:
        m = m.rotate((rx, ry, rz))
    m = m.translate((dx, dy, dz))
    assert m.bounding_box()[2] == pytest.approx(0.0, abs=1e-6)     # lowest point on the ground
    assert m.bounding_box()[5] > 1.0                               # and the body stands above it
