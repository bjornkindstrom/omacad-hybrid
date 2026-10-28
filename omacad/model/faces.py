"""Compatibility exports for CAD mesh surface and edge analysis."""

from omacad.model.faces_types import PlanarFace, PlanarEdge, CircularEdge, LoopEdge
from omacad.model.faces_topology import SLIVER_AREA, _group_min_width, _coplanar, _sliver_roots, _curved_roots
from omacad.model.faces_edges import (
    tangent_chain, _loop_edges, compute_planar_edges, _planar_edges_from, _edge_from,
    _circular_edges, _join_arcs, _join_arc_group
)
from omacad.model.faces_refs import match_edge, edge_from_ref, fuzzy_edge_from_ref
from omacad.model.faces_hit_tests import (
    _ray_triangles, ray_hit_face, ray_hit_faces, in_plane_edges, ray_mesh_hit,
    smooth_patch_vertices, detect_cylinder_surface, _FACE_STACKS
)
from omacad.model.faces_surfaces import (
    compute_planar_faces, clear_topology_cache, compute_planar_faces_and_edges,
    _TOPOLOGY_CACHE, _TOPOLOGY_CACHE_MAX
)

__all__ = [
    "PlanarFace", "PlanarEdge", "CircularEdge", "LoopEdge",
    "compute_planar_faces", "compute_planar_faces_and_edges", "clear_topology_cache",
    "compute_planar_edges", "match_edge", "edge_from_ref", "fuzzy_edge_from_ref",
    "ray_hit_face", "ray_hit_faces", "in_plane_edges", "tangent_chain",
    "ray_mesh_hit", "smooth_patch_vertices", "detect_cylinder_surface",
]
