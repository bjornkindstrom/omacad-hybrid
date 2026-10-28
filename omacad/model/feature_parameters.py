"""Units for scalar feature parameters shared by the tree and its editor."""
import re

COUNTS = {'sides', 'count1', 'count2', 'segments', 'profile_idx'}
ANGLES = {'angle', 'angle2', 'rotation', 'twist', 'taper_angle', 'tip_angle',
          'cs_angle', 'chamfer_angle', 'rx', 'ry', 'rz'}


def parameter_unit(key):
    if key in COUNTS or key in {'taper_turns'}:
        return ''
    return '°' if key in ANGLES else 'mm'


def parameter_label(key):
    return {'chamfer': 'Chamfer width', 'chamfer_depth': 'Max chamfer depth'}.get(
        key, key.replace('_', ' ').capitalize())


def normalize_parameter_text(key, text):
    text = text.strip()
    unit = parameter_unit(key)
    if unit == '°':
        return re.sub(r'\s*(°|deg)\s*$', '', text)
    if unit == 'mm':
        match = re.search(r'\s+(mm|cm|m|in)\s*$', text)
        if match:
            factor = {'mm': 1, 'cm': 10, 'm': 1000, 'in': 25.4}[match.group(1)]
            value = text[:match.start()].strip()
            return value if factor == 1 else f'({value})*{factor}'
    return text
