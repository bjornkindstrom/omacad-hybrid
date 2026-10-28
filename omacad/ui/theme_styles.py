"""Shared QSS stylesheets used by theme styling helpers."""

_MENU_CSS = """
QMenu {
    background-color: #25282C;
    color: #E0E3E7;
    border: 1px solid #3D424A;
    border-radius: 4px;
    padding: 4px 0px;
}
QMenu::item {
    background-color: transparent;
    padding: 6px 28px 6px 10px;
}
QMenu::item:selected {
    background-color: #E26D28;
    color: #FFFFFF;
}
QMenu::item:disabled {
    color: #7B818C;
}
QMenu::separator {
    height: 1px;
    background: #383D45;
    margin: 4px 8px;
}
QMenu::icon { padding-left: 6px; }
QToolTip {
    background-color: #25282C;
    color: #E0E3E7;
    border: 1px solid #4D535E;
    padding: 5px 9px;
    font-size: 12px;
}
"""
_BASE_CSS = """
QMainWindow {
    background-color: #1E2022;
    color: #E0E3E7;
}

QWidget {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "Cantarell", sans-serif;
    font-size: 13px;
    color: #E0E3E7;
}

QGroupBox {
    font-weight: bold;
    border: 1px solid #333842;
    border-radius: 6px;
    margin-top: 22px;
    padding: 10px 8px 8px 8px;
    background-color: #202226;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: #E26D28;
}

/* Menu Bar */
QMenuBar {
    background-color: #1E2022;
    color: #C5CBD3;
    border-bottom: 1px solid #33373E;
    padding: 2px 6px;
}
QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 3px;
}
QMenuBar::item:selected {
    background-color: #2D3136;
    color: #FFFFFF;
}

QMenu {
    background-color: #25282C;
    border: 1px solid #3D424A;
    border-radius: 4px;
    padding: 4px 0px;
}
QMenu::item {
    padding: 6px 24px 6px 16px;
}
QMenu::item:selected {
    background-color: #E26D28;
    color: #FFFFFF;
}
QMenu::separator {
    height: 1px;
    background: #383D45;
    margin: 4px 8px;
}

/* ToolBar & Ribbon */
QToolBar {
    background-color: #25282C;
    border-bottom: 1px solid #353940;
    padding: 4px 6px;
    spacing: 6px;
}
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 8px;
    color: #D2D6DC;
    font-weight: 500;
}
QToolButton:hover {
    background-color: #353A42;
    border: 1px solid #484F5A;
    color: #FFFFFF;
}
QToolButton:pressed, QToolButton:checked {
    background-color: #E26D28;
    border: 1px solid #E26D28;
    color: #FFFFFF;
}

/* Tab Bar (Ribbon workspaces): small muted text on the window's own background, not a band of its own */
QTabWidget::pane {
    border: none;
    background: transparent;
}
QTabBar {
    background: transparent;
}
QTabBar::tab {
    background: transparent;
    color: #7B818C;
    padding: 2px 9px;
    border: none;
    margin-right: 2px;
    font-weight: 500;
    font-size: 10px;
    letter-spacing: 0.5px;
}
QTabBar::tab:selected {
    background: transparent;
    color: #E0E3E7;
    border-bottom: 1px solid #E26D28;
}
QTabBar::tab:hover:!selected {
    background: transparent;
    color: #C4C9D0;
}

/* Dock Widgets & Panels */
QDockWidget {
    background: transparent;
    color: #E0E3E7;
    titlebar-close-icon: url();
    titlebar-normal-icon: url();
}
QDockWidget::title {
    background: transparent;
    padding: 6px 10px;
    border-bottom: 1px solid #33373D;
    font-weight: bold;
    font-size: 11px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    color: #8E95A0;
}

/* Tree Views (Browser Panel) */
QTreeView, QTreeWidget {
    background: transparent;
    border: none;
    color: #D8DCE2;
    outline: none;
    padding: 4px;
}
QTreeView::item {
    padding: 5px 4px;
    border-radius: 3px;
}
QTreeView::item:hover {
    background-color: #2B2F35;
}
QTreeView::item:selected {
    background-color: #383E47;
    color: #FFFFFF;
}
QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {
    border-image: none;
}

/* Tooltips */
QToolTip {
    background-color: #25282C;
    color: #E0E3E7;
    border: 1px solid #4D535E;
    padding: 5px 9px;
    font-size: 12px;
}

/* Buttons */
QPushButton {
    background-color: #33373E;
    color: #E0E3E7;
    border: 1px solid #4D535E;
    border-bottom: 2px solid #25282D;
    border-radius: 5px;
    padding: 5px 14px;
    font-weight: 600;
    font-size: 13px;
    min-height: 16px;
}
QPushButton:hover {
    background-color: #3E434C;
    border-color: #5C6370;
    color: #FFFFFF;
}
QPushButton:pressed {
    background-color: #E26D28;
    border: 1px solid #E26D28;
    border-top: 2px solid #B85317;
    color: #FFFFFF;
    padding-top: 6px;
}
QPushButton#PrimaryButton, QPushButton:default {
    background-color: #E26D28;
    border: 1px solid #FF7E36;
    border-bottom: 2px solid #B85317;
    color: #FFFFFF;
    font-weight: bold;
    padding: 5px 16px;
}
QPushButton#PrimaryButton:hover, QPushButton:default:hover {
    background-color: #FF7E36;
    border-color: #FFA566;
    color: #FFFFFF;
}
QPushButton#PrimaryButton:pressed, QPushButton:default:pressed {
    background-color: #C45B1C;
    border: 1px solid #B85317;
    border-top: 2px solid #8C3A0A;
    color: #FFFFFF;
    padding-top: 6px;
}

QPushButton#SuccessButton {
    background-color: #2E7D32;
    border: 1px solid #388E3C;
    border-bottom: 2px solid #1B5E20;
    color: #FFFFFF;
    font-weight: bold;
    padding: 7px 18px;
}
QPushButton#SuccessButton:hover {
    background-color: #388E3C;
    border-color: #4CAF50;
}
QPushButton#SuccessButton:pressed {
    background-color: #1B5E20;
    border: 1px solid #1B5E20;
    padding-top: 8px;
}

/* Input Fields & Spinners */
QLineEdit, QDoubleSpinBox, QSpinBox {
    background-color: #1A1C1E;
    border: 1px solid #4D535E;
    border-radius: 4px;
    color: #E0E3E7;
    padding: 5px 8px;
    selection-background-color: #E26D28;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #E26D28;
}
QSpinBox, QDoubleSpinBox {
    padding-right: 22px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    background-color: #33373E;
    border-left: 1px solid #555C68;
    border-bottom: 1px solid #555C68;
    border-top-right-radius: 4px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    background-color: #33373E;
    border-left: 1px solid #555C68;
    border-bottom-right-radius: 4px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #555C68;
}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
    background-color: #E26D28;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url(@ARROW_UP@);
    width: 9px;
    height: 9px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url(@ARROW_DOWN@);
    width: 9px;
    height: 9px;
}

/* Dropdown ComboBox: distinct button box with drop-down arrow */
QComboBox {
    background-color: #2D3138;
    border: 1px solid #555C68;
    border-bottom: 2px solid #20242A;
    border-radius: 5px;
    color: #E0E3E7;
    padding: 5px 28px 5px 10px;
    font-weight: 500;
    min-height: 20px;
}
QComboBox:hover {
    background-color: #383D46;
    border-color: #6C7482;
    color: #FFFFFF;
}
QComboBox:focus, QComboBox:on {
    border: 1px solid #E26D28;
    border-bottom: 2px solid #B85317;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid #4D535E;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    background-color: #282C32;
}
QComboBox::drop-down:hover {
    background-color: #3E434C;
}
QComboBox::down-arrow {
    image: url(@ARROW_DOWN@);
    width: 10px;
    height: 10px;
}
QComboBox QAbstractItemView {
    background-color: #25282D;
    border: 1px solid #4D535E;
    border-radius: 4px;
    color: #E0E3E7;
    selection-background-color: #E26D28;
    selection-color: #FFFFFF;
    padding: 4px;
}

/* Sliders */
QSlider::groove:horizontal {
    border: 1px solid #33373E;
    height: 4px;
    background: #1A1C1E;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #E26D28;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #E0E3E7;
    border: 1px solid #33373E;
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #FFFFFF;
    border-color: #E26D28;
}

/* Status Bar */
QStatusBar {
    background-color: #1A1C1E;
    color: #8E95A0;
    border-top: 1px solid #2B2E33;
    font-size: 12px;
    padding: 2px 10px;
}
"""

