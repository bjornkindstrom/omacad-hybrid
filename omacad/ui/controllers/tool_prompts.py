"""Compatibility facade for MainWindow tool prompt controllers."""

from omacad.ui.controllers.round_pattern_prompts import RoundPatternPromptsMixin
from omacad.ui.controllers.sketch_scene_prompts import SketchScenePromptsMixin
from omacad.ui.controllers.solid_feature_prompts import SolidFeaturePromptsMixin
from omacad.ui.controllers.primitive_prompts import PrimitivePromptsMixin
from omacad.ui.controllers.body_prompts import BodyPromptsMixin
from omacad.ui.controllers.canvas_prompts import CanvasPromptsMixin
from omacad.ui.controllers.sweep_prompts import SweepPromptsMixin


class ToolPromptsMixin(
    RoundPatternPromptsMixin,
    SketchScenePromptsMixin,
    SolidFeaturePromptsMixin,
    PrimitivePromptsMixin,
    BodyPromptsMixin,
    CanvasPromptsMixin,
    SweepPromptsMixin,
):
    """Stable combined prompt API used by :class:`MainWindow`."""
