"""Rapport 20261025-094103: a cut sketched on the hexagon's face, made while Cylinder 1 was the active object in the
browser, was aimed at the cylinder, missed it, was stored cutting nothing and showed up as its own object."""
import json
import os

from omacad.io.exporter import Exporter
from omacad.model.document import Document

DATA = os.path.join(os.path.dirname(__file__), 'data', 'hexagon_face_cut_other_object_active.omacad')


def test_cut_on_hexagon_face_belongs_to_hexagon_although_cylinder_is_active():
    doc = Document()
    with open(DATA, encoding='utf-8') as f:
        Exporter.apply_dict(doc, json.load(f))
    history = doc.object_history
    history.sync(doc)
    history.target_object_id = history.active_id = 'object_cylinder_1'
    hexagon = doc.bodies['body_prism_8'].manifold.volume()
    profile_area = 166.2768   # the sketched hexagon (same as the profile signature)

    doc.extrude_profile('sketch_2', 1, -25.0, 'cut')

    feat = doc.timeline.features[-1]
    assert feat.target_body_ids == ['body_prism_8']
    assert abs(doc.bodies['body_prism_8'].manifold.volume() - (hexagon - 25.0 * profile_area)) < 0.5
    assert history.owners[feat.feature_id] == 'object_prism_8'
    assert feat.feature_id in history.objects['object_prism_8'].feature_ids
