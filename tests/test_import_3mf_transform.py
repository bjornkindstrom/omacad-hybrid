"""3MF build items carry a transform in row-vector form (p' = p * M); a rotated item must come in rotated the right way."""
import zipfile

import numpy as np
import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document

MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
 <resources><object id="1" name="Wedge" type="model"><mesh>
  <vertices>
   <vertex x="0" y="0" z="0"/><vertex x="10" y="0" z="0"/><vertex x="0" y="2" z="0"/><vertex x="0" y="0" z="3"/>
  </vertices>
  <triangles>
   <triangle v1="0" v2="2" v3="1"/><triangle v1="0" v2="1" v3="3"/><triangle v1="0" v2="3" v3="2"/><triangle v1="1" v2="2" v3="3"/>
  </triangles>
 </mesh></object></resources>
 <build><item objectid="1" transform="0 1 0 -1 0 0 0 0 1 100 0 0"/></build>
</model>"""


def test_rotated_build_item_is_rotated_the_3mf_way(tmp_path):
    path = tmp_path / "wedge.3mf"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("3D/3dmodel.model", MODEL)
    doc = Document()
    Exporter.import_3mf(str(path), doc)
    body = next(iter(doc.bodies.values()))
    lo, hi = np.array(body.manifold.bounding_box()[:3]), np.array(body.manifold.bounding_box()[3:])
    # x' = x*m00 + y*m10 + m30 = 100 - y,  y' = x*m01 + y*m11 = x: the 10 mm leg now runs along +Y
    assert lo == pytest.approx([98.0, 0.0, 0.0]) and hi == pytest.approx([100.0, 10.0, 3.0])
