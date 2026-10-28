"""A linked object starts from one explicit historical body result."""
from omacad.model.features.base import Feature, Body


class BranchFeature(Feature):
    def __init__(self, feature_id, name, source_feature_id, source_body_id):
        super().__init__(feature_id, 'branch', name)
        self.source_feature_id = source_feature_id
        self.source_body_id = source_body_id

    def execute(self, doc):
        index = doc.object_history.index(doc, self.source_feature_id)
        if index is None:
            raise ValueError('The branch source step is missing')
        if self in doc.timeline.features and index >= doc.timeline.features.index(self):
            raise ValueError('A branch must follow its source step')
        solid = doc.step_states.get(index + 1, {}).get(self.source_body_id)
        if solid is None:
            raise ValueError('The source step has no body result')
        body = Body('body_' + self.feature_id, self.name, solid)
        body.update_render_mesh()
        doc.bodies[body.body_id] = body

    def to_dict(self):
        return dict(feature_type=self.feature_type, feature_id=self.feature_id,
                    name=self.name, suppressed=self.suppressed,
                    source_feature_id=self.source_feature_id, source_body_id=self.source_body_id)
