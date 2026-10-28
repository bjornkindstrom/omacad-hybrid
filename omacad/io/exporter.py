"""
Omacad - Import, Export & Project Persistence
Exports 3D solids to STL / OBJ formats and saves/loads .omacad project files.
"""

import json
import os
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional, List, Tuple
import numpy as np
import trimesh
from omacad.model.document import Document, Parameter, default_origin_vis
from omacad.model.timeline import (Body, SketchFeature, BoxFeature, CylinderFeature, PrismFeature, SphereFeature,
                                    ExtrudeFeature, EmbossFeature, RevolveFeature, CombineFeature, FilletFeature,
                                    PatternFeature, SplitBodyFeature, ShellFeature, MoveFeature, ImportMeshFeature, HoleFeature, DeleteBodyFeature, ThreadFeature, OffsetFaceFeature, HoneycombFeature,
                                    ConeFeature, SweepFeature, LoftFeature, PipeFeature)
from omacad import applog
from omacad.model.sketch import Sketch
from omacad.model.timeline import ProfileRefs
from omacad.model import quality
from omacad.io.step_mesh import DECIMALS, clean_for_step, step_str


class Exporter:
    """Handles STL / OBJ export and document persistence."""

    @staticmethod
    def export_body_to_stl(body: Body, filepath: str) -> bool:
        """Exports a single solid body to an STL file."""
        if not body.render_mesh or len(body.render_mesh.vertices) == 0:
            return False

        mesh = body.manifold.to_mesh()
        tm = trimesh.Trimesh(
            vertices=mesh.vert_properties[:, :3],
            faces=mesh.tri_verts,
            process=False
        )
        tm.export(filepath, file_type="stl")
        return True

    @staticmethod
    def export_body_to_obj(body: Body, filepath: str) -> bool:
        """Exports a single solid body to an OBJ file."""
        if not body.render_mesh or len(body.render_mesh.vertices) == 0:
            return False

        mesh = body.manifold.to_mesh()
        tm = trimesh.Trimesh(
            vertices=mesh.vert_properties[:, :3],
            faces=mesh.tri_verts,
            process=False
        )
        tm.export(filepath, file_type="obj")
        return True

    @staticmethod
    def export_all_to_stl(doc: Document, filepath: str) -> bool:
        """Combines all visible bodies and exports to STL."""
        meshes = []
        for b in doc.bodies.values():
            if b.visible and b.render_mesh and len(b.render_mesh.vertices) > 0:
                m = b.manifold.to_mesh()
                tm = trimesh.Trimesh(
                    vertices=m.vert_properties[:, :3],
                    faces=m.tri_verts,
                    process=False
                )
                meshes.append(tm)

        if not meshes:
            return False

        combined = trimesh.util.concatenate(meshes)
        combined.export(filepath, file_type="stl")
        return True

    @staticmethod
    def _mesh_to_step(body_tuples: List[Tuple[str, np.ndarray, np.ndarray]], filepath: str, title: str = "Omacad Model") -> bool:
        """
        Exports triangle meshes as standard ISO 10303-21 AP214 STEP Faceted B-Rep solids.
        body_tuples: list of (body_name, vertices_ndarray, triangles_ndarray)
        """
        lines = []
        lines.append("ISO-10303-21;")
        lines.append("HEADER;")
        lines.append("FILE_DESCRIPTION(('Omacad STEP AP214 Export'),'2;1');")
        lines.append(f"FILE_NAME('{step_str(os.path.basename(filepath))}','2026-10-11T00:00:00',('Omacad User'),('Omacad CAD'),'Omacad','Omacad','');")
        lines.append("FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));")
        lines.append("ENDSEC;")
        lines.append("DATA;")

        idx = 1
        def nid():
            nonlocal idx
            v = idx
            idx += 1
            return v

        id_app_ctx = nid()
        lines.append(f"#{id_app_ctx}=APPLICATION_CONTEXT('core data for automotive mechanical design processes');")
        id_prod_ctx = nid()
        lines.append(f"#{id_prod_ctx}=APPLICATION_PROTOCOL_DEFINITION('draft international standard','automotive_design',1999,#{id_app_ctx});")
        id_mec_ctx = nid()
        lines.append(f"#{id_mec_ctx}=PRODUCT_CONTEXT('',#{id_app_ctx},'mechanical');")

        id_len_unit = nid()
        lines.append(f"#{id_len_unit}=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.));")
        id_plane_angle = nid()
        lines.append(f"#{id_plane_angle}=(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.));")
        id_solid_angle = nid()
        lines.append(f"#{id_solid_angle}=(NAMED_UNIT(*)SI_UNIT($,.STERADIAN.)SOLID_ANGLE_UNIT());")
        id_uncertainty = nid()
        lines.append(f"#{id_uncertainty}=UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),#{id_len_unit},'distance_accuracy_value','confusion accuracy');")
        id_geom_ctx = nid()
        lines.append(f"#{id_geom_ctx}=(GEOMETRIC_REPRESENTATION_CONTEXT(3)GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#{id_uncertainty}))GLOBAL_UNIT_ASSIGNED_CONTEXT((#{id_len_unit},#{id_plane_angle},#{id_solid_angle}))REPRESENTATION_CONTEXT('3D','Omacad Context'));")

        id_orig_pt = nid()
        lines.append(f"#{id_orig_pt}=CARTESIAN_POINT('Origin',(0.,0.,0.));")
        id_axis_z = nid()
        lines.append(f"#{id_axis_z}=DIRECTION('Z',(0.,0.,1.));")
        id_axis_x = nid()
        lines.append(f"#{id_axis_x}=DIRECTION('X',(1.,0.,0.));")
        id_world_axis = nid()
        lines.append(f"#{id_world_axis}=AXIS2_PLACEMENT_3D('World',#{id_orig_pt},#{id_axis_z},#{id_axis_x});")

        solid_brep_ids = []

        for b_name, verts, tris in body_tuples:
            verts, tris = clean_for_step(verts, tris)
            if len(verts) == 0 or len(tris) == 0:
                continue
            pt_ids = []
            for v in verts:
                pid = nid()
                lines.append(f"#{pid}=CARTESIAN_POINT('',({float(v[0]):.{DECIMALS}f},{float(v[1]):.{DECIMALS}f},{float(v[2]):.{DECIMALS}f}));")
                pt_ids.append(pid)

            face_ids = []
            for tri in tris:
                p1, p2, p3 = pt_ids[tri[0]], pt_ids[tri[1]], pt_ids[tri[2]]
                v1, v2, v3 = verts[tri[0]], verts[tri[1]], verts[tri[2]]
                e1 = v2 - v1
                e2 = v3 - v1
                norm = np.cross(e1, e2)
                nlen = np.linalg.norm(norm)
                if nlen > 1e-8:
                    norm = norm / nlen
                else:
                    norm = np.array([0.0, 0.0, 1.0])

                loop_id = nid()
                lines.append(f"#{loop_id}=POLY_LOOP('',(#{p1},#{p2},#{p3}));")
                bound_id = nid()
                lines.append(f"#{bound_id}=FACE_OUTER_BOUND('',#{loop_id},.T.);")

                dir_norm = nid()
                lines.append(f"#{dir_norm}=DIRECTION('',({float(norm[0]):.6f},{float(norm[1]):.6f},{float(norm[2]):.6f}));")
                ref_dir = np.array([1.0, 0.0, 0.0]) if abs(norm[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
                ref_dir = ref_dir - np.dot(ref_dir, norm) * norm
                rlen = np.linalg.norm(ref_dir)
                if rlen > 1e-8:
                    ref_dir = ref_dir / rlen
                dir_ref = nid()
                lines.append(f"#{dir_ref}=DIRECTION('',({float(ref_dir[0]):.6f},{float(ref_dir[1]):.6f},{float(ref_dir[2]):.6f}));")

                plane_placement = nid()
                lines.append(f"#{plane_placement}=AXIS2_PLACEMENT_3D('',#{p1},#{dir_norm},#{dir_ref});")
                plane_id = nid()
                lines.append(f"#{plane_id}=PLANE('',#{plane_placement});")

                face_id = nid()
                lines.append(f"#{face_id}=ADVANCED_FACE('',(#{bound_id}),#{plane_id},.T.);")
                face_ids.append(face_id)

            shell_id = nid()
            faces_str = ",".join(f"#{f}" for f in face_ids)
            lines.append(f"#{shell_id}=CLOSED_SHELL('',({faces_str}));")
            brep_id = nid()
            lines.append(f"#{brep_id}=MANIFOLD_SOLID_BREP('{step_str(b_name)}',#{shell_id});")
            solid_brep_ids.append(brep_id)

        if not solid_brep_ids:
            return False

        title = step_str(title)
        solids_str = ",".join(f"#{b}" for b in solid_brep_ids)
        shape_rep_id = nid()
        lines.append(f"#{shape_rep_id}=ADVANCED_BREP_SHAPE_REPRESENTATION('{title}',({solids_str},#{id_world_axis}),#{id_geom_ctx});")

        prod_id = nid()
        lines.append(f"#{prod_id}=PRODUCT('{title}','{title}','{title}',(#{id_mec_ctx}));")
        prod_def_formation = nid()
        lines.append(f"#{prod_def_formation}=PRODUCT_DEFINITION_FORMATION('','{title}',#{prod_id});")
        prod_def = nid()
        lines.append(f"#{prod_def}=PRODUCT_DEFINITION('design','{title}',#{prod_def_formation},#{id_mec_ctx});")
        prod_shape = nid()
        lines.append(f"#{prod_shape}=PRODUCT_DEFINITION_SHAPE('','{title}',#{prod_def});")
        lines.append(f"#{nid()}=SHAPE_DEFINITION_REPRESENTATION(#{prod_shape},#{shape_rep_id});")

        lines.append("ENDSEC;")
        lines.append("END-ISO-10303-21;\n")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return True

    @staticmethod
    def export_body_to_step(body: Body, filepath: str) -> bool:
        """Exports a single solid body to an ISO 10303-21 STEP (.step / .stp) file."""
        if not body.render_mesh or len(body.render_mesh.vertices) == 0:
            return False
        mesh = body.manifold.to_mesh()
        verts = np.asarray(mesh.vert_properties[:, :3], dtype=float)
        tris = np.asarray(mesh.tri_verts, dtype=int)
        return Exporter._mesh_to_step([(body.name, verts, tris)], filepath, title=body.name)

    @staticmethod
    def export_all_to_step(doc: Document, filepath: str) -> bool:
        """Combines all visible solid bodies and exports to an ISO 10303-21 STEP file."""
        tuples = []
        for b in doc.bodies.values():
            if b.visible and b.render_mesh and len(b.render_mesh.vertices) > 0:
                mesh = b.manifold.to_mesh()
                verts = np.asarray(mesh.vert_properties[:, :3], dtype=float)
                tris = np.asarray(mesh.tri_verts, dtype=int)
                tuples.append((b.name, verts, tris))

        if not tuples:
            return False
        return Exporter._mesh_to_step(tuples, filepath, title=doc.name)

    @staticmethod
    def import_3mf(filepath: str, doc: Document) -> List[Body]:
        """
        Parses a 3D Manufacturing Format (.3mf) package and imports its solid meshes
        into the active Document with parametric timeline history.
        """
        if not zipfile.is_zipfile(filepath):
            raise ValueError(f"File {filepath} is not a valid 3MF ZIP container.")

        with zipfile.ZipFile(filepath, "r") as zf:
            model_names = [n for n in zf.namelist() if n.lower().endswith(".model")]
            if not model_names:
                raise ValueError("No 3D model XML found in 3MF archive.")

            imported_bodies = []
            for mname in model_names:
                tree = ET.fromstring(zf.read(mname))
                ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}

                # Scale per model unit (default mm)
                unit = tree.attrib.get("unit", "millimeter").lower()
                scales = {
                    "millimeter": 1.0, "micron": 0.001, "centimeter": 10.0,
                    "meter": 1000.0, "inch": 25.4, "foot": 304.8
                }
                scale = scales.get(unit, 1.0)

                # Parse objects in resources
                objects_map = {}
                objs = tree.findall(".//m:object", ns) or tree.findall(".//object")
                for obj in objs:
                    oid = obj.attrib.get("id")
                    oname = obj.attrib.get("name") or f"3MF_Object_{oid}"
                    v_nodes = obj.findall(".//m:vertex", ns) or obj.findall(".//vertex")
                    t_nodes = obj.findall(".//m:triangle", ns) or obj.findall(".//triangle")
                    if not v_nodes or not t_nodes:
                        continue

                    verts = np.array([
                        [float(v.attrib.get("x", 0.0)) * scale,
                         float(v.attrib.get("y", 0.0)) * scale,
                         float(v.attrib.get("z", 0.0)) * scale]
                        for v in v_nodes
                    ], dtype=float)

                    tris = np.array([
                        [int(t.attrib.get("v1")), int(t.attrib.get("v2")), int(t.attrib.get("v3"))]
                        for t in t_nodes
                    ], dtype=int)

                    objects_map[oid] = (oname, verts, tris)

                # Check build items with optional affine transforms
                build_items = tree.findall(".//m:build/m:item", ns) or tree.findall(".//build/item")
                if build_items:
                    for item in build_items:
                        oid = item.attrib.get("objectid")
                        if oid not in objects_map:
                            continue
                        oname, verts, tris = objects_map[oid]
                        # Apply transform if present
                        t_str = item.attrib.get("transform")
                        if t_str:
                            try:
                                t_vals = [float(v) for v in t_str.strip().split()]
                                if len(t_vals) == 12:
                                    rot = np.array([
                                        [t_vals[0], t_vals[1], t_vals[2]],
                                        [t_vals[3], t_vals[4], t_vals[5]],
                                        [t_vals[6], t_vals[7], t_vals[8]],
                                    ])
                                    trans = np.array([t_vals[9] * scale, t_vals[10] * scale, t_vals[11] * scale])
                                    verts = verts @ rot + trans     # 3MF uses row vectors: p' = p * M
                            except ValueError as e:
                                applog.log("ERROR", f"3MF {oname}: unreadable transform {t_str!r} ({e}); imported untransformed")

                        feat = doc.import_mesh(oname, verts.tolist(), tris.tolist(), source_file=filepath)
                        body = doc.bodies.get(feat.created_body_id)
                        if body:
                            imported_bodies.append(body)
                else:
                    # No build items: import all resource objects directly
                    for oname, verts, tris in objects_map.values():
                        feat = doc.import_mesh(oname, verts.tolist(), tris.tolist(), source_file=filepath)
                        body = doc.bodies.get(feat.created_body_id)
                        if body:
                            imported_bodies.append(body)

            return imported_bodies

    @staticmethod
    def document_to_dict(doc: Document) -> dict:
        """The whole document as plain data (what a project file holds, plus the replay marker and the sketch being
        edited). Bodies are not part of it: they are rebuilt from the timeline."""
        return {
            "format_version": 2,
            "object_history": doc.object_history.to_dict(),
            "name": doc.name,
            "units": doc.units,
            "parameters": [{"name": q.name, "expr": q.expr, "comment": q.comment} for q in doc.parameters],
            "timeline": [dict(f.to_dict(), exprs=dict(f.exprs), target_body_ids=getattr(f, "target_body_ids", None)) for f in doc.timeline.features],
            "marker_index": doc.timeline.marker_index,
            "sketches": [s.to_dict() for s in doc.sketches.values()],
            "active_sketch": doc.active_sketch.sketch_id if doc.active_sketch is not None else None,
            "construction_planes": doc.construction_planes,
            "sections": doc.sections,
            "origin_vis": doc.origin_vis,
            "body_colors": getattr(doc, "body_colors", {}),
            "canvases": getattr(doc, "canvases", {}),
            "favorites": getattr(doc, "favorites", []),
            "curve_segments": quality.circle_segments(),   # how finely circles were cut when profiles were numbered
        }

    @staticmethod
    def save_project(doc: Document, filepath: str) -> bool:
        """Saves parametric timeline and sketches to an Omacad (.omacad) JSON file."""
        data = Exporter.document_to_dict(doc)
        data.pop("marker_index", None)      # replay position and sketch mode are session state, not file content
        data.pop("active_sketch", None)
        data["object_history"]["markers"] = {}
        # write to a temp file first so an interrupted save never leaves a half-written project
        tmp = f"{filepath}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, filepath)
        return True

    @staticmethod
    def _seed_profile_refs(doc: Document, baseline: int) -> None:
        """Steps from older files point at profiles by number only. The numbers belong to the curve smoothness
        the file was made with, so remember what those profiles look like at that smoothness; they are then found
        again whatever smoothness is set now."""
        needs = [f for f in doc.timeline.features if isinstance(f, ProfileRefs) and f.profile_sigs is None]
        if not needs:
            return
        current = quality.circle_segments()
        if baseline != current:
            quality.set_circle_segments(baseline)
            for sk in doc.sketches.values():
                sk.solve_profiles()
        try:
            for f in needs:
                sketch = doc.sketches.get(f.sketch_id)
                if sketch is not None:
                    f.resolve_profile_refs(sketch)
        finally:
            if baseline != current:
                quality.set_circle_segments(current)
                for sk in doc.sketches.values():
                    sk.solve_profiles()

    @staticmethod
    def load_project(filepath: str) -> Document:
        """Loads an Omacad project from disk."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        doc = Document(data.get("name", "Omacad - Project"))
        Exporter.apply_dict(doc, data)
        return doc

    @staticmethod
    def apply_dict(doc: Document, data: dict) -> None:
        """Replaces the content of `doc` with `data` (a project file or a snapshot), keeping the Document object and its
        listeners, then rebuilds every body."""
        if data.get("format_version", 1) > 2:
            raise ValueError("This project requires a newer version of Omacad")
        positions = {f.get("feature_id"): i for i, f in enumerate(data.get("timeline", []))}
        if len(positions) != len(data.get("timeline", [])):
            raise ValueError("Duplicate feature identifiers in project")
        for fid, dependencies in data.get("object_history", {}).get("dependencies", {}).items():
            for dependency in dependencies:
                if fid not in positions or dependency not in positions or positions[dependency] >= positions[fid]:
                    raise ValueError("Invalid or circular object history dependency")
        doc.object_history.load(data.get("object_history", {}))
        doc.timeline.features.clear()
        doc.timeline.clear_cache()      # new step objects: results a step stores while it runs must be computed again
        doc.timeline.marker_index = 0
        doc.sketches.clear()
        doc.bodies.clear()
        doc.active_sketch = None
        doc.selected_body_ids = []
        doc.selected_profile = None
        doc.selected_extra = []
        doc.name = data.get("name", doc.name)
        doc.units = data.get("units", "mm")
        doc.parameters = [Parameter(q["name"], q["expr"], q.get("comment", "")) for q in data.get("parameters", [])]

        doc.construction_planes = dict(data.get("construction_planes", {}))
        doc.sections = dict(data.get("sections", {}))
        doc.origin_vis = default_origin_vis()
        saved_vis = data.get("origin_vis", {})
        doc.origin_vis["all"] = bool(saved_vis.get("all", True))
        for key in ("axes", "planes"):
            doc.origin_vis[key].update({k: bool(v) for k, v in saved_vis.get(key, {}).items() if k in doc.origin_vis[key]})
        doc.canvases = dict(data.get("canvases", {}))
        doc.body_colors = {k: list(v) for k, v in data.get("body_colors", {}).items()}
        doc.favorites = [{"name": g["name"], "items": [list(r) for r in g.get("items", [])]}
                         for g in data.get("favorites", []) if g.get("name")]

        # Load sketches
        for s_data in data.get("sketches", []):
            sketch = Sketch.from_dict(s_data)
            doc.sketches[sketch.sketch_id] = sketch

        # Load timeline features
        for f_data in data.get("timeline", []):
            ft = f_data.get("feature_type")
            fid = f_data.get("feature_id")
            fname = f_data.get("name")
            if ft == "branch":
                from omacad.model.features.branch import BranchFeature
                feat = BranchFeature(fid, fname, f_data["source_feature_id"], f_data["source_body_id"])
                doc.timeline.add_feature(feat)
            elif ft == "box":
                feat = BoxFeature(
                    fid, fname, f_data["length"], f_data["width"], f_data["height"], f_data["center"],
                    plane_origin=f_data.get("plane_origin"), plane_normal=f_data.get("plane_normal"),
                    plane_u=f_data.get("plane_u"), plane_v=f_data.get("plane_v"),
                    taper_angle=f_data.get("taper_angle", 0.0),
                    wall_thickness=f_data.get("wall_thickness", 0.0),
                    outer_round=f_data.get("outer_round", 0.0),
                    outer_round_kind=f_data.get("outer_round_kind", "fillet"),
                    inner_round=f_data.get("inner_round", 0.0),
                    inner_round_kind=f_data.get("inner_round_kind", "fillet"),
                    translation=f_data.get("translation"),
                )
                doc.timeline.add_feature(feat)
            elif ft == "cylinder":
                feat = CylinderFeature(
                    fid, fname, f_data["radius"], f_data["height"], f_data["center"],
                    plane_origin=f_data.get("plane_origin"), plane_normal=f_data.get("plane_normal"),
                    plane_u=f_data.get("plane_u"), plane_v=f_data.get("plane_v"),
                    taper_angle=f_data.get("taper_angle", 0.0),
                    wall_thickness=f_data.get("wall_thickness", 0.0),
                    outer_round=f_data.get("outer_round", 0.0),
                    outer_round_kind=f_data.get("outer_round_kind", "fillet"),
                    inner_round=f_data.get("inner_round", 0.0),
                    inner_round_kind=f_data.get("inner_round_kind", "fillet"),
                    translation=f_data.get("translation"),
                )
                doc.timeline.add_feature(feat)
            elif ft == "prism":
                feat = PrismFeature(
                    fid, fname, f_data["across_flats"], f_data["height"], f_data["center"], sides=f_data.get("sides", 6),
                    plane_origin=f_data.get("plane_origin"), plane_normal=f_data.get("plane_normal"),
                    plane_u=f_data.get("plane_u"), plane_v=f_data.get("plane_v"),
                    taper_angle=f_data.get("taper_angle", 0.0),
                    wall_thickness=f_data.get("wall_thickness", 0.0),
                    outer_round=f_data.get("outer_round", 0.0),
                    outer_round_kind=f_data.get("outer_round_kind", "fillet"),
                    inner_round=f_data.get("inner_round", 0.0),
                    inner_round_kind=f_data.get("inner_round_kind", "fillet"),
                    translation=f_data.get("translation"),
                )
                doc.timeline.add_feature(feat)
            elif ft == "sphere":
                feat = SphereFeature(fid, fname, f_data["radius"], translation=f_data.get("translation"))
                doc.timeline.add_feature(feat)
            elif ft == "cone":
                feat = ConeFeature(fid, fname, f_data["radius"], f_data["height"], f_data.get("center", False),
                                   top_radius=f_data.get("top_radius", 0.0), wall_thickness=f_data.get("wall_thickness", 0.0),
                                   plane_origin=f_data.get("plane_origin"), plane_normal=f_data.get("plane_normal"),
                                   plane_u=f_data.get("plane_u"), plane_v=f_data.get("plane_v"),
                                   translation=f_data.get("translation"))
                doc.timeline.add_feature(feat)
            elif ft == "sweep":
                feat = SweepFeature(fid, fname, f_data["sketch_id"], f_data["profile_idx"], f_data["path"],
                                    f_data.get("operation", "new_body"), f_data.get("twist", 0.0),
                                    f_data.get("extra_profiles"))
                feat.load_profile_refs(f_data)
                doc.timeline.add_feature(feat)
            elif ft == "pipe":
                feat = PipeFeature(fid, fname, f_data["path"], f_data.get("diameter", 5.0), f_data.get("thickness", 0.0),
                                   f_data.get("operation", "new_body"))
                doc.timeline.add_feature(feat)
            elif ft == "loft":
                feat = LoftFeature(fid, fname, f_data["sections"], f_data.get("operation", "new_body"),
                                 f_data.get("twist", 0.0))
                doc.timeline.add_feature(feat)
            elif ft == "sketch":
                sk = Sketch.from_dict(f_data["sketch"])
                doc.sketches[sk.sketch_id] = sk
                feat = SketchFeature(fid, fname, sk, f_data.get("reference_bodies"))
                doc.timeline.add_feature(feat)
            elif ft == "extrude":
                feat = ExtrudeFeature(
                    fid, fname, f_data["sketch_id"], f_data["profile_idx"], f_data["distance"], f_data["operation"],
                    f_data.get("direction", "one_side"), f_data.get("distance2", 0.0),
                    extra_profiles=f_data.get("extra_profiles", []),
                    extra_refs=f_data.get("extra_refs", []), holes=f_data.get("holes", []),
                    start_offset=f_data.get("start_offset", 0.0), twist=f_data.get("twist", 0.0),
                )
                feat.load_profile_refs(f_data)
                doc.timeline.add_feature(feat)
            elif ft == "emboss":
                feat = EmbossFeature(
                    fid, fname, f_data["sketch_id"], f_data["profile_idx"], f_data.get("depth", 1.0),
                    flip=f_data.get("flip", False), dx=f_data.get("dx", 0.0), dy=f_data.get("dy", 0.0),
                    rotation=f_data.get("rotation", 0.0), wrap=f_data.get("wrap", True),
                    extra_profiles=f_data.get("extra_profiles", []),
                    extra_refs=f_data.get("extra_refs", []))
                feat.load_profile_refs(f_data)
                doc.timeline.add_feature(feat)
            elif ft == "revolve":
                feat = RevolveFeature(fid, fname, f_data["sketch_id"], f_data["profile_idx"],
                                      f_data.get("segments", 96), f_data.get("operation", "new_body"),
                                      axis=f_data.get("axis", ["v"]), angle=f_data.get("angle", 360.0),
                                      direction=f_data.get("direction", "one_side"), angle2=f_data.get("angle2", 0.0),
                                      extra_profiles=f_data.get("extra_profiles", []))
                feat.load_profile_refs(f_data)
                doc.timeline.add_feature(feat)
            elif ft == "delete_body":
                feat = DeleteBodyFeature(fid, fname, f_data["target_body_id"])
                doc.timeline.add_feature(feat)
            elif ft == "hole":
                feat = HoleFeature(fid, fname, f_data.get("points", []),
                                   **{k: f_data[k] for k in ("hole_type", "diameter", "depth", "through", "cb_diameter", "cb_depth",
                                                             "cs_diameter", "cs_angle", "tip", "tip_angle", "chamfer", "chamfer_angle",
                                                             "chamfer_depth") if k in f_data})
                doc.timeline.add_feature(feat)
            elif ft == "fillet":
                feat = FilletFeature(fid, fname, [tuple(e) if e and isinstance(e[0], str) else (e[0], e[1]) for e in f_data["edges"]],
                                     f_data["size"], f_data.get("kind", "fillet"), f_data.get("chamfer_type", "equal"),
                                     f_data.get("size2", 0.0), f_data.get("angle", 45.0), f_data.get("flip", False))
                doc.timeline.add_feature(feat)
            elif ft == "pattern":
                feat = PatternFeature(fid, fname, f_data.get("source_ids", []), f_data.get("kind", "linear"),
                                      **{k: f_data[k] for k in ("axis1", "count1", "spacing1", "axis2", "count2", "spacing2",
                                                                 "mirror_mode", "about", "angle", "rotation_axis", "axis_origin", "axis_direction") if k in f_data})
                doc.timeline.add_feature(feat)
            elif ft == "combine":
                feat = CombineFeature(fid, fname, f_data["target_body_id"], f_data["tool_body_id"],
                                      f_data.get("operation", "join"), keep_tool=f_data.get("keep_tool", False))
                doc.timeline.add_feature(feat)
            elif ft == "split_body":
                feat = SplitBodyFeature(
                    fid, fname, f_data["target_body_id"], f_data["plane_id"],
                    plane_origin=f_data.get("plane_origin"),
                    plane_normal=f_data.get("plane_normal"),
                    new_body_name=f_data.get("new_body_name"),
                    frozen_source=f_data.get("frozen_source"),
                )
                doc.timeline.add_feature(feat)
            elif ft == "shell":
                feat = ShellFeature(
                    fid, fname, f_data["target_body_id"], f_data.get("thickness", 2.0),
                    open_faces=f_data.get("open_faces", []),
                    direction=f_data.get("direction", "inside"), thickness2=f_data.get("thickness2", 2.0),
                )
                doc.timeline.add_feature(feat)
            elif ft == "offset_face":
                feat = OffsetFaceFeature(fid, fname, f_data["target_body_id"], f_data.get("faces", []), f_data.get("distance", 0.2))
                doc.timeline.add_feature(feat)
            elif ft == "honeycomb":
                feat = HoneycombFeature(fid, fname, f_data["target_body_id"], f_data.get("faces", []),
                                        **{k: f_data[k] for k in HoneycombFeature.PARAMS if k in f_data})
                doc.timeline.add_feature(feat)
            elif ft == "move":
                feat = MoveFeature(
                    fid, fname, f_data["target_body_id"],
                    dx=f_data.get("dx", 0.0), dy=f_data.get("dy", 0.0), dz=f_data.get("dz", 0.0),
                    rx=f_data.get("rx", 0.0), ry=f_data.get("ry", 0.0), rz=f_data.get("rz", 0.0),
                    pivot=f_data.get("pivot", "center"),
                    from_point=f_data.get("from_point"), to_point=f_data.get("to_point"),
                    copy_body=f_data.get("copy_body", False),
                )
                doc.timeline.add_feature(feat)
            elif ft == "import_mesh":
                feat = ImportMeshFeature(
                    fid, fname, f_data.get("vertices", []), f_data.get("triangles", []),
                    source_file=f_data.get("source_file", ""),
                    created_body_id=f_data.get("created_body_id"),
                )
                doc.timeline.add_feature(feat)
            elif ft == "thread":
                feat = ThreadFeature.from_dict(f_data)
                doc.timeline.add_feature(feat)
            else:
                continue
            feat.suppressed = f_data.get("suppressed", False)
            feat.exprs = dict(f_data.get("exprs", {}))
            if f_data.get("target_body_ids") is not None:
                feat.target_body_ids = list(f_data["target_body_ids"])

        Exporter._seed_profile_refs(doc, int(data.get("curve_segments", 48)))   # files from before this was saved used 48
        if "marker_index" in data:
            doc.timeline.marker_index = max(0, min(int(data["marker_index"]), len(doc.timeline.features)))
        active = data.get("active_sketch")
        if active and active in doc.sketches:
            doc.active_sketch = doc.sketches[active]
        doc.timeline.recompute(doc)
        doc.notify_changed()
