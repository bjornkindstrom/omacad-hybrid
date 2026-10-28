"""Text that is painted straight into the 3D view (like the Azimuth/Elevation line), so it takes no room of its own."""


class HudText:
    """Stands in for the QLabel the status line used to be: setText / text / setVisible, drawn by the viewport."""

    def __init__(self, viewport, logged: bool = False, text: str = ""):
        self._viewport = viewport
        self._logged = logged        # everything shown goes into the log that travels with problem reports
        self._text = text
        self._visible = True

    def setText(self, text) -> None:
        text = str(text)
        if self._logged:
            from omacad import applog
            applog.log("status", text)
        if text != self._text:
            self._text = text
            self._viewport.update()

    def text(self) -> str:
        return self._text

    def setVisible(self, visible: bool) -> None:
        if bool(visible) != self._visible:
            self._visible = bool(visible)
            self._viewport.update()

    def isVisible(self) -> bool:
        return self._visible
