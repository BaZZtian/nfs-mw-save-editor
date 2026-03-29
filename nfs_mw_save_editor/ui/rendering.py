"""Reusable UI rendering helpers for chunked card grids."""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QObject,
    Property,
    QParallelAnimationGroup,
    QPauseAnimation,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    QTimer,
)
from PySide6.QtWidgets import QGridLayout, QGraphicsOpacityEffect, QScrollArea, QWidget

logger = logging.getLogger(__name__)


def refresh_widget_style(widget: QWidget) -> None:
    """Re-polish a widget after dynamic-property changes."""
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)


class AnimatedCardShell(QWidget):
    """Layout-managed shell that animates one child widget into view."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._content: Optional[QWidget] = None
        self._offset_y = 0
        self._animation_group: Optional[QSequentialAnimationGroup] = None

    def set_content(self, widget: QWidget) -> None:
        if self._content is widget:
            return
        if self._content is not None:
            self._content.setParent(None)
        self._content = widget
        widget.setParent(self)
        widget.show()
        self.setSizePolicy(widget.sizePolicy())
        self.updateGeometry()
        self._apply_content_geometry()

    def content(self) -> Optional[QWidget]:
        return self._content

    def clear_animation(self) -> None:
        if self._animation_group is not None:
            self._animation_group.stop()
            self._animation_group.deleteLater()
            self._animation_group = None
        self._set_offset_y(0)
        if self._content is not None:
            self._content.setGraphicsEffect(None)

    def _get_offset_y(self) -> int:
        return self._offset_y

    def _set_offset_y(self, value: int) -> None:
        self._offset_y = int(value)
        self._apply_content_geometry()

    offsetY = Property(int, _get_offset_y, _set_offset_y)

    def _apply_content_geometry(self) -> None:
        if self._content is None:
            return
        self._content.setGeometry(0, self._offset_y, self.width(), self.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_content_geometry()

    def sizeHint(self):
        if self._content is not None:
            return self._content.sizeHint()
        return super().sizeHint()

    def minimumSizeHint(self):
        if self._content is not None:
            return self._content.minimumSizeHint()
        return super().minimumSizeHint()

    def play_reveal(
        self,
        *,
        delay_ms: int = 0,
        distance: int = 12,
        duration_ms: int = 200,
    ) -> None:
        if self._content is None:
            return
        self.clear_animation()

        effect = QGraphicsOpacityEffect(self._content)
        effect.setOpacity(0.0)
        self._content.setGraphicsEffect(effect)
        self._set_offset_y(-abs(int(distance)))

        fade = QPropertyAnimation(effect, b"opacity", self)
        fade.setDuration(int(duration_ms))
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)

        slide = QPropertyAnimation(self, b"offsetY", self)
        slide.setDuration(int(duration_ms))
        slide.setStartValue(-abs(int(distance)))
        slide.setEndValue(0)
        slide.setEasingCurve(QEasingCurve.OutCubic)

        parallel = QParallelAnimationGroup(self)
        parallel.addAnimation(fade)
        parallel.addAnimation(slide)

        sequence = QSequentialAnimationGroup(self)
        if delay_ms > 0:
            sequence.addAnimation(QPauseAnimation(int(delay_ms), sequence))
        sequence.addAnimation(parallel)
        sequence.finished.connect(self._on_animation_finished)
        self._animation_group = sequence
        sequence.start()

    def _on_animation_finished(self) -> None:
        self._set_offset_y(0)
        if self._content is not None:
            self._content.setGraphicsEffect(None)
        if self._animation_group is not None:
            self._animation_group.deleteLater()
            self._animation_group = None


class ChunkedGridController(QObject):
    """Incrementally materialize card widgets into a grid layout."""

    def __init__(
        self,
        parent: QObject,
        *,
        name: str,
        layout: QGridLayout,
        scroll_area: QScrollArea,
        initial_batch: int = 2,
        frame_budget_ms: int = 7,
        stagger_ms: int = 24,
        max_animated_cards: int = 12,
        log: Optional[logging.Logger] = None,
    ):
        super().__init__(parent)
        self._name = str(name)
        self._layout = layout
        self._scroll_area = scroll_area
        self._initial_batch = max(1, int(initial_batch))
        self._frame_budget_ms = max(1, int(frame_budget_ms))
        self._stagger_ms = max(0, int(stagger_ms))
        self._max_animated_cards = max(0, int(max_animated_cards))
        self._log = log or logger

        self._generation = 0
        self._columns = 1
        self._last_columns = 0
        self._items: list[Any] = []
        self._shells: list[AnimatedCardShell] = []
        self._empty_widget: Optional[QWidget] = None
        self._build_widget: Optional[Callable[[Any], QWidget]] = None
        self._next_index = 0
        self._rendering = False
        self._animate = False
        self._render_elapsed: Optional[QElapsedTimer] = None
        self._chunk_count = 0

    @property
    def is_rendering(self) -> bool:
        return self._rendering

    def has_rendered_content(self) -> bool:
        return bool(self._shells) or self._empty_widget is not None

    def cancel(self) -> None:
        self._generation += 1
        self._rendering = False

    def clear(self) -> None:
        self.cancel()
        self._items = []
        self._build_widget = None
        self._next_index = 0
        self._shells = []
        self._empty_widget = None
        self._render_elapsed = None
        self._chunk_count = 0
        self._clear_layout(delete_widgets=True)

    def schedule_render(
        self,
        items: Sequence[Any],
        *,
        build_widget: Callable[[Any], QWidget],
        columns: int,
        empty_widget_factory: Optional[Callable[[int], QWidget]] = None,
        animate: bool,
        reset_scroll: bool,
    ) -> None:
        self.cancel()
        self._items = list(items)
        self._build_widget = build_widget
        self._next_index = 0
        self._shells = []
        self._empty_widget = None
        self._columns = max(1, int(columns or 1))
        self._animate = bool(animate)
        self._chunk_count = 0
        self._render_elapsed = QElapsedTimer()
        self._render_elapsed.start()

        self._clear_layout(delete_widgets=True)
        self._configure_columns(self._columns)
        if reset_scroll:
            scrollbar = self._scroll_area.verticalScrollBar()
            if scrollbar is not None:
                scrollbar.setValue(0)

        if not self._items:
            self._rendering = False
            if empty_widget_factory is not None:
                self._empty_widget = empty_widget_factory(self._columns)
                self._layout.addWidget(self._empty_widget, 0, 0, 1, self._columns)
            self._log.debug("%s render finished immediately (empty state)", self._name)
            return

        self._rendering = True
        self._log.debug("%s render start: %d item(s)", self._name, len(self._items))
        self._build_some(max_items=self._initial_batch, budget_ms=None)
        if self._next_index < len(self._items):
            self._schedule_pump(self._generation)
        else:
            self._finish_render()

    def reflow(self, columns: int) -> None:
        new_columns = max(1, int(columns or 1))
        if new_columns == self._columns:
            return
        self._columns = new_columns
        scroll_value = 0
        scrollbar = self._scroll_area.verticalScrollBar()
        if scrollbar is not None:
            scroll_value = scrollbar.value()

        self._clear_layout(delete_widgets=False)
        self._configure_columns(self._columns)

        if self._empty_widget is not None:
            self._layout.addWidget(self._empty_widget, 0, 0, 1, self._columns)
        else:
            for idx, shell in enumerate(self._shells):
                self._layout.addWidget(shell, idx // self._columns, idx % self._columns)

        if scrollbar is not None:
            scrollbar.setValue(scroll_value)

    def _schedule_pump(self, generation: int) -> None:
        QTimer.singleShot(0, lambda gen=generation: self._pump(gen))

    def _pump(self, generation: int) -> None:
        if generation != self._generation or not self._rendering:
            return
        batch_timer = QElapsedTimer()
        batch_timer.start()
        built = self._build_some(max_items=None, budget_ms=self._frame_budget_ms)
        self._chunk_count += 1
        self._log.debug(
            "%s chunk %d: built %d card(s) in %d ms",
            self._name,
            self._chunk_count,
            built,
            batch_timer.elapsed(),
        )
        if self._next_index < len(self._items):
            self._schedule_pump(generation)
        else:
            self._finish_render()

    def _build_some(self, *, max_items: Optional[int], budget_ms: Optional[int]) -> int:
        if self._build_widget is None:
            return 0
        built = 0
        elapsed = QElapsedTimer()
        elapsed.start()
        while self._next_index < len(self._items):
            widget = self._build_widget(self._items[self._next_index])
            shell = AnimatedCardShell(self._layout.parentWidget())
            shell.set_content(widget)
            self._shells.append(shell)
            self._layout.addWidget(shell, self._next_index // self._columns, self._next_index % self._columns)
            if self._animate and self._next_index < self._max_animated_cards:
                shell.play_reveal(delay_ms=self._next_index * self._stagger_ms)
            self._next_index += 1
            built += 1
            if max_items is not None and built >= max_items:
                break
            if budget_ms is not None and built >= 1 and elapsed.elapsed() >= budget_ms:
                break
        return built

    def _finish_render(self) -> None:
        self._rendering = False
        total_ms = self._render_elapsed.elapsed() if self._render_elapsed is not None else 0
        self._log.debug("%s render finish: %d item(s) in %d ms", self._name, len(self._shells), total_ms)

    def _clear_layout(self, *, delete_widgets: bool) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            if delete_widgets:
                if isinstance(widget, AnimatedCardShell):
                    widget.clear_animation()
                widget.deleteLater()

    def _configure_columns(self, columns: int) -> None:
        for col in range(max(self._last_columns, columns)):
            self._layout.setColumnStretch(col, 0)
            self._layout.setColumnMinimumWidth(col, 0)
        for col in range(columns):
            self._layout.setColumnStretch(col, 1)
        self._last_columns = columns
