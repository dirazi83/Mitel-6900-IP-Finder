#!/usr/bin/env python3
"""Build assets/appicon.ico (and a PNG for the README) from the source logo.

Run from the repository root:

    env\\Scripts\\python.exe tools/make_icon.py

The source artwork (assets/logo_source.png) was exported with the editor's
transparency checkerboard flattened into the pixels, so the background is
keyed out first: the checker colours are sampled from the border and flood
filled inward from the edges, which leaves similar greys inside the artwork
untouched. The result is trimmed, squared, scaled to each icon size and packed
into a multi-resolution .ico.
"""
import collections
import os
import struct
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage

SIZES = (16, 24, 32, 48, 64, 128, 256)
SOURCE = os.path.join('assets', 'logo_source.png')
OUTPUT = os.path.join('assets', 'appicon.ico')
PREVIEW = os.path.join('assets', 'appicon.png')

TOLERANCE = 62      # per-channel distance that still counts as background
MARGIN_RATIO = 0.02  # breathing room around the artwork, as a share of the side


def sample_background(image):
    """Collect the distinct colours that make up the border checkerboard."""
    width, height = image.width(), image.height()
    seen = []
    for x in range(0, width, max(1, width // 64)):
        for y in (0, height - 1):
            seen.append(image.pixelColor(x, y).rgb())
    for y in range(0, height, max(1, height // 64)):
        for x in (0, width - 1):
            seen.append(image.pixelColor(x, y).rgb())

    counts = collections.Counter(seen)
    colours = []
    for value, _count in counts.most_common(4):
        colour = QColor.fromRgb(value)
        if all(abs(colour.red() - other.red()) + abs(colour.green() - other.green())
               + abs(colour.blue() - other.blue()) > TOLERANCE for other in colours):
            colours.append(colour)
    return colours


def key_out_background(image):
    """Flood fill the border colours inward and make them transparent."""
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    width, height = image.width(), image.height()
    backgrounds = sample_background(image)
    if not backgrounds:
        return image

    def is_background(colour):
        return any(abs(colour.red() - ref.red()) <= TOLERANCE
                   and abs(colour.green() - ref.green()) <= TOLERANCE
                   and abs(colour.blue() - ref.blue()) <= TOLERANCE
                   for ref in backgrounds)

    visited = bytearray(width * height)
    queue = collections.deque()
    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    transparent = QColor(0, 0, 0, 0)
    while queue:
        x, y = queue.popleft()
        index = y * width + x
        if visited[index]:
            continue
        visited[index] = 1
        if not is_background(image.pixelColor(x, y)):
            continue
        image.setPixelColor(x, y, transparent)
        if x > 0:
            queue.append((x - 1, y))
        if x + 1 < width:
            queue.append((x + 1, y))
        if y > 0:
            queue.append((x, y - 1))
        if y + 1 < height:
            queue.append((x, y + 1))
    return image


def content_bounds(image):
    """Bounding box of the pixels that survived the key-out."""
    width, height = image.width(), image.height()
    left, top, right, bottom = width, height, -1, -1
    for y in range(height):
        for x in range(width):
            if image.pixelColor(x, y).alpha() > 8:
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right < 0:
        return 0, 0, width, height
    return left, top, right - left + 1, bottom - top + 1


def square_canvas(image):
    """Crop to the artwork, then centre it on a transparent square."""
    left, top, width, height = content_bounds(image)
    cropped = image.copy(left, top, width, height)
    side = int(max(width, height) * (1 + MARGIN_RATIO * 2))
    canvas = QImage(side, side, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)

    from PySide6.QtGui import QPainter
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawImage((side - width) // 2, (side - height) // 2, cropped)
    painter.end()
    return canvas


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
    source = QImage(SOURCE)
    if source.isNull():
        print('Cannot read %s' % SOURCE, file=sys.stderr)
        return 1

    master = square_canvas(key_out_background(source))
    images = [master.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
              for size in SIZES]
    write_ico(OUTPUT, images)
    images[-1].save(PREVIEW, 'PNG')
    app.quit()
    print('Wrote %s (%d bytes, sizes: %s)'
          % (OUTPUT, os.path.getsize(OUTPUT), ', '.join(str(s) for s in SIZES)))
    print('Wrote %s (%d bytes)' % (PREVIEW, os.path.getsize(PREVIEW)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
