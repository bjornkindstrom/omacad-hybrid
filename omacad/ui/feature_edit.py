"""
Omacad - Editing steps of the parametric history (timeline).

Each step type reuses the dialog it was created with, filled with its current values.
Accepting rebuilds everything after the step.
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from omacad import applog
from omacad.model import quality
from omacad.ui.dialogs import (
    BoxDialog, CylinderDialog, PrismDialog, SphereDialog, ExtrudeDialog, RoundEdgesDialog, PatternDialog, MoveBodyDialog,
    ThreadDialog, RevolveDialog, ShellDialog, CombineDialog, SplitBodyDialog, HoleDialog
)

DIRECTIONS = ["one_side", "symmetric", "two_sides"]
OPERATIONS = ["auto", "new_body", "join", "cut", "intersect"]  # same order as the Extrude dialog


def can_edit(feature) -> bool:
    return feature.feature_type in (
        "box", "cylinder", "prism", "sphere", "extrude", "emboss", "revolve", "loft",
        "sketch", "fillet", "hole", "pattern", "move", "thread", "offset_face", "honeycomb", "shell", "combine", "split_body"
    )


def _exec_with_preview(win, doc, dlg, preview_fn, hide_body_ids=(), wiring=(), start=None):
    """Connects `preview_fn` to `dlg.changed` (if present) with a 60ms debounce + interactive quality mode,
    hides `hide_body_ids` during editing so the preview cleanly replaces the current solid, runs `dlg.exec()`,
    and restores visibility and clears the preview after. `wiring` (signal, slot) pairs are connected while the
    dialog is open (face picking in the view, as when the step was made); `start` runs once before it opens."""
    vp = getattr(win, "viewport", None)
    saved_vis = {}
    timer = None
    prev_interactive = quality.is_interactive_mode()
    for sig, slot in wiring:
        sig.connect(slot)
    if vp is not None and start is not None:
        start()
    if vp is not None:
        quality.set_interactive_mode(True)
        for bid in hide_body_ids:
            if bid and bid in doc.bodies:
                saved_vis[bid] = doc.bodies[bid].visible
                doc.bodies[bid].visible = False
        if hasattr(dlg, "changed") and preview_fn is not None:
            def _run_preview():
                try:
                    preview_fn()
                except Exception as e:      # a value the step can't build yet: no preview, but say why
                    vp.set_preview(None)
                    applog.log("ERROR", f"edit preview of {dlg.windowTitle()}: {e!r}")
                    if hasattr(win, "status_label"):
                        win.status_label.setText(f"No preview for these values: {e}")
                vp.update()

            timer = QTimer(dlg)
            timer.setSingleShot(True)
            timer.setInterval(60)
            timer.timeout.connect(_run_preview)
            dlg.changed.connect(timer.start)
            _run_preview()
        vp.update()
    try:
        res = dlg.exec()
        if timer is not None and timer.isActive():
            timer.stop()
            _run_preview()
        return res
    finally:
        for sig, slot in wiring:
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        if vp is not None:
            if getattr(vp, "plane_pick_mode", False):
                vp.end_plane_pick()
            if wiring or start is not None:
                vp.shell_target_body_id = ""
                vp.highlighted_faces = []
            quality.set_interactive_mode(prev_interactive)
            if timer is not None:
                timer.stop()
            if hasattr(dlg, "changed") and preview_fn is not None and timer is not None:
                try:
                    dlg.changed.disconnect(timer.start)
                except (RuntimeError, TypeError):
                    pass
            for bid, vis in saved_vis.items():
                if bid in doc.bodies:
                    doc.bodies[bid].visible = vis
            vp.set_preview(None)
            vp.update()



class _StateBefore:
    """The document as it stood before step `index`: its bodies from `doc.step_states`, everything else from `doc`.
    'Auto' decides join/cut/new body against this, not against the bodies the step itself already changed."""

    def __init__(self, doc, state: dict):
        from omacad.model.features.base import Body
        from omacad.model.faces import compute_planar_faces
        self._doc = doc
        self.bodies = {bid: Body(bid, bid, m, faces=compute_planar_faces(m, bid)) for bid, m in state.items()}

    def __getattr__(self, name):
        return getattr(self._doc, name)


def _primitive_face_wiring(vp, dlg, mode="primitive_face", on_plane=None):
    """'On face' in a primitive or Thread panel: the button starts face picking in the view, the pick goes to the panel."""
    wiring = [(dlg.pick_face_requested, lambda: vp.begin_plane_pick(mode)),
              (vp.primitive_face_picked, on_plane or dlg.set_target_plane)]
    return wiring


def edit_feature(win, doc, index: int) -> bool:
    """Opens the right editor for step `index` with live 3D preview. Sketches are edited in sketch mode (returns False).
    Like Fusion 360, the history is rolled back to the step while its panel is open, so the view and every face or
    point picked show the model as it was before the step; OK or Cancel rolls forward again."""
    if index not in doc.step_states or index + 1 not in doc.step_states:
        doc.timeline.recompute(doc)     # steps just added have no recorded states yet: previews start from them
    states = dict(doc.step_states)
    history = doc.object_history
    history.sync(doc)
    feature = doc.timeline.features[index]
    owner = history.owners[feature.feature_id]
    local_steps = history.objects[owner].feature_ids
    local_index = local_steps.index(feature.feature_id)
    saved_markers = dict(history.markers)
    previous = local_steps[local_index - 1] if local_index else None
    doc.object_step_to(owner, previous)
    committed = [False]

    def commit(**params) -> bool:
        committed[0] = True
        history.markers = dict(saved_markers)
        changed = doc.edit_feature(index, **params)
        if not changed:
            doc.timeline.recompute(doc)
            doc.notify_changed()
        return changed

    try:
        return _edit_feature(win, doc, index, states, commit)
    finally:
        if not committed[0]:
            history.markers = dict(saved_markers)
            doc.timeline.recompute(doc)
            doc.notify_changed()


def _edit_feature(win, doc, index: int, states: dict, commit) -> bool:
    feat = doc.timeline.features[index]
    t = feat.feature_type
    vp = getattr(win, "viewport", None)
    state_before = states.get(index, {})

    if t == "loft":
        from omacad.model.features.sweep import LoftFeature
        from omacad.model.features.base import find_profile
        from omacad.ui.dialogs.sweep_dlg import SweepLoftDialog, OPERATIONS as LOFT_OPS
        dlg = SweepLoftDialog(doc, "loft", win)
        dlg.setWindowTitle(f"Edit {feat.name}")
        profiles = []
        for sid, idx, sig in feat.sections:
            j = find_profile(doc.sketches[sid], idx, sig)
            if j is not None:
                profiles.append((sid, j))
        dlg.set_profiles(profiles)
        dlg.spn_twist.setValue(feat.twist)
        if feat.exprs.get("twist"):
            dlg.spn_twist.set_expression(feat.exprs["twist"])
        dlg.cmb_op.setCurrentIndex([k for k, _ in LOFT_OPS].index(feat.operation))

        def sections():
            return [LoftFeature.section_ref(doc, s, i) for s, i in dlg.profiles]

        def preview_loft():
            solid = LoftFeature("preview", feat.name, sections(), dlg.operation(), dlg.spn_twist.value()).build_solid(doc)
            vp.set_preview(solid, dlg.operation())

        shown = {sid: sk.visible for sid, sk in doc.sketches.items()}
        selected = doc.selected_profile, list(doc.selected_extra)
        chain = getattr(vp, "profile_chain_mode", False)

        def sync_profiles():
            doc.selected_profile = dlg.profiles[0] if dlg.profiles else None
            doc.selected_extra = list(dlg.profiles[1:])

        def picked():
            dlg.set_profiles(([doc.selected_profile] if doc.selected_profile else []) + list(doc.selected_extra))

        dlg.changed.connect(sync_profiles)
        try:
            for sk in doc.sketches.values():
                sk.visible = True
            vp.profile_chain_mode = True
            sync_profiles()
            accepted = _exec_with_preview(win, doc, dlg, preview_loft,
                                          wiring=((vp.profile_picked, picked),))
        finally:
            vp.profile_chain_mode = chain
            doc.selected_profile, doc.selected_extra = selected
            for sid, visible in shown.items():
                doc.sketches[sid].visible = visible
        if not accepted:
            return False
        return commit(sections=sections(), operation=dlg.operation(), twist=dlg.spn_twist.value(),
                      exprs=dlg.get_expressions())

    if t == "extrude":
        from omacad.model.timeline import ExtrudeFeature
        dlg = ExtrudeDialog(doc, win)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.select_profile((feat.sketch_id, feat.profile_idx))
        dlg.cmb_dir.setCurrentIndex(DIRECTIONS.index(feat.direction) if feat.direction in DIRECTIONS else 0)
        dlg.spn_dist.setValue(feat.distance)
        dlg.spn_dist2.setValue(abs(feat.distance2))
        dlg.spn_offset.setValue(getattr(feat, "start_offset", 0.0))
        dlg.spn_twist.setValue(getattr(feat, "twist", 0.0))
        if feat.exprs.get("twist"):
            dlg.spn_twist.set_expression(feat.exprs["twist"])
        if feat.exprs.get("distance"):
            dlg.spn_dist.set_expression(feat.exprs["distance"])
        if feat.exprs.get("distance2"):
            dlg.spn_dist2.set_expression(feat.exprs["distance2"])
        if feat.exprs.get("start_offset"):
            dlg.spn_offset.set_expression(feat.exprs["start_offset"])
        dlg.cmb_op.setCurrentIndex(OPERATIONS.index(feat.operation) if feat.operation in OPERATIONS else 0)

        def _preview_extrude():
            s_id, p_idx, dist, op = dlg.get_values()
            direction, dist2 = dlg.get_direction()
            start_offset = dlg.get_start_offset()
            if s_id is None:
                vp.set_preview(None)
                return
            tmp = ExtrudeFeature("tmp", "tmp", s_id, p_idx, dist, op, direction, dist2,
                                 extra_profiles=feat.extra_profiles, extra_refs=feat.extra_refs, holes=feat.holes,
                                 start_offset=start_offset, twist=dlg.get_twist())
            solid = tmp.build_solid(doc)
            vp.set_preview(solid, op if op != "auto" else feat.operation)

        hide_ids = [f"body_{feat.feature_id}"] if feat.operation == "new_body" else []
        if not _exec_with_preview(win, doc, dlg, _preview_extrude, hide_ids):
            return False
        s_id, p_idx, dist, op = dlg.get_values()
        direction, dist2 = dlg.get_direction()
        start_offset = dlg.get_start_offset()
        if s_id is None:
            return False
        if op == "auto":  # decide with the step's own parameters and the bodies before it, as when it was made
            op = ExtrudeFeature("tmp", "tmp", s_id, p_idx, dist, "auto", direction, dist2,
                                extra_profiles=feat.extra_profiles, extra_refs=feat.extra_refs, holes=feat.holes,
                                start_offset=start_offset, twist=dlg.get_twist()).resolve_operation(_StateBefore(doc, state_before))
        return commit(sketch_id=s_id, profile_idx=p_idx, distance=dist,
                                direction=direction, distance2=dist2, start_offset=start_offset,
                                twist=dlg.get_twist(), operation=op, exprs=dlg.get_expressions())

    if t == "emboss":
        from omacad.ui.dialogs import EmbossDialog
        from omacad.model.timeline import EmbossFeature
        dlg = EmbossDialog(win, feat.depth, editing=True)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.set_values(feat)

        def _preview_emboss():
            vals = dlg.get_values()
            tmp = EmbossFeature("tmp", "tmp", feat.sketch_id, feat.profile_idx,
                                extra_profiles=feat.extra_profiles, extra_refs=feat.extra_refs, **vals)
            solid = tmp.build_solid(doc)
            vp.set_preview(solid, "join" if vals["depth"] >= 0 else "cut")

        if not _exec_with_preview(win, doc, dlg, _preview_emboss):
            return False
        return commit(exprs=dlg.get_expressions(), **dlg.get_values())

    if t == "revolve":
        from omacad.model.timeline import RevolveFeature
        dlg = RevolveDialog(doc, win)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.select_profile((feat.sketch_id, feat.profile_idx))
        dlg.spn_angle.setValue(feat.angle)
        dlg.spn_angle2.setValue(feat.angle2)
        if feat.direction in DIRECTIONS:
            dlg.cmb_dir.setCurrentIndex(DIRECTIONS.index(feat.direction))
        if feat.operation in OPERATIONS:
            dlg.cmb_op.setCurrentIndex(OPERATIONS.index(feat.operation))
        for key, spn in (("angle", dlg.spn_angle), ("angle2", dlg.spn_angle2)):
            if feat.exprs.get(key):
                spn.set_expression(feat.exprs[key])

        def _preview_revolve():
            s_id, p_idx = dlg.get_values()
            if s_id is None:
                vp.set_preview(None)
                return
            op = dlg.get_operation()
            tmp = RevolveFeature("tmp", "tmp", s_id, p_idx, operation=op, axis=dlg.get_axis(),
                                 angle=dlg.spn_angle.value(), direction=dlg.get_direction(),
                                 angle2=dlg.spn_angle2.value(), extra_profiles=feat.extra_profiles)
            solid = tmp.build_solid(doc)
            vp.set_preview(solid, op if op != "auto" else feat.operation)

        hide_ids = [f"body_{feat.feature_id}"] if feat.operation == "new_body" else []
        if not _exec_with_preview(win, doc, dlg, _preview_revolve, hide_ids):
            return False
        s_id, p_idx = dlg.get_values()
        if s_id is None:
            return False
        op = dlg.get_operation()
        if op == "auto":
            op = RevolveFeature("tmp", "tmp", s_id, p_idx, operation="auto", axis=dlg.get_axis(),
                                angle=dlg.spn_angle.value(), direction=dlg.get_direction(),
                                angle2=dlg.spn_angle2.value(), extra_profiles=feat.extra_profiles,
                                ).resolve_operation(_StateBefore(doc, state_before))
        return commit(sketch_id=s_id, profile_idx=p_idx, axis=dlg.get_axis(),
                                angle=dlg.spn_angle.value(), direction=dlg.get_direction(),
                                angle2=dlg.spn_angle2.value(), operation=op, exprs=dlg.get_expressions())

    if t == "box":
        from omacad.model.features.primitives import BoxFeature
        dlg = BoxDialog(win)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.spn_length.setValue(feat.length)
        dlg.spn_width.setValue(feat.width)
        dlg.spn_height.setValue(feat.height)
        dlg.set_smart_params(feat)
        if getattr(feat, "plane_origin", None) is not None:
            dlg.plane_origin = feat.plane_origin
            dlg.plane_normal = feat.plane_normal
            dlg.plane_u = feat.plane_u
            dlg.plane_v = feat.plane_v
            idx = dlg.cmb_placement.findData("on_face")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        elif feat.center is True or feat.center == "center":
            idx = dlg.cmb_placement.findData("center")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        elif feat.center is False or feat.center == "corner":
            idx = dlg.cmb_placement.findData("corner")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        else:
            idx = dlg.cmb_placement.findData("bottom_center")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        for key, spin in (("length", dlg.spn_length), ("width", dlg.spn_width), ("height", dlg.spn_height),
                          ("taper_angle", dlg.spn_taper), ("wall_thickness", dlg.spn_wall), ("outer_round", dlg.spn_outer_round),
                          ("inner_round", dlg.spn_inner_round)):
            if feat.exprs.get(key):
                spin.set_expression(feat.exprs[key])

        def _preview_box():
            l, w, h, center, po, pn, pu, pv = dlg.get_values()
            smart = dlg.get_smart_params()
            tmp = BoxFeature("tmp", "tmp", l, w, h, center, translation=feat.translation,
                             plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv, **smart)
            vp.set_preview(tmp.build_solid(), "new_body")

        if not _exec_with_preview(win, doc, dlg, _preview_box, [f"body_{feat.feature_id}"],
                                  wiring=_primitive_face_wiring(vp, dlg)):
            return False
        l, w, h, center, po, pn, pu, pv = dlg.get_values()
        return commit(length=l, width=w, height=h, center=center,
                                plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv,
                                exprs=dlg.get_expressions(), **dlg.get_smart_params())

    if t in ("cylinder", "prism"):
        from omacad.model.features.primitives import CylinderFeature, PrismFeature
        prism = t == "prism"
        dlg = PrismDialog(win) if prism else CylinderDialog(win)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.spn_radius.setValue(feat.across_flats if prism else feat.radius)
        if prism:
            dlg.spn_sides.setValue(feat.sides)
        dlg.spn_height.setValue(feat.height)
        dlg.set_smart_params(feat)
        if getattr(feat, "plane_origin", None) is not None:
            dlg.plane_origin = feat.plane_origin
            dlg.plane_normal = feat.plane_normal
            dlg.plane_u = feat.plane_u
            dlg.plane_v = feat.plane_v
            idx = dlg.cmb_placement.findData("on_face")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        elif feat.center is True or feat.center == "center":
            idx = dlg.cmb_placement.findData("center")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        else:
            idx = dlg.cmb_placement.findData("bottom_center")
            if idx >= 0:
                dlg.cmb_placement.setCurrentIndex(idx)
        for key, spin in (("across_flats" if prism else "radius", dlg.spn_radius), ("height", dlg.spn_height),
                          ("taper_angle", dlg.spn_taper), ("wall_thickness", dlg.spn_wall), ("outer_round", dlg.spn_outer_round),
                          ("inner_round", dlg.spn_inner_round)):
            if feat.exprs.get(key):
                spin.set_expression(feat.exprs[key])

        def _preview_cylinder():
            r, h, center, po, pn, pu, pv = dlg.get_values()
            smart = dlg.get_smart_params()
            place = dict(plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv, translation=feat.translation, **smart)
            tmp = (PrismFeature("tmp", "tmp", r, h, center, sides=dlg.sides(), **place) if prism
                   else CylinderFeature("tmp", "tmp", r, h, center, **place))
            vp.set_preview(tmp.build_solid(), "new_body")

        if not _exec_with_preview(win, doc, dlg, _preview_cylinder, [f"body_{feat.feature_id}"],
                                  wiring=_primitive_face_wiring(vp, dlg)):
            return False
        r, h, center, po, pn, pu, pv = dlg.get_values()
        size = {"across_flats": r, "sides": dlg.sides()} if prism else {"radius": r}
        return commit(**size, height=h, center=center,
                                plane_origin=po, plane_normal=pn, plane_u=pu, plane_v=pv,
                                exprs=dlg.get_expressions(), **dlg.get_smart_params())

    if t == "sphere":
        from omacad.model.kernel import CadKernel
        dlg = SphereDialog(win)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.spn_radius.setValue(feat.radius)
        if feat.exprs.get("radius"):
            dlg.spn_radius.set_expression(feat.exprs["radius"])

        def _preview_sphere():
            vp.set_preview(CadKernel.create_sphere(dlg.get_values()).translate(tuple(feat.translation)), "new_body")

        if not _exec_with_preview(win, doc, dlg, _preview_sphere, [f"body_{feat.feature_id}"]):
            return False
        return commit(radius=dlg.get_values(), exprs=dlg.get_expressions())

    if t == "hole":
        import numpy as np
        from omacad.model.features.hole import HoleFeature
        from omacad.model.features.base import Body
        from omacad.model.sketch_entities import SketchPlane
        dlg = HoleDialog(win, feat.to_dict(), editing=True)
        dlg.setWindowTitle(f"Edit {feat.name}")
        points = list(feat.points)
        dlg.set_points(points)
        plane = (SketchPlane.from_face(np.asarray(points[0]["normal"], dtype=float),
                                       np.asarray(points[0]["origin"], dtype=float)) if points else None)
        dlg.set_plane(plane)
        vp.hole_place_plane = plane
        vp.hole_place_points = [p["origin"] for p in points]
        for key, field in (("diameter", dlg.spn_diameter), ("depth", dlg.spn_depth),
                           ("cb_diameter", dlg.spn_cb_diameter), ("cb_depth", dlg.spn_cb_depth),
                           ("cs_diameter", dlg.spn_cs_diameter), ("cs_angle", dlg.spn_cs_angle),
                           ("tip_angle", dlg.spn_tip_angle), ("chamfer_depth", dlg.spn_chamfer_depth),
                           ("chamfer_angle", dlg.spn_chamfer_angle)):
            if feat.exprs.get(key):
                field.set_expression(feat.exprs[key])
        target_ids = list(getattr(feat, "target_body_ids", [])) or list(state_before)

        def pick_hole_plane():
            vp.end_hole_place()
            vp.begin_plane_pick("hole_plane")

        def plane_picked(selected_plane):
            nonlocal plane
            plane = selected_plane
            points.clear()
            dlg.set_plane(plane)
            dlg.set_points(points)
            vp.begin_hole_place(plane)

        def place_points():
            if plane is not None:
                vp.begin_hole_place(plane, [p["origin"] for p in points])

        def point_picked(hit):
            p, n = hit, plane.normal
            if not any(np.linalg.norm(np.asarray(p) - np.asarray(old["origin"])) < 1e-3 for old in points):
                points.append({"origin": np.asarray(p).tolist(), "normal": np.asarray(n).tolist()})
                dlg.set_points(points)
                vp.hole_place_points = [q["origin"] for q in points]
                preview_hole()

        def preview_hole():
            params = dlg.values()
            params["points"] = points
            tmp = HoleFeature("preview", "preview", **params)
            bodies = {}
            for bid in target_ids:
                if bid not in state_before:
                    continue
                b = Body(bid, bid, state_before[bid])
                b.update_render_mesh = lambda: None
                bodies[bid] = b

            class PreviewDoc:
                pass
            PreviewDoc.bodies = bodies
            tmp.execute(PreviewDoc)
            vp.set_display_override({bid: b.manifold for bid, b in bodies.items()})

        accepted = _exec_with_preview(win, doc, dlg, preview_hole, target_ids,
                                      wiring=((dlg.pick_requested, pick_hole_plane),
                                              (dlg.place_requested, place_points),
                                              (vp.plane_picked, plane_picked),
                                              (vp.hole_point_picked, point_picked)))
        if vp.plane_pick_mode and vp.plane_pick_purpose == "hole_plane":
            vp.end_plane_pick()
        vp.clear_hole_place()
        vp.set_display_override(None)
        if not accepted:
            return False
        params = dlg.values()
        params["points"] = points
        return commit(**params, exprs=dlg.get_expressions())

    if t == "fillet":
        from omacad.model.timeline import FilletFeature
        from omacad.model.features.base import Body
        from omacad.model.faces import compute_planar_edges
        dlg = RoundEdgesDialog(win, feat.kind, feat.size, editing=True, chamfer_type=feat.chamfer_type,
                               size2=feat.size2, angle=feat.angle, flip=feat.flip)
        dlg.setWindowTitle(f"Edit {feat.name}")
        for key, spin in (("size", dlg.spn_size), ("size2", dlg.spn_size2), ("angle", dlg.spn_angle)):
            if feat.exprs.get(key):
                spin.set_expression(feat.exprs[key])

        # Find which body was modified by this fillet step and precompute its edges once
        after_state = states.get(index + 1, {})
        mod_bids = [bid for bid, m in state_before.items() if bid in after_state]
        precomputed_edges = {}
        for bid, m in state_before.items():
            try:
                precomputed_edges[bid] = compute_planar_edges(m)
            except Exception:
                precomputed_edges[bid] = []

        def _preview_fillet():
            tmp_doc_bodies = {}
            for bid, m in state_before.items():
                b = Body(bid, bid, m, edges=list(precomputed_edges.get(bid, ())))
                # Avoid re-running full trimesh face/edge extraction on every spinbox change
                b.update_render_mesh = lambda: None
                tmp_doc_bodies[bid] = b

            class _TmpDoc:
                bodies = tmp_doc_bodies

            v = dlg.values()
            tmp = FilletFeature("tmp", "tmp", feat.edges, v["size"], v["kind"], v["chamfer_type"], v["size2"],
                                v["angle"], v["flip"])
            tmp.execute(_TmpDoc)
            if mod_bids and mod_bids[0] in tmp_doc_bodies:
                vp.set_preview(tmp_doc_bodies[mod_bids[0]].manifold, "new_body")

        kept_edges = list(getattr(vp, "step_edges", []))

        def _show_edges():      # outline the edges this step rounds, so you can tell which of several it is
            vp.step_edges = feat.edges_in(state_before)

        try:
            if not _exec_with_preview(win, doc, dlg, _preview_fillet, mod_bids[:1], start=_show_edges):
                return False
        finally:
            if vp is not None:
                vp.step_edges = kept_edges
        return commit(**dlg.values(), exprs=dlg.get_expressions())

    if t == "offset_face":
        from omacad.ui.dialogs import OffsetFaceDialog
        from omacad.model.features.offset_face import OffsetFaceFeature
        dlg = OffsetFaceDialog(win, feat.distance, editing=True)
        dlg.setWindowTitle(f"Edit {feat.name}")
        if feat.exprs.get("distance"):
            dlg.spn_dist.set_expression(feat.exprs["distance"])
        base_m = state_before.get(feat.target_body_id)

        def _preview_offset_face():
            if base_m is not None:
                res, _ = OffsetFaceFeature.compute(base_m, feat.faces, dlg.distance(), doc)
                vp.set_preview(res, "new_body")

        if not _exec_with_preview(win, doc, dlg, _preview_offset_face, [feat.target_body_id]):
            return False
        return commit(distance=dlg.distance(), exprs=dlg.get_expressions())

    if t == "honeycomb":
        from omacad.ui.dialogs import HoneycombDialog
        from omacad.model.features.honeycomb import HoneycombFeature
        dlg = HoneycombDialog(win, feat)
        dlg.setWindowTitle(f"Edit {feat.name}")
        base_m = state_before.get(feat.target_body_id)

        def _preview_honeycomb():
            if base_m is not None:
                vp.set_preview(HoneycombFeature.compute(base_m, feat.faces, dlg.params())[0], "new_body")

        if not _exec_with_preview(win, doc, dlg, _preview_honeycomb, [feat.target_body_id]):
            return False
        return commit(**dlg.params(), exprs=dlg.get_expressions())

    if t == "shell":
        from omacad.model.timeline import ShellFeature
        dlg = ShellDialog(doc, win, preselected_body_id=feat.target_body_id)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.spn_thickness.setValue(feat.thickness)
        dlg.spn_thickness2.setValue(getattr(feat, "thickness2", 2.0))
        direction = getattr(feat, "direction", "inside")
        if direction in dlg.DIRS:
            dlg.cmb_dir.setCurrentIndex(dlg.DIRS.index(direction))
        dlg.open_faces = list(feat.open_faces or [])
        n_open = len(dlg.open_faces)
        dlg.lbl_faces.setText(f"{n_open} open face{'s' if n_open != 1 else ''} selected.\n(Click again to deselect)")
        for key, spn in (("thickness", dlg.spn_thickness), ("thickness2", dlg.spn_thickness2)):
            if feat.exprs.get(key):
                spn.set_expression(feat.exprs[key])
        base_m = state_before.get(feat.target_body_id)

        def _preview_shell():
            if base_m is not None:
                res = ShellFeature.shell_body(doc, feat.target_body_id, index, base_m, dlg.spn_thickness.value(),
                                              dlg.direction(), dlg.spn_thickness2.value(), dlg.open_faces)
                vp.set_preview(res if res is not None else base_m, "new_body")

        def _shell_face_picked(plane):
            if getattr(plane, "face", None):
                dlg.toggle_face(plane.face)
                vp.highlighted_faces = [f["_face"] for f in dlg.open_faces if "_face" in f]
                vp.update()

        def _start_shell_pick():
            vp.shell_target_body_id = feat.target_body_id
            vp.begin_plane_pick("shell_face")

        if not _exec_with_preview(win, doc, dlg, _preview_shell, [feat.target_body_id],
                                  wiring=[(vp.shell_face_picked, _shell_face_picked)], start=_start_shell_pick):
            return False
        _, thickness, open_faces = dlg.get_values()
        return commit(thickness=thickness, direction=dlg.direction(),
                                thickness2=dlg.spn_thickness2.value(), open_faces=list(open_faces),
                                exprs=dlg.get_expressions())

    if t == "combine":
        body_names = {}
        for bid in state_before.keys():
            if bid in doc.bodies:
                body_names[bid] = doc.bodies[bid].name
            else:
                creator = next((f for f in doc.timeline.features if f"body_{f.feature_id}" == bid), None)
                body_names[bid] = creator.name if creator is not None else bid
        for bid, b in doc.bodies.items():
            body_names.setdefault(bid, b.name)

        dlg = CombineDialog(doc, win, preselected_target_id=feat.target_body_id,
                            preselected_tool_id=feat.tool_body_id, body_names_override=body_names or None)
        dlg.setWindowTitle(f"Edit {feat.name}")
        op_idx = {"join": 0, "cut": 1, "intersect": 2}.get(feat.operation, 0)
        dlg.cmb_op.setCurrentIndex(op_idx)
        dlg.chk_keep_tool.setChecked(getattr(feat, "keep_tool", False))

        def _preview_combine():
            t_id, tool_id, op, _ = dlg.get_values()
            m_t = state_before.get(t_id or feat.target_body_id)
            m_tool = state_before.get(tool_id or feat.tool_body_id)
            if m_t is not None and m_tool is not None:
                from omacad.model.kernel import CadKernel
                vp.set_preview(CadKernel.boolean_op(m_t, m_tool, op), "new_body")

        if not _exec_with_preview(win, doc, dlg, _preview_combine, [feat.target_body_id]):
            return False
        t_id, tool_id, op, keep = dlg.get_values()
        kwargs = {"operation": op, "keep_tool": keep}
        if t_id and tool_id:
            kwargs["target_body_id"] = t_id
            kwargs["tool_body_id"] = tool_id
        return commit(**kwargs)

    if t == "split_body":
        import numpy as np
        dlg = SplitBodyDialog(doc, win, preselected_body_id=feat.target_body_id,
                              preselected_plane_id=feat.plane_id,
                              body_manifolds_override=state_before if state_before else None)
        dlg.setWindowTitle(f"Edit {feat.name}")

        def _preview_split():
            b_id, p_id = dlg.get_values()
            m = state_before.get(b_id) if state_before else (doc.bodies[b_id].manifold if b_id in doc.bodies else None)
            if m is None or not p_id:
                vp.set_preview(None)
                return
            origin, normal = None, None
            if p_id in doc.construction_planes:
                cp = doc.construction_planes[p_id]
                origin, normal = np.array(cp["origin"], dtype=float), np.array(cp["normal"], dtype=float)
            elif p_id in doc.origin_planes:
                op = doc.origin_planes[p_id]
                origin, normal = np.array(op.origin, dtype=float), np.array(op.normal, dtype=float)
            if origin is None or normal is None:
                vp.set_preview(None)
                return
            norm = float(np.linalg.norm(normal))
            if norm < 1e-9:
                return
            normal = normal / norm
            d = float(np.dot(normal, origin))
            p1 = m.trim_by_plane(normal, d)
            vp.set_preview(p1 if not p1.is_empty() else None, "new_body")

        hide_ids = [feat.target_body_id, f"body_{feat.feature_id}"]
        if not _exec_with_preview(win, doc, dlg, _preview_split, hide_ids):
            return False
        b_id, p_id = dlg.get_values()
        if not b_id or not p_id:
            return False
        po, pn = feat.plane_origin, feat.plane_normal
        if p_id in doc.construction_planes:
            cp = doc.construction_planes[p_id]
            po, pn = list(cp["origin"]), list(cp["normal"])
        elif p_id in doc.origin_planes:
            op = doc.origin_planes[p_id]
            po, pn = list(op.origin), list(op.normal)
        return commit(target_body_id=b_id, plane_id=p_id, plane_origin=po, plane_normal=pn)

    if t == "pattern":
        from omacad.model.timeline import PatternFeature
        dlg = PatternDialog(doc, win, feat)
        dlg.bind_axis_picker(vp)
        dlg.bind_timeline(win.timeline_bar)
        dlg.setWindowTitle(f"Edit {feat.name}")

        def _preview_pattern():
            ids = dlg.source_ids()
            if not ids:
                vp.set_preview(None)
                return
            tmp = PatternFeature("tmp", "tmp", ids, dlg.kind(), **dlg.get_params())
            for bid in list(state_before.keys()) or list(doc.bodies.keys()):
                res = tmp.compute(doc, bid)
                if res is not None:
                    rem, add = res
                    solid, op = (rem, "cut") if rem is not None else (add, "join")
                    extra = add if rem is not None else None
                    vp.set_preview(solid, op, extra=extra, extra_op="join")
                    return
            vp.set_preview(None)

        if not _exec_with_preview(win, doc, dlg, _preview_pattern):
            return False
        return commit(source_ids=dlg.source_ids(), kind=dlg.kind(), exprs=dlg.get_expressions(), **dlg.get_params())

    if t == "move":
        import numpy as np
        dlg = MoveBodyDialog(doc, win, preselected_body_id=feat.target_body_id)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.spn_dx.setValue(feat.dx)
        dlg.spn_dy.setValue(feat.dy)
        dlg.spn_dz.setValue(feat.dz)
        dlg.spn_rx.setValue(feat.rx)
        dlg.spn_ry.setValue(feat.ry)
        dlg.spn_rz.setValue(feat.rz)
        dlg.set_points(feat.from_point, feat.to_point)
        dlg.cmb_pivot.setCurrentIndex(max(0, dlg.cmb_pivot.findData(feat.pivot)))
        dlg.chk_copy_body.setChecked(feat.copy_body)
        for btn in (dlg.btn_points, dlg.btn_f2f, dlg.btn_lay):  # these pick on the body as the step is made
            btn.setEnabled(False)
            btn.setToolTip("Picking works when you make a Move. Here, change the numbers (they hold what was picked).")
        for key, spin in (("dx", dlg.spn_dx), ("dy", dlg.spn_dy), ("dz", dlg.spn_dz),
                          ("rx", dlg.spn_rx), ("ry", dlg.spn_ry), ("rz", dlg.spn_rz)):
            if feat.exprs.get(key):
                spin.set_expression(feat.exprs[key])
        base_m = state_before.get(feat.target_body_id)

        def _preview_move():
            if base_m is None:
                return
            from omacad.model.features.transform import MoveFeature
            _, dx, dy, dz, rx, ry, rz, pivot, _ = dlg.get_values()
            frm, to = (MoveFeature.resolve_point(doc, p) for p in dlg.get_points())
            bb = base_m.bounding_box()
            centre = (np.array(bb[:3]) + np.array(bb[3:])) * 0.5
            piv = np.zeros(3) if pivot == "origin" else (frm if pivot == "point" and frm is not None else centre)
            vp.set_preview(MoveFeature.transform(base_m, (dx, dy, dz), (rx, ry, rz), piv, frm, to), "new_body")

        if not _exec_with_preview(win, doc, dlg, _preview_move, [feat.target_body_id]):
            return False
        bid, dx, dy, dz, rx, ry, rz, pivot, exprs = dlg.get_values()
        frm, to = dlg.get_points()
        return commit(target_body_id=bid, dx=dx, dy=dy, dz=dz, rx=rx, ry=ry, rz=rz, pivot=pivot, exprs=exprs,
                                from_point=frm, to_point=to, copy_body=dlg.chk_copy_body.isChecked())

    if t == "thread":
        from omacad.model.features.thread import ThreadFeature
        dlg = ThreadDialog(doc, win, preselected_body_id=feat.target_body_id)
        dlg.setWindowTitle(f"Edit {feat.name}")
        dlg.spn_dia.setValue(feat.diameter)
        dlg.spn_pitch.setValue(feat.pitch)
        dlg.spn_length.setValue(feat.length)
        dlg.spn_clearance.setValue(feat.clearance)
        prof_idx = dlg.cmb_profile.findData(getattr(feat, "profile", "trapezoidal_45"))
        if prof_idx >= 0:
            dlg.cmb_profile.setCurrentIndex(prof_idx)
        dlg.set_lead_in(feat.taper_lead_in, feat.taper_turns)
        idx_type = 1 if feat.is_female else 0
        dlg.cmb_type.setCurrentIndex(idx_type)
        if getattr(feat, "plane_origin", None) is not None:
            dlg.plane_origin = feat.plane_origin
            dlg.plane_normal = feat.plane_normal
            dlg.plane_u = feat.plane_u
            dlg.plane_v = feat.plane_v
        dlg.set_anchor(getattr(feat, "anchor", "bottom"), getattr(feat, "anchor_gap", 0.0), getattr(feat, "host_length", None))
        for key, spn in (("diameter", dlg.spn_dia), ("pitch", dlg.spn_pitch),
                         ("length", dlg.spn_length), ("clearance", dlg.spn_clearance),
                         ("anchor_gap", dlg.spn_gap)):
            if feat.exprs.get(key):
                spn.set_expression(feat.exprs[key])
        before = state_before.get(feat.target_body_id) if feat.target_body_id else None
        host = feat.measure_host(before) if before is not None and feat.host_length is not None else None
        dlg.set_host(host, feat.follow_host)

        def _preview_thread():
            vals = dlg.get_values()
            tmp = ThreadFeature("tmp", "tmp", **vals)
            solid = tmp.build_solid()
            op = "cut" if vals.get("operation") == "cut" else "new_body"
            vp.set_preview(solid, op)

        hide_ids = [f"body_{feat.feature_id}"] if feat.operation == "new_body" else []
        wiring = _primitive_face_wiring(vp, dlg, "thread_surface", dlg.set_plane) + [
            (vp.cylinder_picked, lambda info: dlg.apply_cylinder_info(info, body_id=info.get("body_id")))]
        if not _exec_with_preview(win, doc, dlg, _preview_thread, hide_ids, wiring=wiring):
            return False
        vals = dlg.get_values()
        return commit(exprs=dlg.get_expressions(), **vals)


    QMessageBox.information(win, "Edit", f"{feat.name} can't be edited here yet.")
    return False


def confirm_delete(win, doc, index: int) -> bool:
    deps = doc.dependents_of(index)
    names = ", ".join(doc.timeline.features[i].name for i in deps)
    text = f"Delete {doc.timeline.features[index].name}?"
    if deps:
        text += f"\n\nThese steps are built on it and will be deleted too:\n{names}"
    return QMessageBox.question(win, "Delete step", text) == QMessageBox.StandardButton.Yes
