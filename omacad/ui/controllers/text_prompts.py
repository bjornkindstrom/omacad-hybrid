"""Sketch Text tool: the dialog, placing the text, editing it later. One session at a time, one undo step."""
from typing import Optional

from omacad.model.sketch import SketchText
from omacad.ui.dialogs import EmbossDialog, TextDialog
from omacad.ui.controllers.prompt_guards import leaves_sketch

PARAM_KEYS = ("text", "font", "height", "bold", "italic", "spacing", "h_align", "v_align", "flip_h", "flip_v", "angle",
              "placement", "fit", "margin")


class _TextSession:
    def __init__(self, sketch, dlg, entity: Optional[SketchText], draft: Optional[SketchText]):
        self.sketch, self.dlg, self.entity, self.draft = sketch, dlg, entity, draft
        self.before = sketch.to_dict()          # the text's own entry in here is what undo / cancel go back to
        self.placed = entity is not None        # editing starts with the text already in place
        # the edited text's settings, so Cancel resets only this text (other sketch work stays)
        self.orig = {k: getattr(entity, k) for k in PARAM_KEYS + ("anchor", "path_id", "box")} if entity else None

    def before_text(self) -> dict:
        """The sketch as it is now, with only this text as it was before the session: the undo step covers the
        text alone, whatever else was drawn meanwhile (that has its own undo steps)."""
        now = self.sketch.to_dict()
        eid = self.entity.entity_id
        old = next((e for e in self.before["entities"] if e["entity_id"] == eid), None)
        now["entities"] = [old if e["entity_id"] == eid else e for e in now["entities"]
                           if old is not None or e["entity_id"] != eid]
        return now


