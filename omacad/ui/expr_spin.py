"""A QDoubleSpinBox that accepts arithmetic such as 10-1 or 2x(3+5) (see omacad.model.expr).

Typing a letter lists the parameters that start with what is typed so far, under the field: Up/Down step through
it, Enter or Tab puts the name in (without pressing the panel's OK), Esc closes the list. A field whose value
comes from a formula or parameter is tinted, so you can see which values follow the parameters."""

import re

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox, QLineEdit, QListWidget, QAbstractItemView

from omacad.model import expr
from omacad.ui.theme import style

_NAME_BEFORE_CURSOR = re.compile(r"[^\W\d][\w]*$", re.UNICODE)


def matching_parameters(token):
    """(names, all values): the parameters whose name starts with `token`, ignoring case; none for an empty token or
    when the token already is the only match."""
    values = expr.get_variables()
    names = sorted((n for n in values if token and n.lower().startswith(token.lower())), key=str.lower)
    if len(names) == 1 and names[0] == token:
        names = []
    return names, values


def formula_hint(name: str) -> str:
    """The help line under the list: a parameter can be part of a formula, shown with the user's own name."""
    return f"Formulas too: {name}+2 · {name}/2 · 2*{name}"


def name_before(text: str):
    """The parameter name being typed at the end of `text` (None if it does not end in one) and where it starts."""
    m = _NAME_BEFORE_CURSOR.search(text)
    return (m.group(0), m.start()) if m else (None, len(text))


class ParameterList(QListWidget):
    """The suggestion list under a number field. It never takes the focus: the field keeps the keys and steers it."""

    MAX_ROWS = 6

    def __init__(self, parent):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        style(self, """
            QListWidget { background-color: #24282E; border: 1px solid #E26D28; border-radius: 4px; color: #E0E3E7;
                          font-size: 12px; padding: 2px; }
            QListWidget::item { padding: 3px 6px; }
            QListWidget::item:selected { background-color: #E26D28; color: #FFFFFF; }
        """)
        self.hide()

    def show_at(self, top_left: QPoint, width: int, names_values, hint: str = ""):
        """List `names_values` ((name, value) pairs) with its top-left corner at `top_left` in the parent, and a grey
        help line under them (it cannot be chosen; with no names the list is only that line)."""
        from PySide6.QtGui import QColor, QFont
        from PySide6.QtWidgets import QListWidgetItem
        self.clear()
        for name, value in names_values:
            self.addItem(f"{name}   = {value:g}")
            self.item(self.count() - 1).setData(Qt.ItemDataRole.UserRole, name)
        self.choices = len(names_values)
        if hint:
            item = QListWidgetItem(hint)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setForeground(QColor(154, 160, 166))
            font = QFont(self.font())
            font.setItalic(True)
            item.setFont(font)
            self.addItem(item)
        self.setCurrentRow(0 if self.choices else -1)
        rows = min(self.count(), self.MAX_ROWS + (1 if hint else 0))
        widest = max(self.fontMetrics().horizontalAdvance(self.item(i).text()) for i in range(self.count())) + 24
        self.setGeometry(top_left.x(), top_left.y(), max(170, width, widest), rows * (self.sizeHintForRow(0) or 22) + 8)
        self.show()
        self.raise_()

    def has_choices(self) -> bool:
        """Names to pick (not only the help line): then Up/Down/Enter/Tab belong to the list."""
        return self.isVisible() and getattr(self, "choices", 0) > 0

    def step(self, delta: int):
        self.setCurrentRow(max(0, min(self.choices - 1, self.currentRow() + delta)))

    def chosen(self):
        item = self.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None and self.currentRow() < self.choices else None


