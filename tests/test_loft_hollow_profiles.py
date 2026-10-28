from pathlib import Path

import pytest

from omacad.io.exporter import Exporter
from omacad.model.document import Document


def test_report_preserves_openings_at_both_ends():
    doc = Exporter.load_project(str(Path(__file__).parent / 'data/loft_hollow_profiles.omacad'))
    feat = doc.timeline.features[-1]
    body = next(iter(doc.bodies.values())).manifold
    assert body.genus() == 1
    assert body.volume() < 150000  # filled version was 369140 mm³
    for sid, idx, sig in feat.sections:
        from omacad.model.features.base import find_profile
        sketch = doc.sketches[sid]
        profile = sketch.profiles[find_profile(sketch, idx, sig)]
        z = sketch.plane.origin[2]
        cut = body.slice(z + (0.0001 if z == 0 else -0.0001))
        assert cut.area() == pytest.approx(profile.area, rel=0.003)


def hollow_three_sections():
    doc = Document()
    profiles = []
    for z, half in ((0, 20), (10, 15), (30, 25)):
        plane = doc.construction_plane(doc.add_construction_plane(doc.origin_planes['XY'], z, origin=(0, 0, 0)))
        s = doc.start_sketch_on_plane(plane)
        s.add_rect((-half, -half), (half, half))
        s.add_rect((-half + 5, -half + 5), (half - 5, half - 5))
        doc.finish_sketch()
        profiles.append((s.sketch_id, next(i for i, p in enumerate(s.profiles) if p.interior_holes)))
    return doc, profiles


def test_three_sections_keep_five_mm_walls_and_roundtrip(tmp_path):
    doc, profiles = hollow_three_sections()
    doc.add_loft(profiles)
    body = next(iter(doc.bodies.values())).manifold
    # A square frame's area is 40*h - 100, linear between sections.
    assert body.volume() == pytest.approx(10 * (700 + 500) / 2 + 20 * (500 + 900) / 2, abs=0.01)
    assert body.genus() == 1
    p = tmp_path / 'loft.omacad'
    Exporter.save_project(doc, str(p))
    again = Exporter.load_project(str(p))
    assert next(iter(again.bodies.values())).manifold.volume() == pytest.approx(body.volume())


def test_mismatched_holes_are_reported():
    from omacad.model.features.sweep import LoftFeature
    doc, profiles = hollow_three_sections()
    sid, _ = profiles[-1]
    profiles[-1] = (sid, next(i for i, p in enumerate(doc.sketches[sid].profiles) if not p.interior_holes))
    feat = LoftFeature('test', 'Test', [LoftFeature.section_ref(doc, *p) for p in profiles])
    with pytest.raises(ValueError, match='same number of holes'):
        feat.build_solid(doc)
