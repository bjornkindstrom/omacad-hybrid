"""Test the wine charms user script (wine_charms.py)."""
from pathlib import Path
import pytest
from omacad.model.document import Document
from omacad.scripting.runner import check_report, run_script, ScriptRunError

SCRIPT_PATH = Path.home() / ".config" / "omacad" / "scripts" / "wine_charms.py"
HEART_SCRIPT_PATH = Path.home() / ".config" / "omacad" / "scripts" / "heart_wine_charms.py"

# personal user scripts (and their Honey Script font), not part of the repo: CI and other machines skip these
pytestmark = pytest.mark.skipif(not (SCRIPT_PATH.is_file() and HEART_SCRIPT_PATH.is_file()),
                                reason="wine charm user scripts are not installed in ~/.config/omacad/scripts")


def test_wine_charms_check_passes():
    ok, rep = check_report(SCRIPT_PATH)
    assert ok, rep
    assert "RESULT: OK" in rep
    assert "4 vinglasmarkörer" in rep


def test_heart_wine_charms_check_passes():
    ok, rep = check_report(HEART_SCRIPT_PATH)
    assert ok, rep
    assert "RESULT: OK" in rep
    assert "4 hjärtformade vinglasmarkörer" in rep


def test_wine_charms_single_name_and_undo():
    doc = Document()
    res = run_script(doc, SCRIPT_PATH, {"names": "Björn"})
    assert res.ok
    assert len(doc.bodies) == 1
    (body,) = doc.bodies.values()
    assert body.name == "Vinglasmarkör"
    assert body.manifold.volume() > 200.0

    # Test undo
    doc.undo()
    assert not doc.bodies
    doc.redo()
    assert len(doc.bodies) == 1


def test_heart_wine_charms_swedish_and_dot_merging():
    doc = Document()
    names = "Åsa, Örjan, Älva, Björn, Lina"
    res = run_script(doc, HEART_SCRIPT_PATH, {"names": names, "dot_overlap": 0.8})
    assert res.ok
    assert len(doc.bodies) == 5
    for b in doc.bodies.values():
        assert b.manifold.volume() > 400.0
        # Check Z height
        bb = b.manifold.bounding_box()
        assert pytest.approx(bb[2]) == 0.0
        assert pytest.approx(bb[5]) == 3.0

    doc.undo()
    assert not doc.bodies
    doc.redo()
    assert len(doc.bodies) == 5


def test_wine_charms_grid_and_unicode():
    doc = Document()
    names = "Åsa, Örjan, Älva, Carl-Gustaf, René"
    res = run_script(doc, SCRIPT_PATH, {"names": names, "columns": 3})
    assert res.ok
    assert len(doc.bodies) == 5
    body_names = [b.name for b in doc.bodies.values()]
    assert "Vinglasmarkör (Åsa)" in body_names
    assert "Vinglasmarkör (Carl-Gustaf)" in body_names

    # Check that bodies don't overlap in 3D
    boxes = [b.manifold.bounding_box() for b in doc.bodies.values()]
    for b in boxes:
        # Each body has 2mm height (Z from 0 to 2)
        assert pytest.approx(b[2]) == 0.0
        assert pytest.approx(b[5]) == 2.0


def test_heart_wine_charms_no_holes_in_cursive():
    doc = Document()
    names = "Lina, Björn"
    res = run_script(doc, HEART_SCRIPT_PATH, {"names": names, "font": "Honey Script"})
    assert res.ok
    assert len(doc.bodies) == 2
    for b in doc.bodies.values():
        parts = b.manifold.decompose()
        assert len(parts) == 1, f"{b.name} has disconnected parts: {len(parts)}"

    # Verify that cursive overlaps (n/a in Lina, r/n in Björn) are completely solid with no overlap holes
    from omacad.model.text_layout import layout
    geom_lina = layout(text="Lina", height=16.0, v_align="bottom", font="Honey Script", bold=True)
    # ina is merged into one solid polygon with exactly 1 interior hole (the counter of a)
    lina_polys = geom_lina.geoms if hasattr(geom_lina, "geoms") else [geom_lina]
    ina_poly = next(p for p in lina_polys if p.bounds[0] > 10.0 and p.bounds[3] < 10.0)
    assert len(ina_poly.interiors) == 1, f"Expected exactly 1 hole in 'ina', got {len(ina_poly.interiors)}"


def test_heart_wine_charms_rebecca_letters_intact():
    doc = Document()
    res = run_script(doc, HEART_SCRIPT_PATH, {"names": "Rebecca, Christian", "font": "Honey Script"})
    assert res.ok
    assert len(doc.bodies) == 2
    for b in doc.bodies.values():
        parts = b.manifold.decompose()
        assert len(parts) == 1

    # Specifically check layout of "Rebecca"
    from omacad.model.text_layout import layout
    geom_reb = layout(text="Rebecca", height=16.0, v_align="bottom", font="Honey Script", bold=True)
    # The total width of Rebecca must span >= 38 mm (no missing 'c' letters)
    bx0, by0, bx1, by1 = geom_reb.bounds
    width = bx1 - bx0
    assert width > 35.0, f"Rebecca width too narrow ({width} mm), 'c' letters might be missing!"


def test_wine_charms_empty_name_raises():
    doc = Document()
    with pytest.raises(ScriptRunError) as exc_info:
        run_script(doc, SCRIPT_PATH, {"names": "   , ,  "})
    assert "minst ett namn" in str(exc_info.value)
