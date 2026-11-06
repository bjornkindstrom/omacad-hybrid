"""SVG geometry importer and converter for sketches and surface textures.
Parses SVG elements (path, rect, circle, ellipse, line, polyline, polygon)
and converts them into Shapely polygons and Sketch entities.
"""

import math
import re
from typing import List, Optional, Tuple, Union
import xml.etree.ElementTree as ET

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath, QTransform
from shapely.geometry import MultiPolygon, Polygon
from shapely import affinity

from omacad.model.sketch_entities import SketchEntity, SketchLine, SketchSpline
from omacad.model.text_layout import _even_odd

# Qt flattens curves to about half a unit, which is most of a drawing with a 39-unit viewBox: flatten at this many
# units across the drawing's largest side, whatever size its coordinates happen to be.
FLATTEN_UNITS = 1000.0
MIN_LENGTH = 1e-4       # a shorter sketch segment is numerical noise
CELL_CHORD_ERROR = 0.03 # mm a cell's outline may lie from its curves: finer only costs triangles, in every step after it

def _tokenize_svg_path(d_str: str) -> List[str]:
    """Tokenize SVG path string into command characters and numeric strings."""
    pattern = re.compile(r"([a-df-z]|[+-]?(?:\d*\.\d+|\d+)(?:[eE][+-]?\d+)?)", re.IGNORECASE)
    return pattern.findall(d_str)


def arc_to_cubics(x1: float, y1: float, rx: float, ry: float, phi_deg: float, large_arc: bool, sweep: bool,
                  x2: float, y2: float) -> List[Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]]:
    """An SVG arc (endpoint parameterization, non-zero radii, different end points) as cubic Beziers of at most a
    quarter turn each: [(control 1, control 2, end), ...]."""
    phi = math.radians(phi_deg % 360)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    dx = (x1 - x2) / 2.0
    dy = (y1 - y2) / 2.0
    x1_prime = cos_phi * dx + sin_phi * dy
    y1_prime = -sin_phi * dx + cos_phi * dy

    rx = abs(rx)
    ry = abs(ry)
    lambda_rad = (x1_prime**2) / (rx**2) + (y1_prime**2) / (ry**2)
    if lambda_rad > 1.0:
        s = math.sqrt(lambda_rad)
        rx *= s
        ry *= s

    sign = -1.0 if large_arc == sweep else 1.0
    denom = rx**2 * y1_prime**2 + ry**2 * x1_prime**2
    num = rx**2 * ry**2 - rx**2 * y1_prime**2 - ry**2 * x1_prime**2
    sq = max(0.0, num / max(denom, 1e-12))
    coef = sign * math.sqrt(sq)
    cx_prime = coef * ((rx * y1_prime) / ry)
    cy_prime = coef * (-(ry * x1_prime) / rx)

    cx = cos_phi * cx_prime - sin_phi * cy_prime + (x1 + x2) / 2.0
    cy = sin_phi * cx_prime + cos_phi * cy_prime + (y1 + y2) / 2.0

    def angle(u, v):
        dot = u[0] * v[0] + u[1] * v[1]
        len_prod = math.hypot(*u) * math.hypot(*v)
        val = max(-1.0, min(1.0, dot / max(len_prod, 1e-12)))
        ang = math.acos(val)
        if u[0] * v[1] - u[1] * v[0] < 0:
            ang = -ang
        return ang

    v1 = ((x1_prime - cx_prime) / rx, (y1_prime - cy_prime) / ry)
    v2 = ((-x1_prime - cx_prime) / rx, (-y1_prime - cy_prime) / ry)
    theta1 = angle((1.0, 0.0), v1)
    dtheta = angle(v1, v2) % (2.0 * math.pi)
    if not sweep and dtheta > 0:
        dtheta -= 2.0 * math.pi
    elif sweep and dtheta < 0:
        dtheta += 2.0 * math.pi

    def on_ellipse(ux: float, uy: float) -> Tuple[float, float]:
        return (cos_phi * rx * ux - sin_phi * ry * uy + cx, sin_phi * rx * ux + cos_phi * ry * uy + cy)

    pieces = max(1, int(math.ceil(abs(dtheta) / (math.pi / 2.0) - 1e-9)))
    step = dtheta / pieces
    k = 4.0 / 3.0 * math.tan(step / 4.0)
    cubics = []
    for i in range(pieces):
        a0, a1 = theta1 + i * step, theta1 + (i + 1) * step
        cubics.append((on_ellipse(math.cos(a0) - k * math.sin(a0), math.sin(a0) + k * math.cos(a0)),
                       on_ellipse(math.cos(a1) + k * math.sin(a1), math.sin(a1) - k * math.cos(a1)),
                       on_ellipse(math.cos(a1), math.sin(a1))))
    return cubics


