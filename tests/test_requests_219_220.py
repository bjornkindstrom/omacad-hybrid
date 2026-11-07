"""#219/#220: Split Body makes two separate objects; each keeps every parameter of the steps that built it."""
import math

import pytest
from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.sketch import SketchPlane


def _jar_and_lid():
    """The report: Cylinder 1 → Shell 1 (5 mm) → split by an offset plane into a jar and a lid."""
    doc = Document()
    body = doc.add_cylinder(30., 60.)
    cylinder = doc.timeline.last_added.feature_id
    doc.add_shell(body.body_id, 5.)
    shell = doc.timeline.last_added.feature_id
    plane = doc.add_construction_plane(SketchPlane.create_named("XY"), 50.)
    split = doc.split_body(body.body_id, plane)
    return doc, body.body_id, split.result_body_id, cylinder, shell


def _objects(doc):
    history = doc.object_history
    history.sync(doc)
    kinds = {f.feature_id: f.feature_type for f in doc.timeline.features}
    return {o.name: ([kinds[f] for f in o.feature_ids], o.body_ids) for o in history.objects.values()}


def _volume(doc, bid):
    return doc.bodies[bid].manifold.volume()


def test_split_gives_two_objects_with_their_own_steps():
    doc, lid, jar, _, _ = _jar_and_lid()
    assert _objects(doc) == {
        "Cylinder 1": (["cylinder", "shell", "split_body"], [lid]),
        "Cylinder 1 (Split)": (["cylinder", "shell", "split_body"], [jar]),
    }
    assert doc.bodies[jar].name == "Cylinder 1 (Split)"
    # closed 5 mm shell cut at z = 50: the lid is a 5 mm top on a 5 mm ring, the jar the rest
    assert _volume(doc, lid) == pytest.approx(math.pi * 30 ** 2 * 5 + math.pi * (30 ** 2 - 25 ** 2) * 5, rel=2e-3)
    assert _volume(doc, jar) == pytest.approx(math.pi * 30 ** 2 * 50 - math.pi * 25 ** 2 * 45, rel=2e-3)


def test_editing_one_half_leaves_the_other_alone():
    doc, lid, jar, cylinder, shell = _jar_and_lid()
    jar_volume = _volume(doc, jar)
    doc.edit_feature_dimension(shell, "thickness", "2")       # the lid's own Shell: still editable after the split
    assert _volume(doc, jar) == pytest.approx(jar_volume)
    assert _volume(doc, lid) == pytest.approx(math.pi * 30 ** 2 * 2 + math.pi * (30 ** 2 - 28 ** 2) * 8, rel=2e-3)
    doc.edit_feature_dimension(cylinder, "radius", "40")
    assert _volume(doc, jar) == pytest.approx(jar_volume)
    jar_shell = next(f.feature_id for f in doc.timeline.features
                     if f.feature_type == "shell" and f.feature_id != shell)
    doc.edit_feature_dimension(jar_shell, "thickness", "3")
    assert _volume(doc, jar) == pytest.approx(math.pi * 30 ** 2 * 50 - math.pi * 27 ** 2 * 47, rel=2e-3)
    restored = Document()
    Exporter.apply_dict(restored, Exporter.document_to_dict(doc))
    assert _volume(restored, jar) == pytest.approx(_volume(doc, jar))
    assert _volume(restored, lid) == pytest.approx(_volume(doc, lid))


def test_split_is_one_undo_step():
    doc, lid, jar, _, _ = _jar_and_lid()
    doc.undo()
    assert set(doc.bodies) == {lid}
    assert [f.feature_type for f in doc.timeline.features] == ["cylinder", "shell"]
    doc.redo()
    assert set(doc.bodies) == {lid, jar}


def test_browser_shows_both_objects_with_their_parameters():
    from omacad.ui.browser import BrowserTree
    from omacad.ui.object_browser import add_histories
    QApplication.instance() or QApplication([])
    doc, *_ = _jar_and_lid()
    tree = BrowserTree(doc)
    root = QTreeWidgetItem(["root"])
    add_histories(tree, root)
    objects = root.child(0)
    rows = {}
    for i in range(objects.childCount()):
        obj = objects.child(i)
        rows[obj.text(0)] = [obj.child(j).text(0) for j in range(obj.childCount())]
    assert set(rows) == {"Cylinder 1", "Cylinder 1 (Split)"}
    assert all(any("Shell" in label for label in labels) for labels in rows.values())
    assert "Split Body 1 result" not in rows