class TextPromptsMixin:
    """Mixin for MainWindow: prompt_text, prompt_text_edit, on_text_place."""

    _text_session: Optional[_TextSession] = None

    # --- opening ---------------------------------------------------------------------------------------------------
    def prompt_text(self):
        """Text tool: options in the side panel, then click where the text goes (or on the curve it follows)."""
        sk = self.doc.active_sketch
        if sk is None:
            self.status_label.setText("Text: open a sketch first (Create Sketch).")
            return
        if self._text_session is not None:
            self._text_session.dlg.raise_()
            return
        dlg = TextDialog(self)
        draft = SketchText("text_draft", **self._text_args(dlg))
        draft.sketch = sk
        self._start_text_session(_TextSession(sk, dlg, None, draft))
        self.status_label.setText("Text: click in the sketch to place it. Text On Path: click the circle, arc or line it follows.")

    def prompt_text_edit(self, entity_id: str):
        sk = self.doc.active_sketch
        ent = next((e for e in (sk.entities if sk else []) if e.entity_id == entity_id and isinstance(e, SketchText)), None)
        if ent is None:
            return
        if self._text_session is not None:
            self._text_session.dlg.reject()
        dlg = TextDialog(self)
        dlg.set_params(ent)
        self._start_text_session(_TextSession(sk, dlg, ent, None))
        self.viewport.set_sketch_tool("NONE")
        self._text_changed()
        self.status_label.setText("Edit Text: change the options, then OK.")

    @staticmethod
    def _text_args(dlg) -> dict:
        args = dlg.params()
        args["anchor"] = (0.0, 0.0)
        return args

    def _start_text_session(self, session: _TextSession):
        self._text_session = session
        dlg = session.dlg
        self.dock(dlg)
        dlg.changed.connect(self._text_changed)
        dlg.finished.connect(self._text_finished)
        self.viewport.text_wants_path = dlg.is_path()
        self.viewport.set_text_draft(session.draft)
        self.viewport.sketch_tool_changed.connect(self._text_tool_changed)
        self._text_changed()

    # --- live changes ------------------------------------------------------------------------------------------------
    def _text_changed(self):
        s = self._text_session
        if s is None:
            return
        params = s.dlg.params()
        target = s.entity or s.draft
        for key in PARAM_KEYS:
            setattr(target, key, params[key])
        want_path = s.dlg.is_path()
        self.viewport.text_wants_path = want_path
        self.viewport.text_wants_box = s.dlg.is_box()
        if not s.dlg.is_box():
            target.box = None                               # back to plain text: no box
        elif target.box is not None:
            s.dlg.show_fitted_height(target.fitted_height())   # the height the box gives it (font, text, style)
        if not want_path:
            target.path_id = None
        elif s.entity is not None and target.path_id is None:
            self.viewport.set_sketch_tool("TEXT")          # type changed to Text On Path: pick its curve
            self.status_label.setText("Text On Path: click a circle, an arc or a line of this sketch.")
        s.dlg.set_path_text(self._path_name(s.sketch, target.path_id) if want_path else "")
        if s.entity is not None:
            s.sketch.solve_profiles()
        self.viewport.update()

    @staticmethod
    def _path_name(sketch, path_id) -> str:
        ent = next((e for e in sketch.entities if e.entity_id == path_id), None)
        if ent is None:
            return "Click a circle, an arc or a line in the sketch."
        return {"circle": "Circle", "arc": "Arc", "line": "Line"}.get(ent.entity_type, ent.entity_type) + " " + ent.entity_id

    def _text_tool_changed(self, tool: str):
        s = self._text_session
        if s is None:
            return
        if not s.placed and tool != "TEXT":
            s.dlg.reject()                                  # left the tool before placing anything: cancel
        elif s.placed and tool not in ("NONE", "TEXT"):
            s.dlg.accept()                                  # another tool: keep the text as its own undo step first

    # --- placing -----------------------------------------------------------------------------------------------------
    def on_text_place(self, uv, path_id):
        s = self._text_session
        if s is None:
            return
        if s.entity is not None:                            # editing: a click on a curve sets the path
            if path_id:
                s.entity.path_id = path_id
                s.sketch.solve_profiles()
                s.dlg.set_path_text(self._path_name(s.sketch, path_id))
                self.viewport.set_sketch_tool("NONE")
                self.viewport.update()
            return
        args = s.dlg.params()
        if s.dlg.is_box() and s.draft is not None and s.draft.box:
            args["box"] = tuple(s.draft.box)
        if s.dlg.is_path():
            if not path_id:
                return
            args["path_id"] = path_id
            args["anchor"] = (0.0, 0.0)
        else:
            args["anchor"] = tuple(uv)
        if not args["text"].strip():
            self.status_label.setText("Text: type some text first.")
            return
        s.entity = s.sketch.add_text(**args)
        s.placed = True
        self.viewport.set_text_draft(None)
        self.viewport.selected_entities = {s.entity.entity_id}
        self.viewport.set_sketch_tool("NONE")
        self.status_label.setText("Text placed. Adjust the options, then OK. Esc or Cancel removes it.")
        self.viewport.update()

    # --- closing -----------------------------------------------------------------------------------------------------
    def _text_finished(self, result):
        s, self._text_session = self._text_session, None
        if s is None:
            return
        try:
            self.viewport.sketch_tool_changed.disconnect(self._text_tool_changed)
        except (RuntimeError, TypeError):
            pass
        self.viewport.set_text_draft(None)
        self.viewport.text_wants_path = False
        self.viewport.text_wants_box = False
        self.inspector.undock_tool()
        s.dlg.deleteLater()
        if result and s.entity is not None:
            self.doc.record_sketch_change(s.sketch, s.before_text())  # one undo step for placing and editing it
            self.status_label.setText("Text added to the sketch.")
        else:
            if s.entity is not None and s.orig is None:
                s.sketch.delete_entities([s.entity.entity_id])        # only the text placed in this session
            elif s.entity is not None:
                for key, value in s.orig.items():
                    setattr(s.entity, key, value)
                s.sketch.solve_profiles()
            self.status_label.setText("Text cancelled.")
        self.viewport.update()


