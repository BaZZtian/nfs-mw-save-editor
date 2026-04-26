"""Reusable widgets for the NFS MW Save Editor UI."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, QEvent, QPropertyAnimation, QTimer, QEasingCurve, Property, QRectF, QPoint
from PySide6.QtGui import QPixmap, QPainter, QLinearGradient, QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.icon_map import token_icon_path
from ui.theme import apply_popup_theme, resolve_theme_tokens


def build_perf_level_row(name: str, level: int, max_level: Optional[int]) -> tuple[QWidget, QHBoxLayout]:
    """Build one performance level row: label + optional segments + level number.

    Returns ``(row_widget, row_layout)`` so callers can append page-specific
    controls (e.g. +/- buttons on the Tuning tab).

    Pure function — no page state, no signal wiring.
    """
    row_w = QWidget()
    row_w.setObjectName("partsLevelRow")
    row_layout = QHBoxLayout(row_w)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(6)

    lbl = QLabel(name)
    lbl.setObjectName("partsLevelLabel")
    row_layout.addWidget(lbl)

    if max_level is not None:
        for seg_idx in range(1, max_level + 1):
            seg = QFrame()
            seg.setObjectName("partsLevelSeg")
            seg.setProperty("filled", str(seg_idx) if level >= seg_idx else "0")
            seg.setFixedSize(20, 8)
            row_layout.addWidget(seg)

    num = QLabel(f"{level}/{max_level}" if max_level is not None else f"{level}/?")
    num.setObjectName("partsLevelNum")
    row_layout.addWidget(num)

    return row_w, row_layout


def build_perf_value_host(level: int, max_level: Optional[int], *, object_name: str = "partsPerfControlHost") -> QWidget:
    host = QWidget()
    host.setObjectName(object_name)
    host.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    layout = QHBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    if max_level is not None:
        for seg_idx in range(1, int(max_level) + 1):
            seg = QFrame()
            seg.setObjectName("partsLevelSeg")
            seg.setProperty("filled", str(seg_idx) if int(level) >= seg_idx else "0")
            seg.setFixedSize(20, 8)
            layout.addWidget(seg)

    num = QLabel(f"{int(level)}/{max_level}" if max_level is not None else f"{int(level)}/?")
    num.setObjectName("partsLevelNum")
    layout.addWidget(num)
    return host


class ShimmerFrame(QFrame):
    """A QFrame with a subtle pink shimmer sweep animation.

    The shimmer is a semi-transparent linear gradient that sweeps
    left-to-right every ``interval_ms`` (default ~4 s).
    """

    _SHIMMER_COLOR = QColor(240, 139, 180)  # #F08BB4

    _DEFAULT_INTERVAL_MS = 4000
    _DEFAULT_SWEEP_MS = 1200
    _INITIAL_DELAY_MS = 600

    def __init__(self, parent=None, *, interval_ms: int = _DEFAULT_INTERVAL_MS,
                 sweep_ms: int = _DEFAULT_SWEEP_MS):
        super().__init__(parent)
        self._shimmer_pos: float = -0.3  # off-screen left
        self._interval_ms = interval_ms
        self._sweep_ms = sweep_ms

        # Animation: sweeps _shimmer_pos from -0.3 to 1.3
        self._anim = QPropertyAnimation(self, b"shimmerPos", self)
        self._anim.setDuration(self._sweep_ms)
        self._anim.setStartValue(-0.3)
        self._anim.setEndValue(1.3)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._anim.finished.connect(self._schedule_next)

        # Start first cycle after a short delay
        QTimer.singleShot(self._INITIAL_DELAY_MS, self._start_sweep)

    # ── Qt property for animation ──────────────────────────────
    def _get_shimmer_pos(self) -> float:
        return self._shimmer_pos

    def _set_shimmer_pos(self, val: float) -> None:
        self._shimmer_pos = val
        self.update()  # trigger repaint

    shimmerPos = Property(float, _get_shimmer_pos, _set_shimmer_pos)

    # ── Animation control ──────────────────────────────────────
    def _start_sweep(self) -> None:
        if self.isVisible():
            self._anim.start()

    def _schedule_next(self) -> None:
        QTimer.singleShot(self._interval_ms, self._start_sweep)

    # ── Paint overlay ──────────────────────────────────────────
    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        # Only paint while the gradient is in visible range
        if self._shimmer_pos < -0.25 or self._shimmer_pos > 1.25:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect())
        w = rect.width()
        center_x = rect.left() + w * self._shimmer_pos
        half_band = w * 0.25  # shimmer band width = 50% of widget

        grad = QLinearGradient(center_x - half_band, 0, center_x + half_band, 0)
        c = QColor(self._SHIMMER_COLOR)
        c.setAlphaF(0.0)
        grad.setColorAt(0.0, c)
        c2 = QColor(self._SHIMMER_COLOR)
        c2.setAlphaF(0.18)
        grad.setColorAt(0.5, c2)
        c3 = QColor(self._SHIMMER_COLOR)
        c3.setAlphaF(0.0)
        grad.setColorAt(1.0, c3)

        painter.setBrush(grad)
        painter.setPen(Qt.NoPen)
        # Use rounded rect matching the border-radius from the stylesheet
        painter.drawRoundedRect(rect, 8, 8)
        painter.end()


class WantSpinBox(QSpinBox):
    """SpinBox that ignores mouse wheel to prevent accidental edits."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Keep click/tab keyboard editing, but do not let wheel scrolling focus the control.
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        event.ignore()