# Studio (theme files with window/surface/field/border): extra rules after the themed sheets, see theme.studio_sheet.
# White panels on a grey-blue window, calm borderless buttons, blue only for focus, the active tool, selection
# and the primary action; disabled = muted text on the window colour, so state never rests on colour alone.
_STUDIO_CSS = """
QMainWindow { background-color: @window; }
QWidget { font-size: 13px; }
QMenuBar { background-color: @surface; color: @text; border-bottom: 1px solid @border; padding: 3px 8px; }
QMenuBar::item { padding: 5px 10px; border-radius: 6px; }
QMenuBar::item:selected { background-color: @selection; color: @accent; }
QMenu { background-color: @surface; border: 1px solid @border; border-radius: 8px; padding: 6px 0px; }
QMenu::item:selected { background-color: @selection; color: @accent; }
QMenu::separator { background: @border; }
QToolButton { border: 1px solid transparent; border-radius: 6px; color: @text; }
QToolButton:hover { background-color: @field; border: 1px solid transparent; color: @text; }
QToolButton:pressed, QToolButton:checked { background-color: @selection; border: 1px solid transparent; color: @accent; }
QToolButton:disabled { color: @muted; }
QTabBar::tab { color: @muted; font-size: 11px; font-weight: 600; padding: 4px 10px; }
QTabBar::tab:selected { color: @accent; border-bottom: 2px solid @accent; }
QTabBar::tab:hover:!selected { color: @text; }
QTreeView::item:hover { background-color: @field; }
QTreeView::item:selected { background-color: @selection; color: @accent; }
QGroupBox { background-color: @surface; border: 1px solid @border; border-radius: 8px; }
QGroupBox::title { color: @text; }
QPushButton {
    background-color: @field; color: @text; border: 1px solid @border; border-radius: 6px;
    padding: 6px 12px; font-weight: 500; min-height: 18px;
}
QPushButton:hover { background-color: @border; border-color: @border; color: @text; }
QPushButton:pressed { background-color: @selection; border: 1px solid @accent; color: @accent; padding-top: 6px; }
QPushButton:focus { border: 1px solid @accent; }
QPushButton:disabled { background-color: @window; color: @muted; border: 1px dashed @border; }
QPushButton#PrimaryButton, QPushButton:default {
    background-color: @accent; color: @on_accent; border: 1px solid @accent; font-weight: 600; padding: 6px 14px;
}
QPushButton#PrimaryButton:hover, QPushButton:default:hover { background-color: @accent_hover; border-color: @accent_hover; color: @on_accent; }
QPushButton#PrimaryButton:pressed, QPushButton:default:pressed { background-color: @accent_pressed; border: 1px solid @accent_pressed; padding-top: 6px; }
QPushButton#PrimaryButton:disabled, QPushButton:default:disabled { background-color: @border; border-color: @border; color: @muted; }
QDialogButtonBox QPushButton { min-width: 72px; }
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background-color: @field; color: @text; border: 1px solid @border; border-radius: 6px;
    padding: 6px 10px; min-height: 20px; selection-background-color: @accent; selection-color: @on_accent;
}
QSpinBox, QDoubleSpinBox { padding-right: 24px; }
QComboBox { padding-right: 28px; font-weight: 400; }
QLineEdit:hover, QDoubleSpinBox:hover, QSpinBox:hover, QComboBox:hover { border-color: @border_strong; background-color: @field; color: @text; }
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QComboBox:on {
    border: 1px solid @accent; background-color: @surface;
}
QLineEdit:disabled, QDoubleSpinBox:disabled, QSpinBox:disabled, QComboBox:disabled {
    background-color: @window; color: @muted; border: 1px dashed @border;
}
QLineEdit[error="true"], QDoubleSpinBox[error="true"] { border: 2px solid #C62828; }
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: transparent; border: none; border-left: 1px solid @border; width: 20px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background-color: @border; }
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed { background-color: @selection; }
QComboBox::drop-down { background-color: transparent; border: none; width: 24px; }
QComboBox QAbstractItemView {
    background-color: @surface; color: @text; border: 1px solid @border; border-radius: 6px;
    selection-background-color: @selection; selection-color: @accent;
}
QSlider::groove:horizontal { background: @border; border: none; height: 4px; }
QSlider::sub-page:horizontal { background: @accent; }
QSlider::handle:horizontal { background: @surface; border: 2px solid @accent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background: @border; border-radius: 3px; min-height: 24px; min-width: 24px; }
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: @border_strong; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { background: transparent; border: none; width: 0; height: 0; }
QStatusBar { background-color: @surface; color: @muted; border-top: 1px solid @border; }
QToolTip { background-color: @text; color: @surface; border: none; border-radius: 6px; padding: 6px 10px; }
"""
