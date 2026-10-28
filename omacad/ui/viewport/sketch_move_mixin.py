"""Sketch entity move and rotate drag operations."""

import copy
import math
import numpy as np
from PySide6.QtCore import Qt
from omacad.model.sketch import move_entity, rotate_entity, entity_key_points
from omacad.model.sketch_solver import solve_sketch
from omacad.model.sketch_snap import SketchSnapper


class SketchMoveMixin:
    """Sketch move operation state and pointer handling."""

    def _toggle_pick(self, event, x, y) -> bool:
        """Mirror/Move picking: a click adds or removes the whole figure, Ctrl/Shift/Alt+click one element."""
        ent = self._pick_entity(x, y)
        if ent is None:
            return False
        mods = event.modifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier):
            self.selected_entities ^= {ent.entity_id}
        else:
            ids = self.doc.active_sketch.connected_entities(ent.entity_id)
            self.selected_entities = (self.selected_entities - ids) if ids <= self.selected_entities else (self.selected_entities | ids)
        self.selection_changed.emit()
        self.update()
        return True
    def _move_status(self):
        if self._move_phase == "pick":
            n = len(self.selected_entities)
            self.status_message.emit(f"Move: {n} element(s) picked. Click more (Ctrl+click = one element, click again removes), "
                                     "then Enter. Esc cancels.")
        else:
            sk = self.doc.active_sketch
            u_lbl, v_lbl = sk.plane.axis_names() if sk is not None else ("X", "Y")
            self.status_message.emit("Move: click the base point (it snaps to points), then where it should go. "
                                     f"Type {u_lbl} / {v_lbl} for exact distances. The elements keep their angle. Esc cancels.")
    def _move_next(self):
        """Move: picking done, now the base point."""
        if not self.selected_entities:
            self.status_message.emit("Move: pick at least one sketch element first.")
            return
        self._move_phase = "base"
        self._move_status()
        self.update()
    def _begin_move(self, ids):
        sk = self.doc.active_sketch
        ids = {i for i in ids if not getattr(sk.get_entity(i), "projected", False)}
        orig_ents = {e.entity_id: copy.deepcopy(e) for e in sk.entities if e.entity_id in ids}
        # Compute bounding center as rotation pivot
        all_kps = [kp for ent in orig_ents.values() for kp in entity_key_points(ent)]
        if all_kps:
            center_u = sum(p[0] for p in all_kps) / len(all_kps)
            center_v = sum(p[1] for p in all_kps) / len(all_kps)
        else:
            center_u, center_v = 0.0, 0.0

        self._move = {
            "ids": set(ids),
            "orig": orig_ents,
            "before": sk.to_dict(),
            "delta": (0.0, 0.0),
            "angle": 0.0,
            "pivot": (center_u, center_v),
        }
    def _apply_move(self, du: float, dv: float, angle_deg: float = 0.0):
        """Positions the moving entities at original + (du, dv) rotated by angle_deg around pivot."""
        m = self._move
        if not m:
            return
        sk = self.doc.active_sketch
        pivot = m.get("pivot", (0.0, 0.0))
        for i, ent in enumerate(sk.entities):
            orig = m["orig"].get(ent.entity_id)
            if orig is not None:
                moved = copy.deepcopy(orig)
                if abs(angle_deg) > 1e-4:
                    rotate_entity(moved, angle_deg, pivot)
                if abs(du) > 1e-9 or abs(dv) > 1e-9:
                    move_entity(moved, du, dv)
                sk.entities[i] = moved
        sk._bind_texts()
        sk.solve_profiles()
        m["delta"] = (du, dv)
        m["angle"] = angle_deg
        self.update()
    def _end_move(self, commit: bool):
        m = self._move
        self._move = None
        self._drag = None
        self.active_snap = None
        if not m:
            return
        sk = self.doc.active_sketch
        if sk is None:
            return
        du, dv = m["delta"]
        ang = m.get("angle", 0.0)
        has_change = (abs(du) > 1e-9 or abs(dv) > 1e-9 or abs(ang) > 1e-4)
        if commit and has_change and (sk.constraints or sk.dimensions):
            res = solve_sketch(sk, fixed_ids=m["ids"])
            if not res.ok:
                sk.restore_from_dict(m["before"])
                self.status_message.emit(res.message + " - move cancelled.")
                self.doc.notify_changed()
                self.update()
                return
        copy_box = getattr(getattr(self, "tool_panel", None), "chk_copy", None)
        if commit and has_change and copy_box is not None and copy_box.isChecked() and abs(ang) < 1e-4:
            self._keep_originals(sk, m)     # Move with Copy (Björn #75): the moved ones become new elements
        if commit and has_change:
            self.doc.record_sketch_change(sk, m["before"])
            self.doc.timeline.recompute(self.doc)
            self.doc.notify_changed()
        else:
            sk.restore_from_dict(m["before"])
        self.update()
    def _keep_originals(self, sk, m):
        """Puts the originals back where they were and adds the moved elements as copies with new ids (free:
        no constraints or dimensions come along)."""
        moved = [copy.deepcopy(e) for e in sk.entities if e.entity_id in m["ids"]]
        sk.restore_from_dict(m["before"])
        new_ids = set()
        for ent in moved:
            ent.entity_id = sk._new_entity_id(ent.entity_id.rsplit("_", 1)[0])
            if hasattr(ent, "group"):
                ent.group = None            # a copy is not part of the original's polygon / fillet bookkeeping
            if getattr(ent, "fillet_info", None):
                ent.fillet_info = {}
            sk.entities.append(ent)
            new_ids.add(ent.entity_id)
        sk._bind_texts()
        sk.solve_profiles()
        self.selected_entities = new_ids
        self.selection_changed.emit()

    def _snap_move_delta(self, du: float, dv: float):
        """Snaps the dragged elements' key points to geometry/edges, else the grid."""
        m = self._move
        sk = self.doc.active_sketch
        tol = max(0.3, min(8.0, self._entity_tolerance() * 1.25))

        class _Others:
            entities = [e for e in sk.entities if e.entity_id not in m["ids"]]

        refs = self._reference_segments()
        best = None
        kps = [kp for orig in m["orig"].values() for kp in entity_key_points(orig)][:32]
        for kp in kps:
            r = SketchSnapper.snap(raw_uv=(kp[0] + du, kp[1] + dv), sketch=_Others, snap_distance=tol,
                                   grid_step=0.0, enable_grid_snap=False, enable_geom_snap=True,
                                   reference_segments=refs)
            if r.snap_type in ("ORIGIN", "ENDPOINT", "MIDPOINT", "EDGE"):
                ddu, ddv = r.uv[0] - kp[0], r.uv[1] - kp[1]
                dist = math.hypot(ddu - du, ddv - dv)
                if best is None or dist < best[0]:
                    best = (dist, ddu, ddv, r)
        if best:
            self.active_snap = best[3]
            return best[1], best[2]
        self.active_snap = None
        if self.sketch_palette.chk_snap_grid.isChecked():
            return round(du / 5.0) * 5.0, round(dv / 5.0) * 5.0
        return du, dv
    def _drag_move(self, event):
        d = self._drag
        if not d["moved"]:
            if (event.position() - d["press_pos"]).manhattanLength() < 4:
                return
            d["moved"] = True
            self._begin_move(self.selected_entities)
        uv = self.get_sketch_plane_uv(event.position().x(), event.position().y())
        if uv is None:
            return
        du, dv = self._snap_move_delta(uv[0] - d["press_uv"][0], uv[1] - d["press_uv"][1])
        self._apply_move(du, dv)
    def _drag_release(self, event):
        d = self._drag
        self._drag = None
        if d["moved"]:
            self._end_move(True)
        elif not (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and len(self.selected_entities) > 1:
            self.selected_entities = {d["ent_id"]}  # plain click inside a multi-selection narrows it
            self.selection_changed.emit()
        self.update()

    def _spline_drag_move(self, event):
        d = self._spline_drag
        if not d:
            return
        uv = self.get_sketch_plane_uv(event.position().x(), event.position().y())
        if uv is None:
            return
        d["moved"] = True
        sk = self.doc.active_sketch
        if not sk or sk.sketch_id != d["sketch_id"]:
            return
        ent = sk.get_entity(d["entity_id"])
        from omacad.model.sketch_entities import SketchSpline
        if not isinstance(ent, SketchSpline):
            return

        idx = d["index"]
        if d["kind"] == "point":
            sk.move_spline_point(ent.entity_id, idx, uv)
        elif d["kind"] == "tangent":
            # uv is the dragged handle tip pos. The tangent vector is (uv - pt) * sign
            pt = ent.points[idx]
            sign = d["handle_sign"]
            vec = ((uv[0] - pt[0]) * sign, (uv[1] - pt[1]) * sign)
            sk.set_spline_tangent(ent.entity_id, idx, vec)
        self.update()

    def _spline_drag_release(self):
        d = self._spline_drag
        self._spline_drag = None
        if not d:
            return
        sk = self.doc.active_sketch
        if not sk or sk.sketch_id != d["sketch_id"]:
            return
        if d["moved"]:
            if self.doc.record_sketch_change(sk, d["before"]):
                self.doc.timeline.recompute(self.doc)
                self.doc.notify_changed()
        else:
            sk.restore_from_dict(d["before"])
        self.update()

    def _endpoint_drag_move(self, event):
        d = self._endpoint_drag
        if not d:
            return
        uv = self.get_sketch_plane_uv(event.position().x(), event.position().y())
        if uv is None:
            return
        d["moved"] = True
        sk = self.doc.active_sketch
        if not sk or sk.sketch_id != d["sketch_id"]:
            return

        # Magnetic snap to existing geometry endpoints or lines
        tol = max(0.3, min(8.0, self._entity_tolerance() * 1.25))
        snap = SketchSnapper.snap(
            raw_uv=uv,
            sketch=sk,
            snap_distance=tol,
            grid_step=5.0,
            enable_grid_snap=self.sketch_palette.chk_snap_grid.isChecked(),
            enable_geom_snap=self.sketch_palette.chk_snap_points.isChecked(),
            reference_segments=self._reference_segments(),
        )
        target_uv = snap.uv
        self.active_snap = snap if snap.snap_type != "NONE" else None

        ent = sk.get_entity(d["entity_id"])
        if ent is None:
            return
        pname = d["point_name"]
        if getattr(ent, "entity_type", "") == "line":
            if pname == "p1":
                ent.p1 = (float(target_uv[0]), float(target_uv[1]))
            elif pname == "p2":
                ent.p2 = (float(target_uv[0]), float(target_uv[1]))
            # Update length dimension if attached
            length = math.hypot(ent.p2[0] - ent.p1[0], ent.p2[1] - ent.p1[1])
            for dim in sk.dimensions:
                if dim.target_entity_id == ent.entity_id and dim.dim_type == "LENGTH":
                    dim.value = length
        elif getattr(ent, "entity_type", "") == "arc":
            if pname == "p_start":
                ent.p_start = (float(target_uv[0]), float(target_uv[1]))
            elif pname == "p_end":
                ent.p_end = (float(target_uv[0]), float(target_uv[1]))
        elif getattr(ent, "entity_type", "") == "spline":
            ent.points[pname] = (float(target_uv[0]), float(target_uv[1]))

        sk.solve_profiles()
        self.update()

    def _endpoint_drag_release(self):
        d = self._endpoint_drag
        self._endpoint_drag = None
        self.active_snap = None
        if not d:
            return
        sk = self.doc.active_sketch
        if not sk or sk.sketch_id != d["sketch_id"]:
            return
        if d["moved"]:
            ent = sk.get_entity(d["entity_id"])
            if ent is not None:
                pname = d["point_name"]
                cur_pt = ent.points[pname] if getattr(ent, "entity_type", "") == "spline" else (ent.p1 if pname == "p1" else (ent.p2 if pname == "p2" else (ent.p_start if pname == "p_start" else ent.p_end)))
                # Check if it was placed on/snapped to another endpoint or curve to connect them
                tol = max(0.3, min(8.0, self._entity_tolerance() * 1.25))
                for other in sk.entities:
                    if other.entity_id == ent.entity_id or other.is_construction or getattr(other, "projected", False):
                        continue
                    if getattr(other, "entity_type", "") == "line":
                        for oname, opt in (("p1", other.p1), ("p2", other.p2)):
                            if math.hypot(cur_pt[0] - opt[0], cur_pt[1] - opt[1]) <= tol:
                                # Snap exactly onto the point and add COINCIDENT constraint
                                if pname == "p1":
                                    ent.p1 = opt
                                elif pname == "p2":
                                    ent.p2 = opt
                                elif pname == "p_start":
                                    ent.p_start = opt
                                elif pname == "p_end":
                                    ent.p_end = opt
                                from omacad.model.sketch_types import SketchConstraint
                                cid = sk._new_entity_id("c")
                                sk.constraints.append(SketchConstraint(cid, "COINCIDENT", [ent.entity_id, other.entity_id], [pname, oname]))
                                break
                    elif getattr(other, "entity_type", "") == "arc":
                        for oname, opt in (("p_start", other.p_start), ("p_end", other.p_end)):
                            if math.hypot(cur_pt[0] - opt[0], cur_pt[1] - opt[1]) <= tol:
                                if pname == "p1":
                                    ent.p1 = opt
                                elif pname == "p2":
                                    ent.p2 = opt
                                from omacad.model.sketch_types import SketchConstraint
                                cid = sk._new_entity_id("c")
                                sk.constraints.append(SketchConstraint(cid, "COINCIDENT", [ent.entity_id, other.entity_id], [pname, oname]))
                                break
            sk.solve_profiles()
            if self.doc.record_sketch_change(sk, d["before"]):
                self.doc.timeline.recompute(self.doc)
                self.doc.notify_changed()
        else:
            sk.restore_from_dict(d["before"])
        self.update()
