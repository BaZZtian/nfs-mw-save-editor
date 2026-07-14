"""Build responsive Career hero background/foreground layers from rival art.

The original 2K/4K layers remain untouched. Runtime draws a wide atmospheric
background and a transparent rival independently so ultrawide layouts never
crop a face merely because the banner aspect ratio changed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBitmap, QGuiApplication, QImage, QImageWriter, QPainter, QRegion


BACKGROUND_WIDTH = 3360
BACKGROUND_HEIGHT = 480
FOREGROUND_MAX = 1024


def _source_root() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "icons" / "rivals"


def _load(path: Path) -> QImage:
    image = QImage(str(path))
    if image.isNull():
        raise RuntimeError(f"could not load {path}")
    return image


def _write_png(path: Path, image: QImage) -> None:
    writer = QImageWriter(str(path), b"png")
    writer.setCompression(100)
    if not writer.write(image):
        raise RuntimeError(f"could not write {path}: {writer.errorString()}")


def _trim_transparent(image: QImage) -> QImage:
    bounds = QRegion(QBitmap.fromImage(image.createAlphaMask())).boundingRect()
    if bounds.isEmpty():
        return image
    pad_x = max(12, int(bounds.width() * 0.025))
    pad_y = max(12, int(bounds.height() * 0.018))
    bounds.adjust(-pad_x, -pad_y, pad_x, pad_y)
    bounds = bounds.intersected(image.rect())
    return image.copy(bounds)


def build_stage(root: Path, stage: int, *, force: bool = False) -> tuple[Path, Path]:
    output_dir = root / "hero"
    output_dir.mkdir(parents=True, exist_ok=True)
    background_output = output_dir / f"rival_{stage:02d}_hero_bg.png"
    foreground_output = output_dir / f"rival_{stage:02d}_hero_fg.png"
    if background_output.exists() and foreground_output.exists() and not force:
        return background_output, foreground_output

    background = _load(root / f"rival_{stage:02d}_bg.png")
    portrait = _load(root / f"rival_{stage:02d}.png")
    graffiti = _load(root / f"rival_{stage:02d}_graf.png")

    canvas = QImage(BACKGROUND_WIDTH, BACKGROUND_HEIGHT, QImage.Format_RGB32)
    canvas.fill(Qt.black)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    # Every *_bg source already has a rival baked into its right half. Use the
    # environmental left half only, then take a 7:1 strip for the ultrawide
    # runtime canvas. The separately generated foreground supplies the rival.
    source_width = background.width() * 0.50
    source_height = source_width / 7.0
    source_y = max(0.0, background.height() * 0.10)
    if source_y + source_height > background.height():
        source_y = background.height() - source_height
    painter.drawImage(
        QRectF(0, 0, BACKGROUND_WIDTH, BACKGROUND_HEIGHT),
        background,
        QRectF(0, source_y, source_width, source_height),
    )

    # Signature sits behind the subject so it reads as texture, not a badge.
    signature = graffiti.scaled(620, 310, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    painter.setOpacity(0.42)
    painter.drawImage(BACKGROUND_WIDTH - 930, 195, signature)
    painter.end()
    _write_png(background_output, canvas)

    subject = _trim_transparent(portrait).scaled(
        FOREGROUND_MAX,
        FOREGROUND_MAX,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )
    _write_png(foreground_output, subject)
    return background_output, foreground_output


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_source_root())
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for stage in range(1, 16):
        background, foreground = build_stage(args.root, stage, force=args.force)
        print(background)
        print(foreground)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
