"""Object history presentation and editing helpers for the browser."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtGui import QColor
from omacad.ui.timeline_bar import FeatureNodeWidget
from omacad.ui import theme
from omacad.model.feature_parameters import parameter_unit, parameter_label


ROLE = Qt.ItemDataRole.UserRole
FEATURE_ROLE = ROLE + 1


# Studio icons tell apart steps that share one emoji in the other icon sets (a chamfer is not a fillet)
_STUDIO_KINDS = {("fillet", "chamfer"): "chamfer", ("pattern", "linear"): "pattern_linear",
                 ("pattern", "circular"): "pattern_circular", ("pattern", "fill"): "pattern_fill",
                 ("pattern", "mirror"): "mirror"}
_STUDIO_TYPES = {"move": "move", "delete_body": "delete", "import_mesh": "import"}


def _feature_studio_icon(feat) -> str:
    """The Studio icon name of a step (by its type and kind), or "" when the Studio icons are not chosen."""
    from omacad.ui.settings import get_settings
    if get_settings().get("icon_theme") != theme.STUDIO_ICONS:
        return ""
    symbol = FeatureNodeWidget.FEATURE_ICONS.get(feat.feature_type, '⚙️')
    return (_STUDIO_KINDS.get((feat.feature_type, getattr(feat, "kind", "")))
            or _STUDIO_TYPES.get(feat.feature_type) or theme.EMOJI_TO_TOOL.get(symbol, ""))

def add_histories(browser, root):
    doc = browser.doc
    history = doc.object_history
    history.sync(doc)
    group = QTreeWidgetItem(root, ['Objects', ''])
    group.setData(0, ROLE, ('group', 'objects'))
    group.setExpanded(True)
    excluded = history.excluded()
    features = {f.feature_id: f for f in doc.timeline.features}
    for oid, obj in history.objects.items():
        if obj.parent_id is None:
            _add_object(browser, group, oid, features, excluded)
    # An unfinished sketch has not yet become a feature.
    sk = doc.active_sketch
    if sk and not any(f.feature_type == 'sketch' and f.sketch.sketch_id == sk.sketch_id for f in features.values()):
        node = QTreeWidgetItem(group, ['✏️ ' + sk.name, ''])
        node.setData(0, ROLE, ('sketch', sk.sketch_id))
        _add_sketch_rows(node, sk)


def _pencil(row):
    """A pencil in the eye column of an editable value row: one click edits it (a double-click on a row that is
    already selected was easy to miss)."""
    row.setIcon(1, theme.named_icon('sketch', '✏️', 18))
    row.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)
    row.setToolTip(1, 'Click to edit the value')


def _add_sketch_rows(node, sketch):
    """A sketch's dimensions (editable) and texts (double-click edits the text)."""
    for dim in sketch.dimensions:
        unit = '°' if dim.dim_type == 'ANGLE' else 'mm'
        row = QTreeWidgetItem(node, [f'{dim.name or dim.dim_type}: {dim.expr or f"{dim.value:g}"} {unit}', ''])
        row.setData(0, ROLE, ('dimension', (sketch.sketch_id, dim.dim_id)))
        row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable)
        row.setToolTip(0, f'{dim.value:g} — double-click or click the pencil to edit')
        _pencil(row)
    from omacad.model.sketch import SketchText
    for entity in sketch.entities:
        if isinstance(entity, SketchText):
            row = QTreeWidgetItem(node, ['🔤 ' + entity.text.replace('\n', ' ')[:24], ''])
            row.setData(0, ROLE, ('sketch_text', f'{sketch.sketch_id}:{entity.entity_id}'))