class SplitTextProgressBar(QProgressBar):
    """Progress bar with split text rendering over filled and unfilled regions."""

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in {
            QEvent.StyleChange,
            QEvent.PaletteChange,
            QEvent.ApplicationPaletteChange,
        }:
            self.update()

    def paintEvent(self, event) -> None:
        _ = event
        tokens = resolve_theme_tokens()
        radius = float(tokens.get("RADIUS_MD", "8px").removesuffix("px") or 8.0)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        minimum = self.minimum()
        maximum = self.maximum()
        if maximum <= minimum:
            fraction = 0.0
        else:
            fraction = (self.value() - minimum) / (maximum - minimum)
            fraction = max(0.0, min(1.0, fraction))
        fill_width = rect.width() * fraction
        text = self.text()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor(tokens["BORDER"]))
        painter.setBrush(QColor(tokens["BORDER"]))
        painter.drawRoundedRect(rect, radius, radius)

        if fill_width > 0:
            painter.save()
            painter.setClipRect(QRectF(rect.x(), rect.y(), fill_width, rect.height()))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(tokens["ACCENT"]))
            painter.drawRoundedRect(rect, radius, radius)
            painter.restore()

        if text:
            text_rect = self.rect()
            painter.setFont(self.font())
            if fill_width < rect.width():
                painter.save()
                painter.setClipRect(QRectF(rect.x() + fill_width, rect.y(), rect.width() - fill_width, rect.height()))
                painter.setPen(QColor(tokens["TEXT"]))
                painter.drawText(text_rect, Qt.AlignCenter, text)
                painter.restore()
            if fill_width > 0:
                painter.save()
                painter.setClipRect(QRectF(rect.x(), rect.y(), fill_width, rect.height()))
                painter.setPen(QColor(tokens["TEXT_ON_ACCENT"]))
                painter.drawText(text_rect, Qt.AlignCenter, text)
                painter.restore()
        painter.end()


class ThemeTransitionOverlay(QWidget):
    """Snapshot overlay that crossfades out during runtime theme switches."""

    _DURATION_MS = 240

    def __init__(self, parent: QWidget, snapshot: QPixmap, *, duration_ms: int = _DURATION_MS):
        super().__init__(parent)
        self._snapshot = snapshot
        self._animation_finished = False

        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAutoFillBackground(False)
        self.setGeometry(parent.rect())

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(duration_ms)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.finished.connect(self._cleanup_after_animation)

    def sync_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        self.update()

    def start(self) -> None:
        self.sync_to_parent()
        self.show()
        self.raise_()
        self._fade.start()

    def finish_immediately(self) -> None:
        if self._animation_finished:
            return
        self._fade.stop()
        self._cleanup_after_animation()

    def _cleanup_after_animation(self) -> None:
        if self._animation_finished:
            return
        self._animation_finished = True
        self.hide()
        self.deleteLater()

    def paintEvent(self, event) -> None:
        _ = event
        if self._snapshot.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(self.rect(), self._snapshot)
        painter.end()


