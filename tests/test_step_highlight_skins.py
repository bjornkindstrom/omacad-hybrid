"""Clicking a step in the browser colours what it changed: only real material, and without a crash
(report 20261025-121221: stripes over the whole jar thread when Chamfer 5 was selected)."""
import os
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from omacad.io.exporter import Exporter
from omacad.model.document import Document
from omacad.model.kernel import CadKernel
from omacad.ui.timeline_bar import STEP_CHANGE_MIN_THICKNESS

DATA = Path(__file__).parent / "data" / "jar_chamfer_step_highlight.omacad"


def _area(render_mesh) -> float:
    t = render_mesh.vertices.reshape(-1, 3, 3).astype(float)
    return float(np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1).sum() / 2)


def test_chamfer_step_shows_the_chamfer_ring_not_skins_over_the_thread():
    doc = Exporter.load_project(str(DATA))
    doc.timeline.recompute(doc)
    index = next(i for i, f in enumerate(doc.timeline.features) if f.name == "Chamfer 5")
    added, removed = doc.step_changes(index)
    shown = CadKernel.extract_render_mesh(added, min_thickness=STEP_CHANGE_MIN_THICKNESS)
    z = shown.vertices.reshape(-1, 3, 3).mean(axis=1)[:, 2]
    assert z.min() > 23.9                         # the chamfer sits at z 24..27, the thread below it is untouched
    # every face of the chamfer ring (its only solid part) is still drawn
    ring = max(added.decompose(), key=lambda part: part.volume())
    ring_mesh = ring.to_mesh()
    v, f = np.asarray(ring_mesh.vert_properties)[:, :3], np.asarray(ring_mesh.tri_verts)
    areas = np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1) / 2
    assert abs(_area(shown) - areas[v[f].mean(axis=1)[:, 2] > 23.9].sum()) < 1e-3
    assert added.surface_area() - _area(shown) > 2000     # the skins that were drawn as stripes
    assert _area(CadKernel.extract_render_mesh(removed, min_thickness=STEP_CHANGE_MIN_THICKNESS)) == 0


def test_solid_material_is_drawn_in_full():
    doc = Exporter.load_project(str(DATA))
    doc.timeline.recompute(doc)
    for name in ("Jar", "Shell 1", "Move Lid (1)"):
        index = next(i for i, f in enumerate(doc.timeline.features) if f.name == name)
        for part in doc.step_changes(index):
            if part is not None:
                shown = CadKernel.extract_render_mesh(part, min_thickness=STEP_CHANGE_MIN_THICKNESS)
                assert abs(_area(shown) - part.surface_area()) < 1e-3 * part.surface_area(), name


def test_clicking_a_step_in_the_browser_does_not_rename_or_rebuild():
    from omacad.ui.browser import BrowserTree
    from omacad.ui.object_browser import FEATURE_ROLE
    app = QApplication.instance() or QApplication([])
    doc = Document()
    doc.add_box(10, 10, 10)
    doc.add_cylinder(3, 10)
    widget = BrowserTree(doc)
    widget.show()
    widget.tree.expandAll()
    app.processEvents()
    changes = []
    doc.change_listeners.append(lambda: changes.append(1))
    try:
        for fid in [f.feature_id for f in doc.timeline.features]:
            item = next(it for it, _ in widget._walk() if it.data(0, FEATURE_ROLE) == fid
                        and it.data(0, Qt.ItemDataRole.UserRole)[0] == "feature")
            widget.on_item_clicked(item, 0)       # used to rebuild the tree under its own walk: RuntimeError
        assert changes == []
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()
