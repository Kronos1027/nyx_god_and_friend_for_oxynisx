"""Bundled Lucide SVGs, recolored only with trusted design tokens."""
from functools import lru_cache
from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from app_paths import resource_path

NAMES = {'message-circle','calendar','settings','book-open','panels-top-left','plus','search',
         'mic','arrow-up','square','shield','panel-right','list-checks','brain','chevrons-left','command'}


@lru_cache(maxsize=128)
def icon(name, color):
    if name not in NAMES:
        raise ValueError('Ícone não empacotado.')
    data = (resource_path('assets/icons')/(name+'.svg')).read_bytes().replace(b'currentColor', color.encode('ascii'))
    renderer = QSvgRenderer(QByteArray(data))
    result = QIcon()
    for size in (16,20,24,32,40):
        pixmap = QPixmap(size*2,size*2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(0,0,size*2,size*2))
        painter.end()
        pixmap.setDevicePixelRatio(2)
        result.addPixmap(pixmap)
    return result
