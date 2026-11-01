"""A linked object starts from one explicit historical body result."""
from omacad.model.features.base import Feature, Body


def beside_offset(solid):
    """How far right (+X) a copy goes so it sits next to the original, not inside it: its width plus a gap."""
    lo_x, _, _, hi_x, _, _ = solid.bounding_box()
    width = max(hi_x - lo_x, 0.0)
    return width + max(5.0, 0.5 * width)


def free_offset(solid, others):
    """Like `beside_offset`, but further right past any body (`others`, solids) the copy would touch there, so an
    independent copy never lands on the original or on an earlier copy."""
    lo_x, lo_y, lo_z, hi_x, hi_y, hi_z = solid.bounding_box()
    gap = max(5.0, 0.5 * max(hi_x - lo_x, 0.0))
    boxes = [o.bounding_box() for o in others]
    dx = beside_offset(solid)
    moved = True
    while moved:
        moved = False
        for b in boxes:
            if (b[0] < hi_x + dx + gap and lo_x + dx - gap < b[3] and b[1] < hi_y and lo_y < b[4]
                    and b[2] < hi_z and lo_z < b[5]):
                dx = b[3] + gap - lo_x
                moved = True
    return dx


class BranchFeature(Feature):
    def __init__(self, feature_id, name, source_feature_id, source_body_id, follow=True, beside=False):
        super().__init__(feature_id, 'branch', name)
        self.source_feature_id = source_feature_id
        self.source_body_id = source_body_id
        # True: copies the original's latest result (Timeline._place_linked_objects keeps the link after the
        # original's steps). False: frozen at the source step. None: decided on the first rebuild (older files).
        self.follow = follow
        # the copy is placed to the right of the original (follows its width when the original grows)
        self.beside = beside

    def execute(self, doc):
        index = doc.object_history.index(doc, self.source_feature_id)
        if index is None:
            raise ValueError('The branch source step is missing')
        if self in doc.timeline.features and index >= doc.timeline.features.index(self):
            raise ValueError('A branch must follow its source step')
        solid = None
        if self.follow and self.source_body_id in doc.bodies:
            solid = doc.bodies[self.source_body_id].manifold
        if solid is None:
            solid = doc.step_states.get(index + 1, {}).get(self.source_body_id)
        if solid is None:
            raise ValueError('The source step has no body result')
        if self.beside:
            solid = solid.translate((beside_offset(solid), 0.0, 0.0))
        body = Body('body_' + self.feature_id, self.name, solid)
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    def to_dict(self):
        return dict(feature_type=self.feature_type, feature_id=self.feature_id,
                    name=self.name, suppressed=self.suppressed,
                    source_feature_id=self.source_feature_id, source_body_id=self.source_body_id,
                    follow=self.follow, beside=self.beside)
