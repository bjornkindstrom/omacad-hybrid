"""Omacad viewport package: re-exports Viewport3D and components for backward compatibility."""

from PySide6.QtWidgets import QMenu
from omacad.ui.viewport.viewport import Viewport3D
from omacad.ui.math3d import ray_from_screen
from omacad.ui.viewport.shaders import (
    VERTEX_SHADER_SOLID,
    FRAGMENT_SHADER_SOLID,
    VERTEX_SHADER_FLAT,
    FRAGMENT_SHADER_FLAT,
    VERTEX_SHADER_TEXTURE,
    FRAGMENT_SHADER_TEXTURE,
    VERTEX_SHADER_THICK,
    SKETCH_GROUP_ICONS,
)

__all__ = [
    "Viewport3D",
    "VERTEX_SHADER_SOLID",
    "FRAGMENT_SHADER_SOLID",
    "VERTEX_SHADER_FLAT",
    "FRAGMENT_SHADER_FLAT",
    "VERTEX_SHADER_TEXTURE",
    "FRAGMENT_SHADER_TEXTURE",
    "VERTEX_SHADER_THICK",
    "SKETCH_GROUP_ICONS",
]
