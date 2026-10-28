import glob
import os
import xml.dom.minidom

ICONS = os.path.join(os.path.dirname(__file__), "..", "assets", "icons")


def test_every_icon_svg_is_valid_xml():
    """An SVG with a duplicate attribute fails to render and the ribbon button silently shows no icon."""
    files = glob.glob(os.path.join(ICONS, "*", "*.svg"))
    assert files
    for f in files:
        xml.dom.minidom.parse(f)