class ParameterSuggestions:
    """Lists the parameters matching the name typed at the cursor, under the field. Shared by the number fields
    (ExprDoubleSpinBox) and the browser's row editor (ExprLineEdit); `_edit()` is the QLineEdit typed into."""

    _list = None          # ParameterList, made when first needed (it lives in the window, above the panels)
    show_result = False   # also show what a formula evaluates to while it is typed

    def _edit(self):
        return self

    def _suggestion_taken(self):
        """Called after a name was put into the field."""

    def _name_at_cursor(self):
        edit = self._edit()
        text, cur = edit.text(), edit.cursorPosition()
        m = _NAME_BEFORE_CURSOR.search(text[:cur])
        return (m.group(0), m.start(), cur) if m else (None, cur, cur)

    def _result_hint(self):
        text = self._edit().text().strip()
        if not self.show_result or expr.is_plain_number(text) or not expr.is_expression_text(text):
            return ""
        try:
            return f"= {expr.evaluate(text):g}"
        except ValueError:
            return ""

    def suggest(self):
        """Show the parameters starting with the name being typed (case-insensitive), or hide the list."""
        token, _start, _cur = self._name_at_cursor()
        names, values = matching_parameters(token)
        if names:
            hint, pairs = formula_hint(names[0]), [(n, values[n]) for n in names]
        elif token in values:           # a whole name typed: its value, and that it can be part of a formula
            hint, pairs = f"{token} = {values[token]:g} · {formula_hint(token)}", []
            result = self._result_hint()
            if result and self._edit().text().strip() != token:
                hint = result
        elif self._result_hint():
            hint, pairs = self._result_hint(), []
        else:
            self.hide_suggestions()
            return
        window = self._edit().window()
        if self._list is None or self._list.parentWidget() is not window:
            self._list = ParameterList(window)
            self._list.itemClicked.connect(lambda _item: self._take_suggestion())
        edit = self._edit()
        self._list.show_at(edit.mapTo(window, QPoint(0, edit.height() + 2)), edit.width(), pairs, hint)

    def suggestions_visible(self) -> bool:
        """Names are listed to pick from (the help line alone does not take Enter or the arrows)."""
        return self._list is not None and self._list.has_choices()

    def hide_suggestions(self):
        if self._list is not None:
            self._list.hide()

    def _take_suggestion(self):
        name = self._list.chosen() if self._list is not None else None
        self.hide_suggestions()
        if not name:
            return
        token, start, cur = self._name_at_cursor()
        edit = self._edit()
        text = edit.text()
        edit.setText(text[:start] + name + text[cur:])
        edit.setCursorPosition(start + len(name))
        self._suggestion_taken()

    def suggestion_key(self, event) -> bool:
        """Up/Down/Enter/Tab/Esc steer an open list; True when the key was used for it."""
        key = event.key()
        if self.suggestions_visible():
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                self._list.step(-1 if key == Qt.Key.Key_Up else 1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                self._take_suggestion()      # choose the name; the panel's OK waits for the next Enter
                return True
        if key == Qt.Key.Key_Escape and self._list is not None and self._list.isVisible():
            self.hide_suggestions()         # Esc closes the list first
            return True
        return False


class ExprLineEdit(ParameterSuggestions, QLineEdit):
    """The browser's in-row value editor: parameter names are suggested and a formula shows its result."""

    show_result = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self.textEdited.connect(lambda _t: self.suggest())

    def focusOutEvent(self, event):
        self.hide_suggestions()
        super().focusOutEvent(event)

    def hideEvent(self, event):
        self.hide_suggestions()
        super().hideEvent(event)


class ExprDoubleSpinBox(ParameterSuggestions, QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setKeyboardTracking(True)  # live preview once the formula is complete
        self._expr = None  # the formula behind the current value, when it is not a plain number
        self.lineEdit().textEdited.connect(lambda _t: self.suggest())
        self.valueChanged.connect(lambda _v: self._mark_formula())

    def _edit(self):
        return self.lineEdit()

    def _suggestion_taken(self):
        self.interpretText()
        self.setFocus()

    def keyPressEvent(self, event):
        if self.suggestion_key(event):
            return
        super().keyPressEvent(event)

    def focusNextPrevChild(self, nxt):
        if self.suggestions_visible():   # Tab picks the name instead of moving to the next field
            self._take_suggestion()
            return True
        return super().focusNextPrevChild(nxt)

    def focusOutEvent(self, event):
        self.hide_suggestions()
        super().focusOutEvent(event)

    def _mark_formula(self):
        """Tint the field while its value comes from a formula or a parameter."""
        on = self.expression() is not None
        if bool(self.property("formula")) != on:
            self.setProperty("formula", on)
            self.setStyleSheet("ExprDoubleSpinBox[formula=\"true\"] { color: #111111; background-color: #F4C875; }"
                               "ExprDoubleSpinBox[formula=\"true\"] QLineEdit { color: #111111; background-color: #F4C875; }"
                               if on else "")

    def focusInEvent(self, event):
        names = sorted(expr.get_variables())
        base = "Type a value, a parameter name, or a formula with them: radius+2, width/2, 2*(depth-1)."
        self.setToolTip(base + (f"\nParameters: {', '.join(names)}" if names else "\nNo parameters defined yet (Modify > Change Parameters)."))
        super().focusInEvent(event)

    def expression(self):
        """The formula/parameter expression the user entered (None for a plain number)."""
        if self._expr is None:
            return None
        try:
            return self._expr if abs(expr.evaluate(self._expr) - self.value()) < 1e-9 else None
        except ValueError:
            return None

    def set_expression(self, text):
        """Shows `text` (e.g. 'width/2') as the field's content and sets the value it evaluates to."""
        try:
            value = expr.evaluate(text)
        except ValueError:
            return
        self._expr = None if expr.is_plain_number(text) else text.strip()
        self.setValue(value)
        self.lineEdit().setText(self.textFromValue(value) + self.suffix())
        self._mark_formula()

    def textFromValue(self, value):
        e = self.expression() if self._expr is not None else None
        return e if e is not None else super().textFromValue(value)

    def _core(self, text: str) -> str:
        for affix in (self.suffix(), self.prefix()):
            if affix:
                text = text.replace(affix, "")
        return text.strip()

    def valueFromText(self, text):
        core = self._core(text)
        try:
            value = expr.evaluate(core)
        except ValueError:
            return self.value()
        self._expr = None if expr.is_plain_number(core) else core
        return value

    def validate(self, text, pos):
        core = self._core(text)
        if core == "" or not expr.is_expression_text(core):
            state = QValidator.State.Intermediate if core == "" else QValidator.State.Invalid
            return state, text, pos
        try:
            v = expr.evaluate(core)
        except ValueError:
            return QValidator.State.Intermediate, text, pos  # still being typed
        if self.minimum() <= v <= self.maximum():
            return QValidator.State.Acceptable, text, pos
        return QValidator.State.Intermediate, text, pos
