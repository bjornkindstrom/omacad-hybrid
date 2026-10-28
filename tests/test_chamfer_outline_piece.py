"""A click picks one piece of a flat face's outline for Fillet/Chamfer, a double-click the whole outline (#104)."""
from pathlib import Path

import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.faces_edges import loop_contains

DOC = str(Path(__file__).parent / "data" / "chamfer_single_outline_piece.omacad")


def _top():
    doc = Exporter.load_project(DOC)
    body = next(iter(doc.bodies.values()))
    loop = next(e for e in body.edges if e.kind == "loop" and e.n[2] > 0.5)
    pieces = [e for e in body.edges if e.kind in ("line", "circle") and loop_contains(loop, e)]
    return doc, body, loop, pieces


def test_outline_pieces_are_edges_of_their_own():
    _, body, loop, pieces = _top()
    lines = [e for e in pieces if e.kind == "line"]
    assert any(e.kind == "circle" for e in pieces)
    # the pieces add up to the outline
    total = sum(e.length for e in lines) + sum(float(e.radius) * float(e.sweep) for e in pieces if e.kind == "circle")
    assert total == pytest.approx(loop.perimeter, rel=1e-3)


def test_double_click_on_a_piece_takes_the_whole_outline():
    from omacad.ui.viewport.picker_mixin import PickerMixin
    _, body, loop, pieces = _top()

    class Stub:
        def _visible_edges(self):
            return body.edges
    for piece in pieces:
        assert [e.kind for e in PickerMixin._edge_loop(Stub(), piece)] == ["loop"]


def test_chamfer_one_piece_leaves_the_rest_sharp():
    doc, body, loop, pieces = _top()
    v0 = body.manifold.volume()
    line = max((e for e in pieces if e.kind == "line"), key=lambda e: e.length)
    others = [e for e in pieces if e.kind == "line" and e is not line and e.length > 5.0]
    doc.add_fillet([line.ref()], 2.0, kind="chamfer")
    after = next(iter(doc.bodies.values()))
    removed = v0 - after.manifold.volume()
    # a 2 mm bevel along a 60 mm edge; the slanted neighbouring walls trim the ends a little
    assert 0.97 * 2.0 * line.length < removed <= 1.0 * 2.0 * line.length
    # the other straight pieces of the outline are still sharp edges at full length
    lengths = [e.length for e in after.edges if e.kind == "line"]
    for o in others:
        assert any(abs(o.length - L) < 1e-3 for L in lengths), o.length
    # face pick and whole-outline chamfer: the outline alone, its pieces are not cut a second time
    doc2, body2, loop2, pieces2 = _top()
    doc2.add_fillet([loop2.ref(), *[p.ref() for p in pieces2]], 2.0, kind="chamfer")
    doc3, body3, loop3, _ = _top()
    doc3.add_fillet([loop3.ref()], 2.0, kind="chamfer")
    vol = lambda d: next(iter(d.bodies.values())).manifold.volume()
    assert vol(doc2) == pytest.approx(vol(doc3), rel=1e-6)
