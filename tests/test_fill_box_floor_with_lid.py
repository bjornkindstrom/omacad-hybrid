"""Björn #59: Fill face pattern of a hexagon hole in the floor of a box did nothing. Two causes: the box's walls
were taken as an obstacle with their hole filled in (a ring's outline and hole became two filled polygons), and the
lid parked 54 mm above the box cast its whole outline onto the floor. Either left no room for a single copy."""
from pathlib import Path

from omacad.io.exporter import Exporter

DOC = str(Path(__file__).parent / "data" / "fill_box_floor_with_lid.omacad")
HOLE = 83.1384          # volume of one hexagon hole through the 2 mm floor


def test_hexagon_holes_fill_the_floor_around_the_posts():
    doc = Exporter.load_project(DOC)
    box = "body_extrude_2"
    before = doc.bodies[box].manifold.volume()
    pat = doc.add_pattern(["extrude_15"], kind="fill", count1=0.0, spacing1=3.0, spacing2=3.0, mirror_mode="stagger")
    assert pat.copies >= 20
    assert abs((before - doc.bodies[box].manifold.volume()) - HOLE * pat.copies) < 0.05 * HOLE
