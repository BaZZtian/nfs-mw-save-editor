"""Build the runtime Career rival layers from the dev-only rival art vault.

The original 2K/4K layers live under ``dev_assets/og_assets/rivals`` and are
never copied into a release.  The generator optionally writes a wide preview
background back to that dev-only vault, while the transparent foreground and
the 1024px fallback portrait go to the packaged ``assets/icons/rivals`` tree.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBitmap, QGuiApplication, QImage, QImageWriter, QPainter, QRegion


BACKGROUND_WIDTH = 3360
BACKGROUND_HEIGHT = 480
FOREGROUND_MAX = 1024
RUNTIME_PORTRAIT_MAX = 1024


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2] / "dev_assets" / "og_assets" / "rivals"


def _runtime_root() -> Path:
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


def build_stage(
    root: Path,
    stage: int,
    *,
    runtime_root: Path | None = None,
    include_background: bool = False,
    force: bool = False,
) -> tuple[Path, Path]:
    """Build one rival's generated layers.

    ``root`` remains the source directory so callers can point the generator
    at a temporary fixture.  When ``runtime_root`` is supplied, only the
    runtime foreground and fallback portrait are written there.  The wide
    background is a dev-only preview and is generated only when
    ``include_background=True``; the live Qt hero does not read it.  Leaving
    ``runtime_root`` unset preserves the old single-root output location for
    small local generator tests; pass ``include_background=True`` when that
    test also needs the optional preview background.
    """
    output_root = runtime_root or root
    output_dir = output_root / "hero"
    output_dir.mkdir(parents=True, exist_ok=True)
    background_output = root / "hero" / f"rival_{stage:02d}_hero_bg.png"
    foreground_output = output_dir / f"rival_{stage:02d}_hero_fg.png"
    portrait_output = output_root / f"rival_{stage:02d}.png"
    graffiti_output = output_root / f"rival_{stage:02d}_graf.png"
    if (
        (not include_background or background_output.exists())
        and foreground_output.exists()
        and (runtime_root is None or portrait_output.exists())
        and (runtime_root is None or graffiti_output.exists())
        and not force
    ):
        return background_output, foreground_output

    (root / "hero").mkdir(parents=True, exist_ok=True)
    portrait = _load(root / f"rival_{stage:02d}.png")
    graffiti = _load(root / f"rival_{stage:02d}_graf.png")

    if include_background:
        background = _load(root / f"rival_{stage:02d}_bg.png")
        canvas = QImage(BACKGROUND_WIDTH, BACKGROUND_HEIGHT, QImage.Format_RGB32)
        canvas.fill(Qt.black)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # Every *_bg source already has a rival baked into its right half. Use
        # the environmental left half only, then take a 7:1 strip for the
        # ultrawide preview canvas. The separately generated foreground
        # supplies the rival.
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

        # Signature sits behind the subject so it reads as texture, not a
        # badge.
        signature = graffiti.scaled(
            620, 310, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
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
    if runtime_root is not None:
        # Graffiti is already a compact 512x256 runtime layer.  Copy it
        # byte-for-byte so the generator never recompresses or changes the
        # visual source while still making the runtime tree reproducible.
        shutil.copyfile(root / f"rival_{stage:02d}_graf.png", graffiti_output)
        fallback = portrait.scaled(
            RUNTIME_PORTRAIT_MAX,
            RUNTIME_PORTRAIT_MAX,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        _write_png(portrait_output, fallback)
    return background_output, foreground_output


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_source_root())
    parser.add_argument("--runtime-root", type=Path, default=_runtime_root())
    parser.add_argument(
        "--include-background",
        action="store_true",
        help="also regenerate the dev-only hero background preview",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    for stage in range(1, 16):
        background, foreground = build_stage(
            args.root,
            stage,
            runtime_root=args.runtime_root,
            include_background=args.include_background,
            force=args.force,
        )
        if args.include_background:
            print(background)
        print(foreground)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
