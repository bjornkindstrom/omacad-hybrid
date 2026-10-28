"""Edit expressions in the browser row; never open a floating input dialog.

The editor starts after the row's label ("Height: "), so the name of the value stays in sight while it is typed,
and it suggests parameter names and shows what a formula evaluates to (ExprLineEdit)."""
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtWidgets import QLineEdit, QStyledItemDelegate
from omacad.model import expr
from omacad.ui.expr_spin import ExprLineEdit


def label_prefix(text: str) -> str:
    """The part of a value row before the value: 'Height: ' of 'Height: 10 mm'."""
    head, sep, _rest = text.partition(': ')
    return head + sep if sep else ''


def value_ref(data):
    """(kind, ids) of a value row: a parameter or sketch dimension, or a starred one (also "text"); else None."""
    if not data:
        return None
    if data[0] in ('parameter', 'dimension'):
        return data
    if data[0] == 'fav':
        kind, a, b = data[1]
        return kind, (a, b)
    return None


class HistoryDelegate(QStyledItemDelegate):
    def __init__(self, browser):
        super().__init__(browser.tree)
        self.browser = browser
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(180)
        self.preview_timer.timeout.connect(self.update_preview)
        self.preview_value = None
        self.closeEditor.connect(lambda *args: self.clear_preview())

    def clear_preview(self):
        self.preview_timer.stop()
        self.preview_value = None
        self.browser.preview_changed.emit(None)

    def update_preview(self):
        if self.preview_value is None:
            return
        from omacad.model.document import Document
        from omacad.io.exporter import Exporter
        import manifold3d as m3d
        kind, ids, text = self.preview_value
        try:
            preview = Document()
            Exporter.apply_dict(preview, self.browser.doc.snapshot())
            apply_dimension(preview, kind, ids, text)
            if any(f.error for f in preview.timeline.features):
                self.browser.preview_changed.emit(None)
                return
            self.browser.preview_changed.emit({bid: preview.bodies[bid].manifold if bid in preview.bodies else m3d.Manifold()
                                               for bid in self.browser.doc.bodies})
        except (ValueError, TypeError):
            self.browser.preview_changed.emit(None)

    def createEditor(self, parent, option, index):
        ref = value_ref(index.data(Qt.ItemDataRole.UserRole))
        if ref:
            reason = getattr(self.browser, 'busy_reason', lambda: '')()
            if reason:
                self.browser.status_message.emit(reason)
                return None
            if ref[0] == 'text':
                editor = QLineEdit(parent)
                editor.setFrame(False)
                return editor
            expr.set_variables(self.browser.doc.parameter_values())
            editor = ExprLineEdit(parent)
            editor.setFrame(False)
            return editor
        return super().createEditor(parent, option, index)

    def eventFilter(self, editor, event):
        # Qt's delegate filter sees Enter/Tab/Esc before the editor: an open name list takes them first.
        if isinstance(editor, ExprLineEdit) and event.type() == QEvent.Type.KeyPress and editor.suggestion_key(event):
            return True
        return super().eventFilter(editor, event)

    def updateEditorGeometry(self, editor, option, index):
        # Qt places the editor inside the item padding of the stylesheet, which left 17 px: the text was cut off.
        # Give it the whole row from the text to the eye column, never less than its own height.
        super().updateEditorGeometry(editor, option, index)
        rect = editor.geometry()
        height = max(option.rect.height(), editor.sizeHint().height())
        right = max(rect.right(), option.rect.right())
        rect.setTop(option.rect.center().y() - height // 2)
        rect.setHeight(height)
        rect.setRight(right)
        if value_ref(index.data(Qt.ItemDataRole.UserRole)):
            prefix = label_prefix(index.data(Qt.ItemDataRole.DisplayRole) or '')
            if prefix:
                shift = option.fontMetrics.horizontalAdvance(prefix)
                rect.setLeft(rect.left() + shift)
                rect.setRight(max(rect.right(), rect.left() + 60))
        editor.setGeometry(rect)

    def setEditorData(self, editor, index):
        data = index.data(Qt.ItemDataRole.UserRole)
        ref = value_ref(data)
        if ref:
            kind, ids = ref
            doc = self.browser.doc
            if data[0] == 'fav':
                from omacad.ui.object_browser import favorite_row
                row = favorite_row(doc, data[1])
                if row is None:
                    return
                value = row[1]
            elif kind == 'parameter':
                fid, key = ids
                pos = doc.object_history.index(doc, fid)
                if pos is None:
                    return
                feature = doc.timeline.features[pos]
                value = feature.exprs.get(key, str(getattr(feature, key)))
            else:
                sid, did = ids
                sketch = doc.sketches.get(sid)
                dim = next((d for d in sketch.dimensions if d.dim_id == did), None) if sketch else None
                if dim is None:
                    return
                value = dim.expr or str(dim.value)
            editor.setText(value)
            editor.selectAll()
            editor.textChanged.connect(lambda text: self.browser.grow_for_editor(label_prefix(index.data() or '') + text, index))
            def schedule(text):
                self.preview_value = (kind, ids, text)
                self.preview_timer.start()
            editor.textChanged.connect(schedule)
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        ref = value_ref(index.data(Qt.ItemDataRole.UserRole))
        if not ref:
            return super().setModelData(editor, model, index)
        kind, ids = ref
        text = editor.text()
        # Qt must finish closing its editor before a document notification rebuilds the tree.
        QTimer.singleShot(0, lambda: self.apply_value(kind, ids, text))

    def apply_value(self, kind, ids, text):
        doc = self.browser.doc
        try:
            reason = getattr(self.browser, 'busy_reason', lambda: '')()
            if reason:
                raise ValueError(reason)
            apply_dimension(doc, kind, ids, text)
            self.browser.parameter_error = None
        except (ValueError, TypeError) as error:
            self.browser.parameter_error = (kind, tuple(ids), str(error))
            self.browser.status_message.emit(str(error))
        self.browser.refresh_tree()


def apply_dimension(doc, kind, ids, text):
    if kind == 'parameter':
        return doc.edit_feature_dimension(*ids, text)
    if kind == 'text':
        if not doc.set_sketch_text(*ids, text):
            raise ValueError('Type some text')
        return True
    from omacad.model.feature_parameters import normalize_parameter_text
    sid, did = ids
    sketch = doc.sketches.get(sid)
    dim = next((d for d in sketch.dimensions if d.dim_id == did), None) if sketch else None
    if dim is None:
        raise ValueError('The sketch dimension no longer exists')
    text = normalize_parameter_text('angle' if dim.dim_type == 'ANGLE' else 'length', text)
    value = expr.evaluate(text, doc.parameter_values())
    if not doc.update_dimension(*ids, value, None if expr.is_plain_number(text) else text):
        raise ValueError(getattr(doc, 'last_message', '') or 'The sketch cannot satisfy this dimension')
