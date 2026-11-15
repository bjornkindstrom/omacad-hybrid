"""STEP export of a threaded body opens in OpenCASCADE readers (Bambu Studio, FreeCAD).

Report 0.9.3: the thread mesh held vertices at the same spot and slivers flatter than the
6-decimal precision, so the reader built zero-length edges and rejected both solids.
"""
import os
import re
import shutil
import subprocess

import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.io.step_mesh import SLIVER_HEIGHT, WELD_TOL, clean_for_step, remove_slivers, step_str

DATA = os.path.join(os.path.dirname(__file__), "data", "thread_step_export.omacad")


def _mesh(body):
    m = body.manifold.to_mesh()
    return np.asarray(m.vert_properties[:, :3], dtype=float), np.asarray(m.tri_verts, dtype=int)


def _volume(pts, tris):
    a, b, c = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def _heights(pts, tris):
    a, b, c = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    longest = np.max([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1), np.linalg.norm(a - c, axis=1)], axis=0)
    return np.linalg.norm(np.cross(b - a, c - a), axis=1) / longest


@pytest.fixture(scope="module")
def doc():
    return Exporter.load_project(DATA)


def test_report_mesh_has_the_defects(doc):
    verts, _ = _mesh(doc.bodies["body_split_2"])
    assert len(np.unique(verts, axis=0)) < len(verts)  # separate vertices at one spot


def test_cleaned_mesh_is_closed_sliver_free_and_keeps_volume(doc):
    for body in doc.bodies.values():
        pts, tris = clean_for_step(*_mesh(body))
        edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
        _, uses = np.unique(edges, axis=0, return_counts=True)
        assert set(uses) == {2}
        directed = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
        assert len(np.unique(directed, axis=0)) == len(directed)
        assert len(np.unique(pts, axis=0)) == len(pts)
        assert _heights(pts, tris).min() >= SLIVER_HEIGHT
        assert _volume(pts, tris) == pytest.approx(body.manifold.volume(), abs=1e-3)


def test_sliver_is_split_into_its_neighbour():
    # Point 4 lies on the diagonal 0-2: sliver 0-2-4 next to triangle 2-0-3.
    pts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0.5, 0.5, 0]], dtype=float)
    tris = np.array([[0, 2, 4], [2, 0, 3]])
    out = remove_slivers(pts, tris)
    assert sorted(map(tuple, out)) == sorted([(2, 4, 3), (4, 0, 3)])
    assert _heights(pts, out).min() > 0.1


def test_written_points_are_unique_and_names_escaped(doc, tmp_path):
    path = tmp_path / "gänga's.step"
    assert Exporter.export_all_to_step(doc, str(path))
    text = path.read_text(encoding="ascii")  # STEP is ASCII: no raw "ä"
    assert "g\\X2\\00E4\\X0\\nga" in text
    assert "FILE_NAME('g\\X2\\00E4\\X0\\nga''s.step'" in text
    pts = re.findall(r"CARTESIAN_POINT\('',\(([^)]*)\)\)", text)
    assert len(pts) == len(set(pts))
    assert step_str("a'b") == "a''b"


@pytest.mark.skipif(not shutil.which("freecadcmd"), reason="needs FreeCAD (OpenCASCADE STEP reader)")
def test_opencascade_reads_both_solids(doc, tmp_path):
    path = tmp_path / "thread.step"
    Exporter.export_all_to_step(doc, str(path))
    script = tmp_path / "read.py"
    script.write_text(
        "import Part\n"
        f"s = Part.Shape(); s.read({str(path)!r})\n"
        "print('RESULT', len(s.Solids), round(s.Volume, 2), s.isValid())\n"
    )
    out = subprocess.run(["freecadcmd", "-c", f"exec(open({str(script)!r}).read())"],
                         capture_output=True, text=True, timeout=600).stdout
    expected = sum(b.manifold.volume() for b in doc.bodies.values())
    line = next(l for l in out.splitlines() if l.startswith("RESULT"))
    _, solids, volume, valid = line.split()
    assert int(solids) == 2 and valid == "True"
    assert float(volume) == pytest.approx(expected, abs=0.01)