class TokenCard(QWidget):
    """A dark card representing a single Junkman token."""

    CARD_WIDTH = 240
    ICON_SIZE = 40

    def __init__(
        self,
        token_id: int,
        name: str,
        have: int,
        want: int,
        max_val: int,
        on_change: Callable[[int, int], None],
        on_rename: Callable[[int, str], None],
    ):
        super().__init__()
        self.token_id = token_id
        self._on_change = on_change
        self._on_rename = on_rename

        self.setObjectName("tokenCard")
        self.setFixedWidth(self.CARD_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setToolTip(f"Token ID: {token_id}")
        self.setProperty("hovered", False)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)
        root.setAlignment(Qt.AlignTop)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        icon_path = token_icon_path(token_id)
        if icon_path and icon_path.exists():
            pix = QPixmap(str(icon_path)).scaled(
                self.ICON_SIZE,
                self.ICON_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.icon_label.setPixmap(pix)
        icon_row = QHBoxLayout()
        icon_row.setAlignment(Qt.AlignCenter)
        icon_row.addWidget(self.icon_label)
        root.addLayout(icon_row)

        self.name_edit = QLineEdit(name)
        self.name_edit.setAlignment(Qt.AlignCenter)
        self.name_edit.setObjectName("cardName")
        self.name_edit.setToolTip(name)
        self.name_edit.setCursorPosition(0)
        self.name_edit.setMinimumWidth(180)
        self.name_edit.editingFinished.connect(self._handle_rename)
        root.addWidget(self.name_edit)

        self.have_label = QLabel(f"Have: {have}")
        self.have_label.setObjectName("haveLabel")
        self.have_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.have_label)

        spin_row = QHBoxLayout()
        spin_row.setSpacing(4)
        spin_row.setAlignment(Qt.AlignCenter)

        self.btn_minus = QPushButton("-")
        self.btn_minus.setObjectName("cardBtn")
        self.btn_minus.setFixedSize(26, 26)
        self.btn_minus.clicked.connect(lambda: self._bump(-1))

        self.spin = WantSpinBox()
        self.spin.setRange(0, max_val)
        self.spin.setValue(want)
        self.spin.setFixedWidth(60)
        self.spin.setAlignment(Qt.AlignCenter)
        self.spin.valueChanged.connect(self._on_spin_changed)

        self.btn_plus = QPushButton("+")
        self.btn_plus.setObjectName("cardBtn")
        self.btn_plus.setFixedSize(26, 26)
        self.btn_plus.clicked.connect(lambda: self._bump(1))

        spin_row.addWidget(self.btn_minus)
        spin_row.addWidget(self.spin)
        spin_row.addWidget(self.btn_plus)
        root.addLayout(spin_row)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, max_val)
        self.slider.setValue(want)
        self.slider.setObjectName("cardSlider")
        self.slider.setTracking(False)
        self.slider.valueChanged.connect(self._on_slider_changed)
        root.addWidget(self.slider)

        self._apply_changed_state(want != have)

    def set_have_want(self, have: int, want: int) -> None:
        self.have_label.setText(f"Have: {have}")
        self.spin.blockSignals(True)
        self.spin.setValue(want)
        self.spin.blockSignals(False)
        self.slider.blockSignals(True)
        self.slider.setValue(want)
        self.slider.blockSignals(False)
        self._apply_changed_state(want != have)

    def set_max(self, max_val: int) -> None:
        cur = self.spin.value()
        self.spin.setRange(0, max_val)
        self.spin.setValue(min(cur, max_val))
        self.slider.setRange(0, max_val)
        self.slider.setValue(min(cur, max_val))

    def _bump(self, delta: int) -> None:
        new_val = max(self.spin.minimum(), min(self.spin.maximum(), self.spin.value() + delta))
        self.spin.setValue(new_val)

    def _on_spin_changed(self, val: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(val)
        self.slider.blockSignals(False)
        self._on_change(self.token_id, val)
        have = int(self.have_label.text().replace("Have: ", ""))
        self._apply_changed_state(val != have)

    def _on_slider_changed(self, val: int) -> None:
        self.spin.blockSignals(True)
        self.spin.setValue(val)
        self.spin.blockSignals(False)
        self._on_change(self.token_id, val)
        have = int(self.have_label.text().replace("Have: ", ""))
        self._apply_changed_state(val != have)

    def _handle_rename(self) -> None:
        new_name = self.name_edit.text().strip() or f"Token #{self.token_id}"
        self.name_edit.setText(new_name)
        self.name_edit.setToolTip(new_name)
        self.name_edit.setCursorPosition(0)
        self._on_rename(self.token_id, new_name)

    def _apply_changed_state(self, changed: bool) -> None:
        self.setProperty("changed", changed)
        self.style().unpolish(self)
        self.style().polish(self)

    # ── Hover effect ─────────────────────────────────────────────

    def enterEvent(self, event) -> None:
        self.setProperty("hovered", True)
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setProperty("hovered", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)


class ToastNotification(QLabel):
    """A brief, self-destroying notification that appears at the top-right."""

    _active: list["ToastNotification"] = []   # class-level stack
    _DISMISS_MS = 2500
    _STACK_SPACING = 44
    _BASE_Y_OFFSET = 12

    def __init__(self, parent: QWidget, message: str, *, is_error: bool = False):
        super().__init__(message, parent)
        self.setObjectName("toastError" if is_error else "toastSuccess")
        apply_popup_theme(self)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(36)
        self.setMinimumWidth(220)
        self.adjustSize()
        self.setFixedWidth(max(220, self.sizeHint().width() + 32))

        # opacity effect for fade-out
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        # position at top-right
        start_pos = QPoint(parent.width() - self.width() - 16, -self.height())
        self.move(start_pos)
        self.show()
        self.raise_()

        # slide in
        self._slide = QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(300)
        self._slide.setStartValue(self.pos())
        self._slide.setEndValue(self._target_pos(len(ToastNotification._active)))
        self._slide.setEasingCurve(QEasingCurve.OutCubic)
        self._slide.start()

        ToastNotification._active.append(self)

        # auto-dismiss
        QTimer.singleShot(self._DISMISS_MS, self._fade_out)

    def _fade_out(self):
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(400)
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._cleanup)
        self._fade.start()

    def _cleanup(self):
        if self in ToastNotification._active:
            ToastNotification._active.remove(self)
            ToastNotification.reposition_active(self.parentWidget())
        self.deleteLater()

    def _target_pos(self, index: int) -> QPoint:
        parent = self.parentWidget()
        if parent is None:
            return self.pos()
        px = parent.width() - self.width() - 16
        py = self._BASE_Y_OFFSET + index * self._STACK_SPACING
        return QPoint(px, py)

    def reposition(self, index: int) -> None:
        if hasattr(self, "_slide"):
            self._slide.stop()
        self.move(self._target_pos(index))
        self.raise_()

    @classmethod
    def reposition_active(cls, parent: QWidget | None = None) -> None:
        active = [toast for toast in cls._active if parent is None or toast.parentWidget() is parent]
        for index, toast in enumerate(active):
            toast.reposition(index)

    @staticmethod
    def show_toast(parent: QWidget, message: str, *, is_error: bool = False):
        """Show a brief toast notification."""
        ToastNotification(parent, message, is_error=is_error)


