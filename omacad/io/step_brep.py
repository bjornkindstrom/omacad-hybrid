"""Exact STEP export (B-rep bodies, step 4). B-rep bodies are written as their OpenCascade shapes (true planes,
cylinders, tori, B-splines); mesh bodies in the same file become polyhedral solids (one flat face per triangle,
cleaned like the mesh-only writer). Names and colours go along (XCAF). Raises on failure: the caller falls back to
the mesh-only writer."""
from __future__ import annotations

import os
from typing import Iterable, Optional, Sequence, Tuple

import numpy as np


def mesh_solid(verts: np.ndarray, tris: np.ndarray):
    """A closed triangle mesh as an OpenCascade solid. Edges are shared by construction (no sewing pass: 16k
    triangles take ~1 s instead of 8)."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeVertex,
                                    BRepBuilderAPI_MakeWire)
    from OCP.TopoDS import TopoDS, TopoDS_Shell, TopoDS_Solid
    from OCP.gp import gp_Pnt
    from omacad.io.step_mesh import clean_for_step
    pts, tris = clean_for_step(np.asarray(verts, dtype=float), np.asarray(tris, dtype=int))
    vertices = [BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, p))).Vertex() for p in pts]
    edges = {}

    def edge(a, b):
        key = (a, b) if a < b else (b, a)
        e = edges.get(key)
        if e is None:
            e = edges[key] = BRepBuilderAPI_MakeEdge(vertices[key[0]], vertices[key[1]]).Edge()
        return e if key == (a, b) else TopoDS.Edge(e.Reversed())

    builder = BRep_Builder()
    shell = TopoDS_Shell()
    builder.MakeShell(shell)
    for a, b, c in tris:
        wire = BRepBuilderAPI_MakeWire(edge(a, b), edge(b, c), edge(c, a)).Wire()
        builder.Add(shell, BRepBuilderAPI_MakeFace(wire, True).Face())
    solid = TopoDS_Solid()
    builder.MakeSolid(solid)
    builder.Add(solid, shell)
    return solid


class _quiet:
    """OpenCascade prints transfer statistics to the terminal on every write; keep only failures."""

    def __enter__(self):
        from OCP.Message import Message, Message_Gravity
        printers = Message.DefaultMessenger_s().Printers()
        self._printers = [printers.Value(i) for i in range(1, printers.Length() + 1)]
        self._levels = [p.GetTraceLevel() for p in self._printers]
        for p in self._printers:
            p.SetTraceLevel(Message_Gravity.Message_Fail)
        return self

    def __exit__(self, *exc):
        for p, level in zip(self._printers, self._levels):
            p.SetTraceLevel(level)
        return False


def _escape_non_ascii(path: str) -> None:
    """OpenCascade writes names as raw UTF-8; strict readers (Bambu Studio) want ISO 10303-21 \\X2\\ escapes, as the
    mesh writer does (step_mesh.step_str). Non-ASCII only occurs inside string literals."""
    with open(path, "r", encoding="utf-8", errors="strict") as f:
        text = f.read()
    if text.isascii():
        return
    from omacad.io.step_mesh import _utf16
    out = "".join(ch if ord(ch) < 127 else "\\X2\\" + "".join(f"{u:04X}" for u in _utf16(ch)) + "\\X0\\"
                  for ch in text)
    with open(path, "w", encoding="ascii") as f:
        f.write(out)


def write(bodies: Iterable[Tuple[str, Sequence[float], Optional[object], Optional[np.ndarray], Optional[np.ndarray]]],
          filepath: str, title: str = "Omacad Model") -> int:
    """bodies = (name, rgba, brep shape or None, verts, tris). Writes atomically; returns the number of exact
    (B-rep) bodies written."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_ColorSurf, XCAFDoc_DocumentTool
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    colours = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    exact = 0
    count = 0
    for name, rgba, shape, verts, tris in bodies:
        if shape is None:
            if verts is None or tris is None or len(tris) == 0:
                continue
            shape = mesh_solid(verts, tris)
        else:
            exact += 1
        label = shapes.AddShape(shape, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(str(name), True))   # UTF-8, not Latin-1
        r, g, b = (float(x) for x in list(rgba)[:3])
        colours.SetColor(label, Quantity_Color(r, g, b, Quantity_TOC_RGB), XCAFDoc_ColorSurf)
        count += 1
    if not count:
        raise ValueError("nothing to export")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    Interface_Static.SetCVal_s("write.step.product.name", str(title))
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    writer.SetColorMode(True)
    temporary = filepath + ".tmp"
    with _quiet():
        if not writer.Transfer(doc, STEPControl_AsIs):
            raise RuntimeError("OpenCascade could not translate the model to STEP")
        if writer.Write(temporary) != IFSelect_RetDone:
            raise RuntimeError("OpenCascade could not write the STEP file")
    _escape_non_ascii(temporary)
    os.replace(temporary, filepath)
    return exact