class EmbossPromptMixin:
    """Mixin for MainWindow: Emboss. The profiles (letters) are picked in the view, the options are in the panel."""

    @leaves_sketch
    def prompt_emboss(self):
        from omacad.model.timeline import EmbossFeature, ExtrudeFeature
        from PySide6.QtWidgets import QMessageBox
        if getattr(self, "_emboss_dlg", None) is not None:
            self._emboss_dlg.raise_()
            return
        if not any(sk.profiles for sk in self.doc.sketches.values()):
            QMessageBox.information(self, "Emboss", "Make some text (Sketch > Text) or a closed shape in a sketch on a face first, "
                                    "then emboss it.")
            return
        doc, vp = self.doc, self.viewport
        dlg = EmbossDialog(self)
        self._emboss_dlg = dlg
        self.dock(dlg)

        def select_text(sketch_id=None):
            """Every letter of the sketch (the selected one, or the newest with text) becomes the selection."""
            sk = doc.sketches.get(sketch_id or (doc.selected_profile[0] if doc.selected_profile else None))
            if sk is None or not sk.text_profile_indices():
                sk = next((s for s in reversed(list(doc.sketches.values())) if s.text_profile_indices()), None)
            idx = sk.text_profile_indices() if sk is not None else []
            if idx:
                doc.selected_profile = (sk.sketch_id, idx[0])
                doc.selected_extra = [(sk.sketch_id, i) for i in idx[1:]]
                vp.update()
            return bool(idx)

        def feature(name="preview"):
            if not doc.selected_profile:
                return None
            s_id, p_idx = doc.selected_profile
            extra, refs, _holes = ExtrudeFeature.selection_parts(doc, s_id, p_idx, doc.selected_extra)
            return EmbossFeature(name, name, s_id, p_idx, extra_profiles=extra, extra_refs=refs, **dlg.get_values())

        def refresh():
            feat = feature()
            solid = None
            if feat is not None:
                try:
                    solid = feat.build_solid(doc)
                except Exception:
                    solid = None
            vp.set_preview(solid, "join" if dlg.get_values()["depth"] > 0 else "cut")
            n = (1 + len(doc.selected_extra)) if doc.selected_profile else 0
            dlg.set_info(f"{n} profile(s) selected. Click letters or shapes in the view, Shift+click for more." if n else
                         "Click the letters (or a shape) in the view, or press the button below.")
            self.status_label.setText("Emboss: pick the profiles to raise or press in, set the depth, OK.")

        def on_pick():
            refresh()

        def on_select_text():
            if not select_text():
                self.status_label.setText("Emboss: this sketch has no text.")
            refresh()

        def finished(result):
            vp.profile_picked.disconnect(on_pick)
            vp.set_preview(None)
            self._emboss_dlg = None
            self.inspector.undock_tool()
            values, exprs, feat = dlg.get_values(), dlg.get_expressions(), feature("final")
            dlg.deleteLater()
            if result and feat is not None and abs(values["depth"]) > 1e-9:
                doc.add_emboss(feat.sketch_id, feat.profile_idx, extra_profiles=feat.extra_profiles,
                               extra_refs=feat.extra_refs, exprs=exprs, **values)
                doc.selected_profile, doc.selected_extra = None, []
                self.status_label.setText(f"{'Embossed' if values['depth'] > 0 else 'Debossed'} {abs(values['depth']):g} mm.")
            else:
                self.status_label.setText("Emboss cancelled." if not result else "Emboss: nothing was selected.")
            vp.update()

        dlg.changed.connect(refresh)
        dlg.select_text_requested.connect(on_select_text)
        vp.profile_picked.connect(on_pick)
        dlg.finished.connect(finished)
        if not doc.selected_profile:
            select_text()                                   # a sketch with text: start with all its letters picked
        refresh()