class ApplyConfirmDialog(QDialog):
    """Compact apply-confirm dialog with collapsible details."""

    def __init__(
        self,
        parent: QWidget,
        *,
        summary_lines: list[str],
        detail_sections: list[tuple[str, list[str]]],
    ):
        super().__init__(parent)
        self.setWindowTitle("Review staged changes")
        self.setModal(True)
        self.setSizeGripEnabled(True)
        self._base_width = 760

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("Apply staged changes to the open save?")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        summary = QLabel("\n".join(summary_lines))
        summary.setWordWrap(True)
        summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(summary)

        detail_count = sum(len(lines) for _, lines in detail_sections)
        self.details_toggle = QToolButton()
        self.details_toggle.setText(f"Show details ({detail_count})")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setChecked(False)
        self.details_toggle.toggled.connect(self._on_toggle_details)
        root.addWidget(self.details_toggle, 0, Qt.AlignLeft)

        self.details_edit = QPlainTextEdit()
        self.details_edit.setReadOnly(True)
        self.details_edit.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.details_edit.setMaximumHeight(320)
        self.details_edit.setMinimumHeight(220)
        self.details_edit.setVisible(False)
        self.details_edit.setPlainText(self._details_text(detail_sections))
        root.addWidget(self.details_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._apply_btn = buttons.button(QDialogButtonBox.Ok)
        self._cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        if self._apply_btn is not None:
            self._apply_btn.setText("Apply")
        if self._cancel_btn is not None:
            self._cancel_btn.setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        apply_popup_theme(self)

        root.activate()
        self._collapsed_height = max(320, self.sizeHint().height() + 12)
        self.resize(self._base_width, self._collapsed_height)

    @staticmethod
    def _details_text(detail_sections: list[tuple[str, list[str]]]) -> str:
        chunks: list[str] = []
        for title, lines in detail_sections:
            if not lines:
                continue
            chunks.append(f"{title}:\n" + "\n".join(lines))
        return "\n\n".join(chunks)

    def _on_toggle_details(self, checked: bool) -> None:
        self.details_toggle.setText("Hide details" if checked else f"Show details ({self._detail_line_count()})")
        self.details_edit.setVisible(checked)
        layout = self.layout()
        if layout is not None:
            layout.activate()
        if checked:
            target_height = max(self._collapsed_height + 260, self.sizeHint().height() + 12)
            self.resize(max(self.width(), self._base_width), target_height)
        else:
            self.resize(max(self.width(), self._base_width), self._collapsed_height)

    def _detail_line_count(self) -> int:
        text = self.details_edit.toPlainText()
        return 0 if not text else len([line for line in text.splitlines() if line.strip()])
