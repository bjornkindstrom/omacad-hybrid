"""Render three fan-menu label proposals using Hybrid's real FanMenu painter."""
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from omacad.ui.fan_menu import FanItem, FanMenu
import omacad.ui.fan_menu as fan_menu_module


OUT = Path(__file__).parent
APP = QApplication([])
viewport = QWidget()
viewport.resize(1000, 760)
categories = [FanItem('create', 'Create', children=[FanItem(x.lower().replace(' ', '_'), x) for x in
              ('Sketch', 'Extrude', 'Hole', 'Revolve', 'Pattern', 'Fillet', 'Shell')])]
categories += [FanItem(x.lower(), x) for x in ('Modify', 'Inspect', 'View', 'History', 'Context')]
pages = []
for style, title in (('curved', 'A · Böjd text som nu'),
                     ('readable_curved', 'B · Läsbar böjd text i nedre bågen'),
                     ('horizontal', 'C · Horisontell text')):
    fan_menu_module.get_settings = lambda: SimpleNamespace(get=lambda *_: style)
    menu = FanMenu(viewport)
    menu.popup(QPoint(500, 390), categories, hub_center=FanItem('cancel', 'Cancel'))
    image = QImage(1000, 760, QImage.Format.Format_RGB32)
    image.fill(QColor('#1c2530'))
    painter = QPainter(image)
    painter.setPen(QColor('#34465b'))
    for x in range(50, 1000, 50): painter.drawLine(x, 60, x, 750)
    for y in range(60, 760, 50): painter.drawLine(50, y, 950, y)
    menu.draw(painter, 1000, 760)
    painter.setPen(QColor('#ffffff'))
    font = QFont('Sans Serif')
    font.setPixelSize(22)
    painter.setFont(font)
    painter.drawText(QRectF(25, 10, 950, 40), Qt.AlignmentFlag.AlignLeft, title)
    painter.end()
    path = OUT / f'forslag-{len(pages)+1}.png'
    image.save(str(path))
    pages.append(Image.open(path).convert('RGB'))
pages[0].save(OUT / 'layoutforslag.pdf', save_all=True, append_images=pages[1:], resolution=96)
