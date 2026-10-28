import sys
from types import ModuleType
import numpy as np

from omacad.ui.dialogs import base
from omacad.ui.dialogs.base import (
    BaseFeatureDialog,
    run_docked,
)
from omacad.ui.dialogs.sketch_plane_dlg import (
    SketchPlaneDialog,
    OffsetPlaneDialog,
)
from omacad.ui.dialogs.extrude_dlg import (
    ExtrudeDialog,
)
from omacad.ui.dialogs.revolve_dlg import (
    RevolveDialog,
)
from omacad.ui.dialogs.primitives_dlg import (
    BoxDialog,
    CylinderDialog,
    PrismDialog,
    SphereDialog,
)
from omacad.ui.dialogs.section_dlg import (
    SectionDialog,
)
from omacad.ui.dialogs.boolean_dlg import (
    CombineDialog,
    SplitBodyDialog,
)
from omacad.ui.dialogs.fillet_dlg import (
    RoundEdgesDialog,
)
from omacad.ui.dialogs.pattern_dlg import (
    PatternDialog,
)
from omacad.ui.dialogs.text_dlg import TextDialog
from omacad.ui.dialogs.emboss_dlg import EmbossDialog
from omacad.ui.dialogs.shell_dlg import (
    ShellDialog,
)
from omacad.ui.dialogs.offset_face_dlg import OffsetFaceDialog
from omacad.ui.dialogs.honeycomb_dlg import HoneycombDialog
from omacad.ui.dialogs.jar_dlg import JarDialog
from omacad.ui.dialogs.transform_dlg import (
    MoveBodyDialog,
)
from omacad.ui.dialogs.thread_dlg import (
    ThreadDialog,
)
from omacad.ui.dialogs.hole_dlg import HoleDialog


class _DialogsModule(ModuleType):
    @property
    def SIDE_HOST(self):
        return base.SIDE_HOST

    @SIDE_HOST.setter
    def SIDE_HOST(self, value):
        base.SIDE_HOST = value


sys.modules[__name__].__class__ = _DialogsModule

__all__ = [
    "BaseFeatureDialog",
    "run_docked",
    "SIDE_HOST",
    "SketchPlaneDialog",
    "OffsetPlaneDialog",
    "ExtrudeDialog",
    "RevolveDialog",
    "BoxDialog",
    "CylinderDialog",
    "PrismDialog",
    "SphereDialog",
    "SectionDialog",
    "CombineDialog",
    "SplitBodyDialog",
    "TextDialog",
    "EmbossDialog",
    "RoundEdgesDialog",
    "PatternDialog",
    "ShellDialog",
    "OffsetFaceDialog",
    "HoneycombDialog",
    "JarDialog",
    "MoveBodyDialog",
    "ThreadDialog",
    "HoleDialog",
]
