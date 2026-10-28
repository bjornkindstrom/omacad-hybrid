"""Edges and faces light up under the cursor when nothing is being edited, so a right-click can fillet/chamfer them."""
from types import SimpleNamespace

from omacad.ui.viewport.viewport import Viewport3D


class _Stub(Viewport3D):
    def __init__(self):   # no GL context needed for the state check
        pass


def _vp(**over):
    vp = _Stub()
    vp.edge_pick_mode = False
    vp.plane_pick_mode = False
    vp.doc = SimpleNamespace(active_sketch=None)
    vp.move_gizmo = None
    vp._move = None
    vp.active_tool_title = lambda: None
    for k, v in over.items():
        setattr(vp, k, v)
    return vp


def test_idle_hover_on_when_nothing_is_edited():
    assert _vp()._idle_hover_ok()


def test_idle_hover_off_while_editing():
    assert not _vp(edge_pick_mode=True)._idle_hover_ok()
    assert not _vp(plane_pick_mode=True)._idle_hover_ok()
    assert not _vp(doc=SimpleNamespace(active_sketch=object()))._idle_hover_ok()
    assert not _vp(move_gizmo={"dragging": False})._idle_hover_ok()
    assert not _vp(active_tool_title=lambda: "Extrude")._idle_hover_ok()


def test_viewport_starts_with_hover_state(qtbot=None):
    """mouseMoveEvent reads both on every move, so a fresh viewport must define them."""
    import inspect
    src = inspect.getsource(Viewport3D.__init__)
    assert "self.hover_edge" in src and "self.hover_face" in src