def parse_svg_path_to_painter_path(d_str: str) -> QPainterPath:
    """Parse SVG path d string into a QPainterPath."""
    path = QPainterPath()
    tokens = _tokenize_svg_path(d_str)
    if not tokens:
        return path

    idx = 0
    cmd = ""
    cur = QPointF(0.0, 0.0)
    start_subpath = QPointF(0.0, 0.0)
    last_ctrl = QPointF(0.0, 0.0)

    while idx < len(tokens):
        t = tokens[idx]
        if t.isalpha():
            cmd = t
            idx += 1
        is_rel = cmd.islower()
        up_cmd = cmd.upper()

        if up_cmd == "M":
            if idx + 1 >= len(tokens):
                break
            x, y = float(tokens[idx]), float(tokens[idx + 1])
            idx += 2
            p = QPointF(cur.x() + x, cur.y() + y) if is_rel else QPointF(x, y)
            path.moveTo(p)
            cur = p
            start_subpath = p
            last_ctrl = p
            cmd = "l" if is_rel else "L"
        elif up_cmd == "L":
            if idx + 1 >= len(tokens):
                break
            x, y = float(tokens[idx]), float(tokens[idx + 1])
            idx += 2
            p = QPointF(cur.x() + x, cur.y() + y) if is_rel else QPointF(x, y)
            path.lineTo(p)
            cur = p
            last_ctrl = p
        elif up_cmd == "H":
            if idx >= len(tokens):
                break
            x = float(tokens[idx])
            idx += 1
            p = QPointF(cur.x() + x, cur.y()) if is_rel else QPointF(x, cur.y())
            path.lineTo(p)
            cur = p
            last_ctrl = p
        elif up_cmd == "V":
            if idx >= len(tokens):
                break
            y = float(tokens[idx])
            idx += 1
            p = QPointF(cur.x(), cur.y() + y) if is_rel else QPointF(cur.x(), y)
            path.lineTo(p)
            cur = p
            last_ctrl = p
        elif up_cmd == "C":
            if idx + 5 >= len(tokens):
                break
            x1, y1 = float(tokens[idx]), float(tokens[idx + 1])
            x2, y2 = float(tokens[idx + 2]), float(tokens[idx + 3])
            x, y = float(tokens[idx + 4]), float(tokens[idx + 5])
            idx += 6
            c1 = QPointF(cur.x() + x1, cur.y() + y1) if is_rel else QPointF(x1, y1)
            c2 = QPointF(cur.x() + x2, cur.y() + y2) if is_rel else QPointF(x2, y2)
            p = QPointF(cur.x() + x, cur.y() + y) if is_rel else QPointF(x, y)
            path.cubicTo(c1, c2, p)
            last_ctrl = c2
            cur = p
        elif up_cmd == "S":
            if idx + 3 >= len(tokens):
                break
            x2, y2 = float(tokens[idx]), float(tokens[idx + 1])
            x, y = float(tokens[idx + 2]), float(tokens[idx + 3])
            idx += 4
            c1 = QPointF(2.0 * cur.x() - last_ctrl.x(), 2.0 * cur.y() - last_ctrl.y())
            c2 = QPointF(cur.x() + x2, cur.y() + y2) if is_rel else QPointF(x2, y2)
            p = QPointF(cur.x() + x, cur.y() + y) if is_rel else QPointF(x, y)
            path.cubicTo(c1, c2, p)
            last_ctrl = c2
            cur = p
        elif up_cmd == "Q":
            if idx + 3 >= len(tokens):
                break
            x1, y1 = float(tokens[idx]), float(tokens[idx + 1])
            x, y = float(tokens[idx + 2]), float(tokens[idx + 3])
            idx += 4
            c1 = QPointF(cur.x() + x1, cur.y() + y1) if is_rel else QPointF(x1, y1)
            p = QPointF(cur.x() + x, cur.y() + y) if is_rel else QPointF(x, y)
            path.quadTo(c1, p)
            last_ctrl = c1
            cur = p
        elif up_cmd == "T":
            if idx + 1 >= len(tokens):
                break
            x, y = float(tokens[idx]), float(tokens[idx + 1])
            idx += 2
            c1 = QPointF(2.0 * cur.x() - last_ctrl.x(), 2.0 * cur.y() - last_ctrl.y())
            p = QPointF(cur.x() + x, cur.y() + y) if is_rel else QPointF(x, y)
            path.quadTo(c1, p)
            last_ctrl = c1
            cur = p
        elif up_cmd == "A":
            if idx + 6 >= len(tokens):
                break
            rx, ry = float(tokens[idx]), float(tokens[idx + 1])
            phi_deg = float(tokens[idx + 2])
            large_arc = bool(int(tokens[idx + 3]))
            sweep = bool(int(tokens[idx + 4]))
            x, y = float(tokens[idx + 5]), float(tokens[idx + 6])
            idx += 7
            x2 = cur.x() + x if is_rel else x
            y2 = cur.y() + y if is_rel else y
            if abs(rx) < 1e-9 or abs(ry) < 1e-9 or (x2 == cur.x() and y2 == cur.y()):
                path.lineTo(x2, y2)
            else:
                for c1, c2, end in arc_to_cubics(cur.x(), cur.y(), rx, ry, phi_deg, large_arc, sweep, x2, y2):
                    path.cubicTo(*c1, *c2, *end)
            cur = QPointF(x2, y2)
            last_ctrl = cur
        elif up_cmd == "Z":
            path.closeSubpath()
            cur = start_subpath
            last_ctrl = cur
        else:
            idx += 1

    return path


