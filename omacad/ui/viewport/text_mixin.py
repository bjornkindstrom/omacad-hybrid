"""The sketch Text tool in the view: a ghost of the text follows the cursor, a click places it; for Text On Path the
click picks the circle, arc or line the text runs along (it lights up while you hover it)."""
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt

from omacad.model.sketch import SketchArc, SketchCircle, SketchLine, SketchText


class TextToolMixin:
    PATH_KINDS = (SketchCircle, SketchArc, SketchLine)

    def set_text_draft(self, draft: Optional[SketchText]) -> None:
        """The text being placed (None: none). Its anchor follows the cursor; on a path it follows the hovered curve."""
        self.text_draft = draft
        self._text_box_start = None
        self.update()

    def _text_box_from(self, start, end) -> None:
        """Text In Box: the draft fills the box between the first corner and `end`."""
        draft = self.text_draft
        w, h = abs(end[0] - start[0]), abs(end[1] - start[1])
        draft.anchor = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
        draft.box = (max(w, 1e-3), max(h, 1e-3))

    def _text_path_pick(self, x: float, y: float):
        ent = self._pick_entity(x, y)
        return ent if isinstance(ent, self.PATH_KINDS) else None

    def _text_hover(self, x: float, y: float) -> None:
        draft = getattr(self, "text_draft", None)
        if draft is None:
            return
        if draft.path_id is not None or getattr(self, "text_wants_path", False):
            ent = self._text_path_pick(x, y)
            new_id = ent.entity_id if ent is not None else None
            if new_id != self.hover_entity_id:
                self.hover_entity_id = new_id
            draft.path_id = new_id
        elif getattr(self, "text_wants_box", False):
            if getattr(self, "_text_box_start", None) is not None and self.sketch_current_uv is not None:
                self._text_box_from(self._text_box_start, self.sketch_current_uv)
        elif self.sketch_current_uv is not None:
            draft.anchor = tuple(self.sketch_current_uv)
        self.update()

    def _text_press(self, event, x: float, y: float) -> bool:
        """Left click with the Text tool: place the draft, or edit the text under the cursor. True when handled."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        sk = self.doc.active_sketch
        under = self._pick_entity(x, y)
        draft = getattr(self, "text_draft", None)
        if isinstance(under, SketchText) and not getattr(self, "text_wants_path", False):
            self.text_edit_requested.emit(under.entity_id)
            return True
        if draft is None:
            return True
        if getattr(self, "text_wants_path", False):
            ent = self._text_path_pick(x, y)
            if ent is None:
                self.status_message.emit("Text On Path: click a circle, an arc or a line of this sketch.")
                return True
            self.text_place_requested.emit(None, ent.entity_id)
            return True
        uv = self.get_sketch_plane_uv(x, y)
        if self.sketch_current_uv is not None:
            uv = self.sketch_current_uv
        if uv is None:
            return True
        if getattr(self, "text_wants_box", False):
            start = getattr(self, "_text_box_start", None)
            if start is None:                            # first corner; the box follows the cursor to the second
                self._text_box_start = (float(uv[0]), float(uv[1]))
                self.status_message.emit("Text In Box: click the opposite corner.")
                return True
            if abs(uv[0] - start[0]) < 1e-3 or abs(uv[1] - start[1]) < 1e-3:
                self.status_message.emit("Text In Box: the box needs a width and a height; click another corner.")
                return True
            self._text_box_from(start, uv)
            self._text_box_start = None
            self.text_place_requested.emit(tuple(draft.anchor), None)
            return True
        self.text_place_requested.emit((float(uv[0]), float(uv[1])), None)
        return True

    def render_text_preview(self, mvp: np.ndarray) -> None:
        """The ghost of the text being placed, in the highlight colour; the boxes of Text In Box texts, dashed."""
        sk = self.doc.active_sketch
        if sk is not None:
            self._render_text_boxes(mvp, sk)
        draft = getattr(self, "text_draft", None)
        if draft is None or sk is None or self.sketch_tool != "TEXT":
            return
        if getattr(self, "text_wants_box", False) and getattr(self, "_text_box_start", None) is None:
            return                                       # no box yet: nothing to show until the first corner
        flat = []
        for p1, p2 in self._box_lines(draft) + draft.to_lines():
            w1, w2 = sk.plane.uv_to_world(*p1), sk.plane.uv_to_world(*p2)
            flat.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
        if not flat:
            return
        from OpenGL import GL
        from omacad.ui import theme
        from omacad.ui.settings import get_settings
        col = get_settings().highlight_color_rgb01() or theme.palette().highlight01()
        GL.glDisable(GL.GL_DEPTH_TEST)
        self.draw_thick_lines(mvp, flat, (*col, 0.9), 2.0, halo=False)
        GL.glEnable(GL.GL_DEPTH_TEST)

    @staticmethod
    def _box_lines(text):
        corners = text.box_corners() if text is not None else None
        return [] if not corners else [(corners[i], corners[(i + 1) % 4]) for i in range(4)]

    def _render_text_boxes(self, mvp, sk) -> None:
        """The area each Text In Box text may fill, as a thin dashed outline (it is not a profile)."""
        flat = []
        for ent in sk.entities:
            if isinstance(ent, SketchText):
                for p1, p2 in self._box_lines(ent):
                    a, b = np.asarray(p1, float), np.asarray(p2, float)
                    n = max(1, int(np.linalg.norm(b - a) / 1.5))
                    for k in range(0, n, 2):                 # dashes of 1.5 mm
                        q1, q2 = a + (b - a) * k / n, a + (b - a) * min(k + 1, n) / n
                        w1, w2 = sk.plane.uv_to_world(*q1), sk.plane.uv_to_world(*q2)
                        flat.extend([w1[0], w1[1], w1[2], w2[0], w2[1], w2[2]])
        if flat:
            from OpenGL import GL
            GL.glDisable(GL.GL_DEPTH_TEST)
            self.draw_thick_lines(mvp, flat, (0.6, 0.65, 0.72, 0.8), 1.0, halo=False)
            GL.glEnable(GL.GL_DEPTH_TEST)
