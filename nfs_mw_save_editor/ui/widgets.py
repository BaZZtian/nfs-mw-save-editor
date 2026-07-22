"""Reusable widgets for the NFS MW Save Editor UI."""
from __future__ import annotations

import math
from typing import Callable, Optional

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    QTimer,
    Qt,
    Property,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPalette, QPixmap, QTransform
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
    QStackedLayout,
    QStackedWidget,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.icon_map import token_back_icon_path, token_icon_path
from ui.theme import apply_popup_theme, resolve_theme_tokens


class ShellActionButton(QPushButton):
    """Header/footer button with deterministic icon/text spacing."""

    _SIDE_PADDING = 8
    _ICON_TEXT_GAP = 8
    _HEIGHT = 44
    _MIN_WIDTH = 140

    def __init__(
        self,
        text: str,
        parent: Optional[QWidget] = None,
        *,
        height: Optional[int] = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("shellActionButton")
        self._height = int(height) if height is not None else self._HEIGHT
        self.setMinimumHeight(self._height)

    def _content_rects(self) -> tuple[QRectF, QRectF]:
        inner = QRectF(self.rect()).adjusted(
            self._SIDE_PADDING, 0, -self._SIDE_PADDING, 0
        )
        if self.icon().isNull():
            return QRectF(), inner
        icon_size = self.iconSize()
        icon_rect = QRectF(
            inner.left(),
            inner.center().y() - icon_size.height() / 2.0,
            icon_size.width(),
            icon_size.height(),
        )
        text_rect = QRectF(
            icon_rect.right() + self._ICON_TEXT_GAP,
            inner.top(),
            max(0.0, inner.right() - icon_rect.right() - self._ICON_TEXT_GAP),
            inner.height(),
        )
        return icon_rect, text_rect

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        width = self._SIDE_PADDING * 2 + text_width
        if not self.icon().isNull():
            width += self.iconSize().width() + self._ICON_TEXT_GAP
        return QSize(max(self._MIN_WIDTH, width), self._height)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self.sizeHint()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        option = QStyleOptionButton()
        self.initStyleOption(option)
        painter = QStylePainter(self)
        text = option.text
        icon = self.icon()
        option.text = ""
        option.icon = QIcon()
        painter.drawControl(QStyle.CE_PushButton, option)

        icon_rect, text_rect = self._content_rects()
        if option.state & QStyle.State_Sunken:
            shift_x = self.style().pixelMetric(QStyle.PM_ButtonShiftHorizontal, option, self)
            shift_y = self.style().pixelMetric(QStyle.PM_ButtonShiftVertical, option, self)
            icon_rect.translate(shift_x, shift_y)
            text_rect.translate(shift_x, shift_y)

        enabled = bool(option.state & QStyle.State_Enabled)
        if not icon.isNull():
            mode = QIcon.Normal if enabled else QIcon.Disabled
            state = QIcon.On if self.isChecked() else QIcon.Off
            icon.paint(painter, icon_rect.toRect(), Qt.AlignCenter, mode, state)
            alignment = Qt.AlignLeft | Qt.AlignVCenter
        else:
            alignment = Qt.AlignCenter
        painter.setFont(self.font())
        painter.drawItemText(
            text_rect.toRect(),
            int(alignment),
            option.palette,
            enabled,
            text,
            QPalette.ButtonText,
        )


class _SegmentHitButton(QPushButton):
    """Accessible click/focus target whose visuals belong entirely to its parent."""

    def paintEvent(self, _event) -> None:  # noqa: N802 - intentionally no native/QSS paint
        return

    def _update_control(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            parent.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().enterEvent(event)
        self._update_control()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().leaveEvent(event)
        self._update_control()

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().focusInEvent(event)
        self._update_control()

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().focusOutEvent(event)
        self._update_control()


class AnimatedSegmentedControl(QFrame):
    """Crisp segmented control painted as one interruptible moving surface."""

    _TRACK_INSET = 3
    currentChanged = Signal(int)

    def __init__(
        self,
        labels: list[str] | tuple[str, ...],
        *,
        button_object_name: str = "animatedSegmentButton",
        duration_ms: int = 180,
        fixed_height: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        if not labels:
            raise ValueError("AnimatedSegmentedControl needs at least one label")
        self.setObjectName("animatedSegmentedControl")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        if fixed_height is not None:
            self.setFixedHeight(fixed_height)
        self._current_index = 0
        self._duration_ms = duration_ms
        self._indicator_position = 0.0
        self._buttons: list[QPushButton] = []
        self._animation = QPropertyAnimation(self, b"indicatorPosition", self)
        self._animation.setDuration(duration_ms)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            self._TRACK_INSET,
            self._TRACK_INSET,
            self._TRACK_INSET,
            self._TRACK_INSET,
        )
        layout.setSpacing(2)
        for index, label in enumerate(labels):
            button = _SegmentHitButton(label)
            button.setObjectName(button_object_name)
            button.setCheckable(False)
            button.setCursor(Qt.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            button.clicked.connect(lambda _checked=False, i=index: self.setCurrentIndex(i))
            layout.addWidget(button, 1)
            self._buttons.append(button)
        self._sync_button_state()
        QTimer.singleShot(0, self._snap_indicator)

    def count(self) -> int:
        return len(self._buttons)

    def currentIndex(self) -> int:  # noqa: N802 - Qt-style API
        return self._current_index

    def button(self, index: int) -> QPushButton:
        return self._buttons[index]

    def setCurrentIndex(  # noqa: N802 - Qt-style API
        self, index: int, *, animate: bool = True, emit: bool = True
    ) -> None:
        if not 0 <= index < len(self._buttons):
            raise IndexError(index)
        if index == self._current_index:
            if not animate:
                self._snap_indicator()
            return
        self._current_index = index
        self._sync_button_state()
        self._animation.stop()
        if animate and self.isVisible() and self._button_geometry(index).isValid():
            self._animation.setStartValue(self._indicator_position)
            self._animation.setEndValue(float(index))
            self._animation.start()
        else:
            self._set_indicator_position(float(index))
        if emit:
            self.currentChanged.emit(index)

    def _sync_button_state(self) -> None:
        for index, button in enumerate(self._buttons):
            selected = index == self._current_index
            if button.property("selected") != selected:
                button.setProperty("selected", selected)

    def _button_geometry(self, index: int):
        button = self._buttons[index]
        return button.geometry()

    def indicatorRect(self) -> QRectF:  # noqa: N802 - Qt-style API
        """Current painted indicator rectangle, exposed for deterministic UI tests."""
        if not self._buttons:
            return QRectF()
        position = max(0.0, min(float(len(self._buttons) - 1), self._indicator_position))
        left_index = int(position)
        right_index = min(left_index + 1, len(self._buttons) - 1)
        progress = position - left_index
        left = QRectF(self._button_geometry(left_index))
        right = QRectF(self._button_geometry(right_index))
        return QRectF(
            left.x() + (right.x() - left.x()) * progress,
            left.y() + (right.y() - left.y()) * progress,
            left.width() + (right.width() - left.width()) * progress,
            left.height() + (right.height() - left.height()) * progress,
        ).adjusted(0.5, 0.5, -0.5, -0.5)

    def _get_indicator_position(self) -> float:
        return self._indicator_position

    def _set_indicator_position(self, value: float) -> None:
        self._indicator_position = float(value)
        self.update()

    indicatorPosition = Property(  # noqa: N815 - Qt property name
        float, _get_indicator_position, _set_indicator_position
    )

    def _snap_indicator(self) -> None:
        if not self._buttons:
            return
        self._animation.stop()
        self._set_indicator_position(float(self._current_index))

    @staticmethod
    def _radius(tokens: dict[str, str], name: str, fallback: float) -> float:
        raw = tokens.get(name, str(fallback)).removesuffix("px")
        try:
            return float(raw)
        except ValueError:
            return fallback

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._buttons:
            return
        tokens = resolve_theme_tokens()
        indicator = self.indicatorRect()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        track = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        track_radius = self._radius(tokens, "RADIUS_LG", 10.0)
        painter.setPen(QColor(tokens["BORDER"]))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(track, track_radius, track_radius)

        inner_radius = max(0.0, track_radius - self._TRACK_INSET)
        allow_hover = self._animation.state() != QAbstractAnimation.Running
        for index, button in enumerate(self._buttons):
            if allow_hover and button.underMouse() and index != self._current_index:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(tokens["BG_NAV_HOVER"]))
                painter.drawRoundedRect(QRectF(button.geometry()), inner_radius, inner_radius)

        painter.setPen(QColor(tokens["ACCENT_BRIGHT"]))
        painter.setBrush(QColor(tokens["ACCENT"]))
        painter.drawRoundedRect(indicator, inner_radius, inner_radius)

        def draw_labels(color: QColor) -> None:
            painter.setPen(color)
            for button in self._buttons:
                painter.setFont(button.font())
                painter.drawText(button.geometry(), Qt.AlignCenter, button.text())

        draw_labels(QColor(tokens["MUTED"]))
        painter.save()
        painter.setClipRect(indicator)
        draw_labels(QColor(tokens["TEXT_ON_ACCENT"]))
        painter.restore()

        for button in self._buttons:
            if button.hasFocus():
                focus = QRectF(button.geometry()).adjusted(1.5, 1.5, -1.5, -1.5)
                focus_color = QColor(tokens["ACCENT_BRIGHT"])
                focus_color.setAlpha(150)
                painter.setPen(focus_color)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(focus, inner_radius, inner_radius)
        painter.end()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._snap_indicator()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        QTimer.singleShot(0, self._snap_indicator)

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().changeEvent(event)
        if event.type() in {
            QEvent.StyleChange,
            QEvent.PaletteChange,
            QEvent.ApplicationPaletteChange,
        }:
            self._snap_indicator()
            self.update()


class AnimatedStackedWidget(QStackedWidget):
    """QStackedWidget that crossfades two live pages at native geometry."""

    def __init__(self, parent: Optional[QWidget] = None, *, duration_ms: int = 180) -> None:
        super().__init__(parent)
        self._duration_ms = duration_ms
        self._transition_group: Optional[QParallelAnimationGroup] = None
        self._transition_widgets: tuple[QWidget, QWidget] | None = None

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        current = self.currentWidget()
        return current.sizeHint() if current is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        current = self.currentWidget()
        return current.minimumSizeHint() if current is not None else super().minimumSizeHint()

    def setCurrentIndexAnimated(  # noqa: N802 - Qt-style API
        self, index: int, *, direction: int = 1
    ) -> None:
        if index == self.currentIndex() or not 0 <= index < self.count():
            return
        self._finish_transition()
        outgoing = self.currentWidget()
        incoming = self.widget(index)
        if outgoing is None or incoming is None or not self.isVisible():
            super().setCurrentIndex(index)
            self.updateGeometry()
            return

        stack_layout = self.layout()
        if isinstance(stack_layout, QStackedLayout):
            stack_layout.setStackingMode(QStackedLayout.StackAll)

        outgoing_effect = QGraphicsOpacityEffect(outgoing)
        incoming_effect = QGraphicsOpacityEffect(incoming)
        outgoing_effect.setOpacity(1.0)
        incoming_effect.setOpacity(0.0)
        outgoing.setGraphicsEffect(outgoing_effect)
        incoming.setGraphicsEffect(incoming_effect)
        super().setCurrentIndex(index)
        self.updateGeometry()
        outgoing.show()
        incoming.show()
        incoming.raise_()

        fade_out = QPropertyAnimation(outgoing_effect, b"opacity", self)
        fade_out.setDuration(self._duration_ms)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.OutCubic)
        fade_in = QPropertyAnimation(incoming_effect, b"opacity", self)
        fade_in.setDuration(self._duration_ms)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(fade_out)
        group.addAnimation(fade_in)
        group.finished.connect(self._finish_transition)
        self._transition_widgets = (outgoing, incoming)
        self._transition_group = group
        group.start()

    def _finish_transition(self) -> None:
        group = self._transition_group
        self._transition_group = None
        if group is not None and group.state() != QAbstractAnimation.Stopped:
            group.stop()
        widgets = self._transition_widgets
        self._transition_widgets = None
        if widgets is not None:
            for widget in widgets:
                widget.setGraphicsEffect(None)
        stack_layout = self.layout()
        if isinstance(stack_layout, QStackedLayout):
            stack_layout.setStackingMode(QStackedLayout.StackOne)
        current = self.currentWidget()
        if current is not None:
            current.show()
            current.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._finish_transition()
        super().resizeEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.type() in {
            QEvent.StyleChange,
            QEvent.PaletteChange,
            QEvent.ApplicationPaletteChange,
        }:
            self._finish_transition()
        super().changeEvent(event)


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
        parent.installEventFilter(self)

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
        self._geometry_sync = QTimer(self)
        self._geometry_sync.setInterval(16)
        self._geometry_sync.timeout.connect(self.sync_to_parent)

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
        self._geometry_sync.start()
        self._fade.start()

    def finish_immediately(self) -> None:
        if self._animation_finished:
            return
        self._fade.stop()
        self._cleanup_after_animation()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override
        if watched is self.parentWidget() and event.type() == QEvent.Resize:
            self.sync_to_parent()
        return super().eventFilter(watched, event)

    def _cleanup_after_animation(self) -> None:
        if self._animation_finished:
            return
        self._animation_finished = True
        self._geometry_sync.stop()
        parent = self.parentWidget()
        if parent is not None:
            parent.removeEventFilter(self)
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
        description: Optional[str] = None,
    ):
        super().__init__()
        self.token_id = token_id
        self._on_change = on_change
        self._on_rename = on_rename

        self.setObjectName("tokenCard")
        self.setFixedWidth(self.CARD_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        tooltip = f"Token ID: {token_id}"
        if description:
            tooltip = f"{tooltip}\n{description}"
        self.setToolTip(tooltip)
        self.setProperty("hovered", False)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)
        root.setAlignment(Qt.AlignTop)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        self._icon_front: Optional[QPixmap] = None
        self._icon_back: Optional[QPixmap] = None
        self._flip_anim: Optional[QVariantAnimation] = None
        icon_path = token_icon_path(token_id)
        if icon_path and icon_path.exists():
            pix = QPixmap(str(icon_path)).scaled(
                self.ICON_SIZE,
                self.ICON_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._icon_front = pix
            self.icon_label.setPixmap(pix)
        back_path = token_back_icon_path(token_id)
        if self._icon_front is not None and back_path and back_path.exists():
            # Coin-flip on hover: a single half-spin to the back-side icon,
            # back again on leave — echo of the in-game marker-select spin
            # (INDUCTION shows turbo up front, supercharger on the back).
            self._icon_back = QPixmap(str(back_path)).scaled(
                self.ICON_SIZE,
                self.ICON_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._flip_anim = QVariantAnimation(self)
            self._flip_anim.setDuration(360)
            self._flip_anim.setEasingCurve(QEasingCurve.InOutQuad)
            self._flip_anim.valueChanged.connect(self._set_flip_progress)
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

    # ── Icon coin-flip ───────────────────────────────────────────

    def _set_flip_progress(self, t: float) -> None:
        # t in 0..1 is a half-spin around the vertical axis: the front face
        # is edge-on at 0.5, the back face fully shown at 1.
        sx = math.cos(math.pi * float(t))
        base = self._icon_front if sx >= 0 else self._icon_back
        if base is None:
            return
        squeezed = base.transformed(
            QTransform().scale(max(abs(sx), 0.04), 1.0),
            Qt.SmoothTransformation,
        )
        self.icon_label.setPixmap(squeezed)

    def _start_flip(self, to_back: bool) -> None:
        if self._flip_anim is None:
            return
        current = self._flip_anim.currentValue()
        start = float(current) if current is not None else 0.0
        self._flip_anim.stop()
        self._flip_anim.setStartValue(start)
        self._flip_anim.setEndValue(1.0 if to_back else 0.0)
        self._flip_anim.start()

    def _apply_changed_state(self, changed: bool) -> None:
        self.setProperty("changed", changed)
        self.style().unpolish(self)
        self.style().polish(self)

    # ── Hover effect ─────────────────────────────────────────────

    def enterEvent(self, event) -> None:
        self.setProperty("hovered", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self._start_flip(to_back=True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setProperty("hovered", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self._start_flip(to_back=False)
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