def _parse_svg_points(pts_str: str) -> List[Tuple[float, float]]:
    coords = [float(v) for v in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][+-]?\d+)?", pts_str)]
    return [(coords[i], coords[i + 1]) for i in range(0, len(coords) - 1, 2)]


def _svg_painter_path(svg_content_or_path: str) -> Optional[QPainterPath]:
    """Every shape of an SVG file or XML string as one QPainterPath with its real curves (Y down, as in the file)."""
    try:
        if "<svg" in svg_content_or_path:
            root = ET.fromstring(svg_content_or_path)
        else:
            root = ET.parse(svg_content_or_path).getroot()
    except (ET.ParseError, OSError):
        return None

    combined_path = QPainterPath()

    # Strip XML namespace if present
    for elem in root.iter():
        tag = elem.tag.split("}")[-1].lower() if "}" in elem.tag else elem.tag.lower()
        if tag == "path":
            d = elem.attrib.get("d", "").strip()
            if d:
                combined_path.addPath(parse_svg_path_to_painter_path(d))
        elif tag == "rect":
            x = float(elem.attrib.get("x", 0.0))
            y = float(elem.attrib.get("y", 0.0))
            w = float(elem.attrib.get("width", 0.0))
            h = float(elem.attrib.get("height", 0.0))
            if w > 0 and h > 0:
                combined_path.addRect(x, y, w, h)
        elif tag == "circle":
            cx = float(elem.attrib.get("cx", 0.0))
            cy = float(elem.attrib.get("cy", 0.0))
            r = float(elem.attrib.get("r", 0.0))
            if r > 0:
                combined_path.addEllipse(QPointF(cx, cy), r, r)
        elif tag == "ellipse":
            cx = float(elem.attrib.get("cx", 0.0))
            cy = float(elem.attrib.get("cy", 0.0))
            rx = float(elem.attrib.get("rx", 0.0))
            ry = float(elem.attrib.get("ry", 0.0))
            if rx > 0 and ry > 0:
                combined_path.addEllipse(QPointF(cx, cy), rx, ry)
        elif tag in ("polygon", "polyline"):
            pts_str = elem.attrib.get("points", "")
            pts = _parse_svg_points(pts_str)
            if len(pts) >= 2:
                p = QPainterPath()
                p.moveTo(pts[0][0], pts[0][1])
                for pt in pts[1:]:
                    p.lineTo(pt[0], pt[1])
                if tag == "polygon":
                    p.closeSubpath()
                combined_path.addPath(p)
        elif tag == "line":
            x1 = float(elem.attrib.get("x1", 0.0))
            y1 = float(elem.attrib.get("y1", 0.0))
            x2 = float(elem.attrib.get("x2", 0.0))
            y2 = float(elem.attrib.get("y2", 0.0))
            p = QPainterPath()
            p.moveTo(x1, y1)
            p.lineTo(x2, y2)
            combined_path.addPath(p)

    return combined_path