def _add_object(browser, group, oid, features, excluded):
    """One object's history; objects a Combine used up hang under that Combine as branches."""
    doc = browser.doc
    history = doc.object_history
    obj = history.objects[oid]
    children = history.children(oid)
    label = obj.name
    parent = QTreeWidgetItem(group, [label, ''])
    parent.setData(0, ROLE, ('object', oid))
    parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsEditable)
    parent.setExpanded(True)
    font = parent.font(0)
    font.setBold(oid == history.active_id)
    parent.setFont(0, font)
    parent.setToolTip(0, 'Active object' if oid == history.active_id else 'Click to activate this object')
    browser._style_eye(parent, doc.object_visible(oid))
    if obj.origin_feature_id in features:
        link = QTreeWidgetItem(parent, ["🔗 " + features[obj.origin_feature_id].name, ""])
        link.setData(0, ROLE, ("feature_link", obj.origin_feature_id))
    for fid in obj.feature_ids:
        feat = features[fid]
        studio_icon = _feature_studio_icon(feat)
        if studio_icon:
            node = QTreeWidgetItem(parent, [feat.name, ''])
            node.setIcon(0, theme.named_icon(studio_icon, '⚙️', 22))
        else:
            icon = FeatureNodeWidget.FEATURE_ICONS.get(feat.feature_type, '⚙️')
            node = QTreeWidgetItem(parent, [icon + ' ' + feat.name, ''])
        node.setData(0, ROLE, ('feature', fid))
        node.setData(0, FEATURE_ROLE, fid)
        if feat.feature_type == 'sketch':
            node.setData(0, ROLE, ('sketch', feat.sketch.sketch_id))
            browser._style_eye(node, feat.sketch.visible)
            _add_sketch_rows(node, feat.sketch)
        else:
            node.setFlags(node.flags() | Qt.ItemFlag.ItemIsEditable)
            for key in doc.EDITABLE.get(feat.feature_type, ()):
                value = getattr(feat, key, None)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or key in ('profile_idx', 'segments'):
                    continue
                formula = feat.exprs.get(key)
                shown = f'{formula} = {value:g}' if formula else f'{value:g}'
                row = QTreeWidgetItem(node, [f'{parameter_label(key)}: {shown} {parameter_unit(key)}'.rstrip(), ''])
                row.setData(0, ROLE, ('parameter', (fid, key)))
                row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable)
                row.setToolTip(0, 'Double-click or click the pencil to edit this parameter or expression')
                _pencil(row)
        if feat.error:
            node.setForeground(0, QColor('#e06c75'))
            node.setToolTip(0, feat.error)
        if feat.suppressed or fid in excluded:
            node.setForeground(0, QColor('#858585'))
            node.setToolTip(0, 'Suppressed' if feat.suppressed else 'After history marker / blocked by dependency')
        branches = children.get(fid, [])
        for child in branches:
            _add_object(browser, node, child, features, excluded)
        for dep in history.dependencies.get(fid, []):
            if history.owners.get(dep) not in (oid, *branches) and dep in features:
                link = QTreeWidgetItem(node, ['🔗 ' + features[dep].name, ''])
                link.setData(0, ROLE, ('feature_link', dep))
        if history.markers.get(oid, object()) == fid:
            QTreeWidgetItem(parent, ['● History marker — later steps paused', ''])
    # Current geometry stays separately selectable for export and body tools.
    for bid in obj.body_ids:
        body = doc.bodies.get(bid)
        if body is None:
            continue
        item = QTreeWidgetItem(parent, ['🧊 ' + body.name, ''])
        item.setData(0, ROLE, ('body', bid))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        browser._style_eye(item, body.visible)
        item.setSelected(body.selected)
    if oid not in history.markers:
        end = QTreeWidgetItem(parent, ['● End of history', ''])
        end.setData(0, ROLE, ('history_end', oid))


def find_feature(browser, feature_id):
    for item, _ in browser._walk():
        if item.data(0, FEATURE_ROLE) == feature_id:
            parent = item.parent()
            while parent:
                parent.setExpanded(True)
                parent = parent.parent()
            browser.tree.setCurrentItem(item)
            browser.tree.scrollToItem(item)
            return True
    return False


def edit_parameter(browser, kind, item_id):
    """Open the value editor of a parameter/dimension row. Done on the next event-loop turn and looked up again by
    its id: the click that asked for it may still be finishing (or have rebuilt the tree), which closed an editor
    opened straight away."""
    from PySide6.QtCore import QTimer

    def open_editor():
        tree = browser.tree
        if tree.state() == tree.State.EditingState:
            return
        for item, _ in browser._walk():
            if item.data(0, ROLE) == (kind, item_id):
                tree.setCurrentItem(item)
                tree.scrollToItem(item)
                tree.editItem(item, 0)
                return
    QTimer.singleShot(0, open_editor)


def favorite_row(doc, ref):
    """(label, editor text) of a starred value, or None when what it points at is gone. The label is
    "<step or sketch> · <value name>: <value>" so the editor can start after the ': '."""
    kind, a, b = ref
    if kind == 'parameter':
        pos = doc.object_history.index(doc, a)
        if pos is None:
            return None
        feat = doc.timeline.features[pos]
        value = getattr(feat, b, None)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        formula = feat.exprs.get(b)
        shown = f'{formula} = {value:g}' if formula else f'{value:g}'
        return f'{feat.name} · {parameter_label(b)}: {shown} {parameter_unit(b)}'.rstrip(), formula or str(value)
    sketch = doc.sketches.get(a)
    if sketch is None:
        return None
    if kind == 'dimension':
        dim = next((d for d in sketch.dimensions if d.dim_id == b), None)
        if dim is None:
            return None
        unit = '°' if dim.dim_type == 'ANGLE' else 'mm'
        return f'{sketch.name} · {dim.name or dim.dim_type}: {dim.expr or f"{dim.value:g}"} {unit}', dim.expr or str(dim.value)
    from omacad.model.sketch import SketchText
    ent = next((e for e in sketch.entities if e.entity_id == b), None)
    if not isinstance(ent, SketchText):
        return None
    return f'{sketch.name} · Text: {ent.text}', ent.text


def add_favorites(browser, root):
    """⭐ Favorites: the starred values in their named groups, editable right here (Björn #110)."""
    doc = browser.doc
    if not doc.favorites:
        return
    top = QTreeWidgetItem(root, ['⭐ Favorites', ''])
    top.setData(0, ROLE, ('favorites', ''))
    top.setExpanded(True)
    for group in doc.favorites:
        node = QTreeWidgetItem(top, [group['name'], ''])
        node.setData(0, ROLE, ('fav_group', group['name']))
        node.setFlags(node.flags() | Qt.ItemFlag.ItemIsEditable)
        node.setExpanded(True)
        for ref in group['items']:
            row_text = favorite_row(doc, ref)
            if row_text is None:
                row = QTreeWidgetItem(node, ['(gone) ' + ' '.join(map(str, ref[1:])), ''])
                row.setData(0, ROLE, ('fav_gone', tuple(ref)))
                row.setForeground(0, QColor('#858585'))
                continue
            row = QTreeWidgetItem(node, [row_text[0], ''])
            row.setData(0, ROLE, ('fav', tuple(ref)))
            row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable)
            row.setToolTip(0, 'Double-click or click the pencil to change it')
            _pencil(row)
