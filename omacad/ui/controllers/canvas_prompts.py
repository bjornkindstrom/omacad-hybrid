"""Grouped MainWindow tool prompt workflows."""

import os
from typing import Optional
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox
from omacad.model.timeline import (
    ExtrudeFeature, SplitBodyFeature, ShellFeature, MoveFeature
)
from omacad.ui.dialogs import (
    RoundEdgesDialog, PatternDialog, OffsetPlaneDialog,
    SketchPlaneDialog, ExtrudeDialog, BoxDialog, CylinderDialog, PrismDialog,
    SphereDialog, CombineDialog, SplitBodyDialog, ShellDialog, MoveBodyDialog,
    ThreadDialog
)
from omacad.ui.canvas_dialog import CanvasEditorDialog


class CanvasPromptsMixin:
    """Canvas prompt workflows for MainWindow."""

    def prompt_canvas_on_face(self, face):
        self.prompt_insert_canvas(preselected_face=face)

    def prompt_insert_canvas(self, preselected_plane_id: str = "", preselected_face=None):
        """Insert reference image onto a plane, edit/crop/calibrate with tape measure."""
        dlg = CanvasEditorDialog(self.doc, self, preselected_plane_id=preselected_plane_id or None,
                                 preselected_face=preselected_face)
        if dlg.exec():
            data = dlg.get_canvas_data()
            if data and data.get("image_data"):
                cid = self.doc.add_canvas(**data)
                self.viewport.update()
                self.status_label.setText(f"Inserted image reference: {data['name']} ({data['width_mm']:.1f} × {data['height_mm']:.1f} mm).")

    def prompt_edit_canvas(self, cid: str):
        """Edit / calibrate an existing canvas reference image."""
        c = self.doc.canvases.get(cid)
        if not c:
            return
        dlg = CanvasEditorDialog(self.doc, self, existing_canvas_id=cid)
        if dlg.exec():
            data = dlg.get_canvas_data()
            if data:
                # Invalidate cached texture in viewport if image data or dimensions changed
                if hasattr(self.viewport, "_canvas_textures") and cid in self.viewport._canvas_textures:
                    del self.viewport._canvas_textures[cid]
                self.doc.update_canvas(cid, **data)
                self.viewport.update()
                self.status_label.setText(f"Updated image reference: {data.get('name', c.get('name'))}.")
