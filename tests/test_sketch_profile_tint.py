"""Closed profiles tinted and loose ends marked in the open sketch (sketch plan step 7)."""
import pytest

from omacad.model.document import Document
from omacad.model.sketch_gaps import open_ends


def _u_shape(sk, dx=0.0):
    sk.add_line((dx, 0.0), (dx + 20.0, 0.0))
    sk.add_line((dx + 20.0, 0.0), (dx + 20.0, 10.0))
    sk.add_line((dx, 10.0), (dx, 0.0))


def test_an_almost_closed_chain_shows_its_two_loose_ends():
    doc = Document()
    sk = doc.start_sketch()
    _u_shape(sk)
    assert sorted(open_ends(sk)) == [pytest.approx((0.0, 10.0)), pytest.approx((20.0, 10.0))]
    sk.add_line((20.0, 10.0), (0.0, 10.0))                    # closing the gap
    assert open_ends(sk) == []


def test_a_lone_line_a_circle_and_a_t_junction_have_no_loose_ends():
    doc = Document()
    sk = doc.start_sketch()
    sk.add_line((0.0, 0.0), (10.0, 0.0))
    sk.add_circle((30.0, 0.0), 5.0)
    assert open_ends(sk) == []                                 # drawing one line is not a mistake
    sk.add_line((5.0, 0.0), (5.0, 8.0))                        # a T: it ends on the first line's middle
    assert open_ends(sk) == [pytest.approx((5.0, 8.0))]
    sk.add_line((5.0, 8.0), (9.0, 8.0), is_construction=True)
    assert open_ends(sk) == [pytest.approx((5.0, 8.0))]        # construction lines close nothing


def test_the_open_sketch_tints_its_closed_profiles_and_rings_its_gaps():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from omacad.ui.viewport.viewport import Viewport3D
    doc = Document()
    vp = Viewport3D(doc)
    sk = doc.start_sketch()
    assert vp.live_profile_fill() is None
    _u_shape(sk)
    sk.add_line((20.0, 10.0), (0.0, 10.0))
    sk.solve_profiles()
    tris = vp.live_profile_fill()
    assert tris is not None and len(tris) % 3 == 0
    assert vp.live_profile_fill() is tris                      # unchanged profiles: the same buffer
    assert tris[:, 0].min() == pytest.approx(0.0, abs=1e-6) and tris[:, 0].max() == pytest.approx(20.0, abs=1e-6)
    assert vp.sketch_open_ends(sk) == []
    _u_shape(sk, 40.0)                                         # a second, open shape beside it
    sk.solve_profiles()
    assert len(vp.sketch_open_ends(sk)) == 2
    vp.deleteLater()
