"""A body's render mesh and face/edge analysis are computed on first use, once per manifold, with exactly the result
an immediate analysis gives; intermediate bodies of a rebuild that nothing reads are never analysed."""
import copy

import numpy as np

from omacad.model import faces_surfaces
from omacad.model.document import Document
from omacad.model.features import base
from omacad.model.features.base import Body
from omacad.model.kernel import CadKernel


def _count_analyses(monkeypatch):
    calls = []
    original = base.compute_planar_faces_and_edges

    def counted(manifold, body_id):
        calls.append(body_id)
        return original(manifold, body_id)
    monkeypatch.setattr(base, "compute_planar_faces_and_edges", counted)
    return calls


def test_lazy_analysis_matches_immediate_and_is_shared_by_copies(monkeypatch):
    calls = _count_analyses(monkeypatch)
    m = CadKernel.create_box(20, 10, 5)
    body = Body("b", "Box", m)
    body.update_render_mesh()
    assert calls == []                                    # nothing read yet
    twin = copy.copy(body)                                # a checkpoint copy shares the pending analysis
    faces, edges = faces_surfaces.compute_planar_faces_and_edges(m, "b")
    assert len(body.faces) == len(faces) == 6 and len(body.edges) == len(edges) == 12
    assert calls == ["b"]
    assert twin.edges is body.edges and len(calls) == 1   # the copy reuses it
    for got, want in zip(body.faces, faces):
        assert np.allclose(got.normal, want.normal) and np.allclose(got.tris, want.tris)
    assert body.render_mesh is twin.render_mesh is not None


def test_setting_a_value_wins_over_the_pending_one(monkeypatch):
    calls = _count_analyses(monkeypatch)
    body = Body("b", "Box", CadKernel.create_box(1, 1, 1))
    body.update_render_mesh()
    body.faces = []
    assert body.faces == [] and len(body.edges) == 12     # edges still come from the analysis
    assert calls == ["b"]
    body.manifold = CadKernel.create_box(2, 2, 2)         # a new manifold without update keeps the old analysis
    assert len(body.edges) == 12


def test_a_body_never_updated_has_empty_defaults():
    body = Body("b", "Box", CadKernel.create_box(1, 1, 1))
    assert body.faces == [] and body.edges == [] and body.render_mesh is None


def test_rebuild_analyses_only_final_bodies(monkeypatch):
    doc = Document()
    box = doc.add_box(20, 20, 10)
    doc.add_box(5, 5, 30)
    calls = _count_analyses(monkeypatch)
    doc.timeline.clear_cache()
    doc.timeline.recompute(doc)
    finals = sorted(doc.bodies)
    assert sorted(calls) == finals                        # each final body once, at the end of the rebuild
    for b in doc.bodies.values():
        assert "faces" in b.__dict__ and "render_mesh" in b.__dict__   # analysed before the GUI asks
    assert box is not None


def test_rebuild_in_the_busy_thread_warms_what_the_first_paint_draws(monkeypatch):
    from omacad import busy
    from omacad.model import quality
    from omacad.model.features.base import analyse_bodies
    doc = Document()
    doc.add_cylinder(10, 20)
    body = next(iter(doc.bodies.values()))
    body.update_render_mesh()                             # a fresh mesh with nothing cached yet
    monkeypatch.setattr(busy, "in_worker", lambda: True)
    quality.set_fast_view(True)
    try:
        analyse_bodies(doc)
        mesh = body.render_mesh
        assert True in mesh.__dict__.get("_drawn_edges", {})            # tangent edges on by default
        warmed = mesh._display[len(mesh.drawn_edges(True))]
        assert mesh.display_arrays(mesh.drawn_edges(True)) is warmed    # the paint takes the very same arrays
        fresh = CadKernel.extract_render_mesh(body.manifold)
        for a, b in zip(fresh.display_arrays(fresh.drawn_edges(True)), warmed):
            assert np.array_equal(a, b)
    finally:
        quality.set_fast_view(False)
