"""A fillet/chamfer tool for an edge whose faces are flat (180°) or folded onto each other (0°) is empty: there is
no corner to round, and it must not divide by tan(0)."""
import numpy as np
import pytest

from omacad.model.kernel import CadKernel


class _Edge:
    def __init__(self, d2):
        self.p0, self.p1 = np.array([0.0, 0.0, 0.0]), np.array([0.0, 0.0, 10.0])
        self.d1, self.d2 = np.array([1.0, 0.0, 0.0]), np.asarray(d2, dtype=float)
        self.convex = True


@pytest.mark.parametrize("d2", [[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]])
@pytest.mark.parametrize("kind", ["fillet", "chamfer"])
def test_degenerate_edges_give_an_empty_tool(d2, kind):
    assert CadKernel.edge_round_tool(_Edge(d2), 2.0, kind).is_empty()


def test_a_right_angle_still_gives_the_exact_chamfer_sliver():
    tool = CadKernel.edge_round_tool(_Edge([0.0, 1.0, 0.0]), 2.0, "chamfer")
    assert tool.volume() == pytest.approx(0.5 * 2 * 2 * 10, rel=0.02)    # the margin outside the corner adds a little