def parse_svg_to_geometry(svg_content_or_path: str) -> Optional[Union[Polygon, MultiPolygon]]:
    """Parse an SVG file or XML string into a Shapely geometry (Polygon or MultiPolygon, Y up)."""
    path = _svg_painter_path(svg_content_or_path)
    if path is None or path.isEmpty():
        return None
    bounds = path.boundingRect()
    size = max(bounds.width(), bounds.height())
    if size <= 0.0:
        return None
    zoom = FLATTEN_UNITS / size
    geom = _even_odd(QTransform.fromScale(zoom, zoom).map(path))
    return None if geom is None else affinity.scale(geom, xfact=1.0 / zoom, yfact=1.0 / zoom, origin=(0.0, 0.0))


def svg_to_template(geom: Union[Polygon, MultiPolygon], target_size: float) -> Tuple[List[Polygon], Tuple[float, float]]:
    """Normalize a Shapely geometry to target_size (max width/height = target_size) centered at (0, 0).
    Returns ([polygons], (width, height))."""
    if geom is None or geom.is_empty:
        # Default placeholder square
        h = target_size / 2.0
        return [Polygon([(-h, -h), (h, -h), (h, h), (-h, h)])], (target_size, target_size)

    minx, miny, maxx, maxy = geom.bounds
    w = max(maxx - minx, 1e-6)
    h = max(maxy - miny, 1e-6)
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0

    scale = target_size / max(w, h)
    scaled = affinity.scale(geom, xfact=scale, yfact=scale, origin=(cx, cy))
    centered = affinity.translate(scaled, xoff=-cx, yoff=-cy).simplify(CELL_CHORD_ERROR)

    polys = []
    if isinstance(centered, Polygon):
        polys.append(centered)
    elif isinstance(centered, MultiPolygon):
        polys.extend(centered.geoms)

    return polys, (w * scale, h * scale)


def _subpaths(path: QPainterPath) -> List[List[Tuple]]:
    """The path's subpaths in file coordinates, each [start, segment, ...]: a segment is (end,) for a straight line
    and (control 1, control 2, end) for a cubic Bezier."""
    subpaths: List[List[Tuple]] = []
    i = 0
    while i < path.elementCount():
        element = path.elementAt(i)
        point = (element.x, element.y)
        if element.isMoveTo():
            subpaths.append([point])
            i += 1
        elif element.isLineTo():
            subpaths[-1].append((point,))
            i += 1
        else:
            c2, end = path.elementAt(i + 1), path.elementAt(i + 2)
            subpaths[-1].append((point, (c2.x, c2.y), (end.x, end.y)))
            i += 3
    return subpaths


def parse_svg_to_sketch_entities(svg_content_or_path: str, origin: Tuple[float, float] = (0.0, 0.0),
                                 scale: float = 1.0, is_construction: bool = False) -> List[SketchEntity]:
    """Parse SVG into sketch entities that keep its shape exactly: a SketchLine per straight segment and a two-point
    SketchSpline per Bezier (Hermite tangents 3(c1 - p0) and 3(p3 - c2) give the same cubic)."""
    path = _svg_painter_path(svg_content_or_path)
    if path is None:
        return []

    def place(p):
        return (p[0] * scale + origin[0], -p[1] * scale + origin[1])

    entities: List[SketchEntity] = []
    for subpath in _subpaths(path):
        segments = subpath[1:]
        # SVG fills an open subpath as if it were closed: that is its outline, unless it is a single straight line
        if len(segments) > 1 or (segments and len(segments[0]) == 3):
            segments = segments + [(subpath[0],)]
        current = place(subpath[0])
        for segment in segments:
            end = place(segment[-1])
            if len(segment) == 1:
                if math.dist(current, end) > MIN_LENGTH:
                    entities.append(SketchLine(f"svg_l_{len(entities) + 1}", current, end, is_construction=is_construction))
                    current = end
                continue
            c1, c2 = place(segment[0]), place(segment[1])
            tangents = {0: (3.0 * (c1[0] - current[0]), 3.0 * (c1[1] - current[1])),
                        1: (3.0 * (end[0] - c2[0]), 3.0 * (end[1] - c2[1]))}
            entities.append(SketchSpline(f"svg_s_{len(entities) + 1}", [current, end], is_construction=is_construction,
                                         tangents=tangents))
            current = end
    return entities
