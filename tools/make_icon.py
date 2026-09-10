#!/usr/bin/env python3
"""Generate assets/appicon.ico for the application and the Windows build.

Run from the repository root:

    env\\Scripts\\python.exe tools/make_icon.py

Draws the icon with QPainter at several sizes, encodes each as PNG and packs
them into a multi-resolution .ico. Committed output keeps the build
reproducible without adding a runtime dependency.
"""
import math
import os
import struct
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPainterPathStroker, QPen,
                           QTransform)

SIZES = (16, 24, 32, 48, 64, 128, 256)
OUTPUT = os.path.join('assets', 'appicon.ico')
PREVIEW = os.path.join('assets', 'appicon.png')

BACKGROUND_TOP = QColor('#1f6feb')
BACKGROUND_BOTTOM = QColor('#0b3a86')
FOREGROUND = QColor('#ffffff')
ACCENT = QColor('#7ee2c6')


def handset_path(size):
    """Telephone handset: a curved shaft with an ear pad flared at each end."""
    radius = size * 0.30
    shaft = size * 0.125
    pad_width = size * 0.20
    pad_height = size * 0.26
    corner = size * 0.05
    sweep = 148.0  # degrees of arc the shaft covers

    arc = QPainterPath()
    box = QRectF(-radius, -radius, radius * 2, radius * 2)
    arc.arcMoveTo(box, 270 - sweep / 2)
    arc.arcTo(box, 270 - sweep / 2, sweep)

    stroker = QPainterPathStroker()
    stroker.setWidth(shaft)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    path = stroker.createStroke(arc)

    for sign in (-1, 1):
        angle = math.radians(270 - sign * sweep / 2)
        end = QPointF(radius * math.cos(angle), -radius * math.sin(angle))
        pad = QPainterPath()
        pad.addRoundedRect(QRectF(-pad_width / 2, -pad_height / 2,
                                  pad_width, pad_height), corner, corner)
        transform = QTransform()
        transform.translate(end.x(), end.y())
        transform.rotate(sign * sweep / 2)
        path = path.united(transform.map(pad))
    return path.simplified()


def draw_icon(size):
    scale = 4 if size < 64 else 1  # supersample small sizes for clean edges
    canvas = size * scale
    image = QImage(canvas, canvas, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    gradient = QLinearGradient(0, 0, canvas, canvas)
    gradient.setColorAt(0.0, BACKGROUND_TOP)
    gradient.setColorAt(1.0, BACKGROUND_BOTTOM)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(gradient))
    radius = canvas * 0.22
    painter.drawRoundedRect(QRectF(0, 0, canvas, canvas), radius, radius)

    # Signal arcs, upper right.
    pen = QPen(ACCENT)
    pen.setWidthF(canvas * 0.055)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    centre = QPointF(canvas * 0.70, canvas * 0.34)
    for index, factor in enumerate((0.12, 0.21, 0.30)):
        if size <= 16 and index > 1:
            break
        radius_arc = canvas * factor
        rect = QRectF(centre.x() - radius_arc, centre.y() - radius_arc,
                      radius_arc * 2, radius_arc * 2)
        painter.drawArc(rect, -25 * 16, 95 * 16)

    # Handset, lower left, rotated like a lifted receiver.
    painter.save()
    painter.translate(canvas * 0.44, canvas * 0.60)
    painter.rotate(-38)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(FOREGROUND)
    painter.drawPath(handset_path(canvas))
    painter.restore()
    painter.end()

    if scale != 1:
        image = image.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    return image


def png_bytes(image):
    storage = QByteArray()  # must outlive the buffer that writes into it
    buffer = QBuffer(storage)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise RuntimeError('Qt could not encode the image as PNG.')
    buffer.close()
    return bytes(storage)


def write_ico(path, images):
    """Pack PNG-encoded images into an .ico (PNG frames, Vista and later)."""
    payloads = [png_bytes(image) for image in images]
    header = struct.pack('<HHH', 0, 1, len(payloads))
    offset = len(header) + 16 * len(payloads)
    entries, blob = b'', b''
    for image, payload in zip(images, payloads):
        width = 0 if image.width() >= 256 else image.width()
        height = 0 if image.height() >= 256 else image.height()
        entries += struct.pack('<BBBBHHII', width, height, 0, 0, 1, 32,
                               len(payload), offset)
        offset += len(payload)
        blob += payload
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'wb') as output:
        output.write(header + entries + blob)


def main():
    app = QGuiApplication(sys.argv)  # must stay referenced while painting
    images = [draw_icon(size) for size in SIZES]
    write_ico(OUTPUT, images)
    images[-1].save(PREVIEW, 'PNG')  # for the README
    app.quit()
    print('Wrote %s (%d bytes, sizes: %s)'
          % (OUTPUT, os.path.getsize(OUTPUT), ', '.join(str(s) for s in SIZES)))
    print('Wrote %s (%d bytes)' % (PREVIEW, os.path.getsize(PREVIEW)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
