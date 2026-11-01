"""Render three fan-menu label proposals using Hybrid's real FanMenu painter."""
import math
from pathlib import Path
from types import MethodType

from PIL import Image
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from omacad.ui.fan_menu import FanItem, FanMenu


OUT = Path(__file__).parent
APP = QApplication([])
viewport = QWidget()
viewport.resize(1000, 760)
categories = [FanItem('create', 'Create', children=[FanItem(x.lower().replace(' ', '_'), x) for x in
              ('Sketch', 'Extrude', 'Hole', 'Revolve', 'Pattern', 'Fillet', 'Shell')])]
categories += [FanItem(x.lower(), x) for x in ('Modify', 'Inspect', 'View', 'History', 'Context')]
original = FanMenu._draw_sector_content


def label_variant(mode):
    def draw(self, painter, sec, text_col, muted_col):
        mid = sec.start_angle + sec.span_angle / 2
        if mode == 0 or (mode == 1 and math.sin(math.radians(mid)) >= 0):
            return original(self, painter, sec, text_col, muted_col)
        radius = (sec.r_inner + sec.r_outer) / 2
        x = self.center_pos.x() + radius * math.cos(math.radians(mid))
        y = self.center_pos.y() - radius * math.sin(math.radians(mid))
        painter.save()
        painter.translate(x, y)
        painter.setPen(text_col)
        font = QFont('Sans Serif')
        font.setPixelSize(11)
        painter.setFont(font)
        painter.drawText(QRectF(-48, -12, 96, 24), Qt.AlignmentFlag.AlignCenter, sec.item.label)
        painter.restore()
    return draw


pages = []
for mode, title in enumerate(('A · Böjd text som nu', 'B · Vänd text i nedre bågen', 'C · Horisontell text')):
    menu = FanMenu(viewport)
    menu.popup(QPoint(500, 390), categories, hub_center=FanItem('cancel', 'Cancel'))
    menu._draw_sector_content = MethodType(label_variant(mode), menu)
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
    path = OUT / f'forslag-{mode+1}.png'
    image.save(str(path))
    pages.append(Image.open(path).convert('RGB'))
pages[0].save(OUT / 'layoutforslag.pdf', save_all=True, append_images=pages[1:], resolution=96)
