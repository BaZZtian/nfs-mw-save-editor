"""Reusable UI rendering helpers for chunked card grids."""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from math import ceil
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
        self._reveal_generation = 0

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
        self._reveal_generation += 1
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

    def queue_reveal(
        self,
        *,
        delay_ms: int = 0,
        distance: int = 12,
        duration_ms: int = 200,
        stable_checks: int = 2,
    ) -> None:
        if self._content is None:
            return
        self.clear_animation()
        effect = QGraphicsOpacityEffect(self._content)
        effect.setOpacity(0.0)
        self._content.setGraphicsEffect(effect)
        self._set_offset_y(0)
        generation = self._reveal_generation
        self._schedule_settle_check(
            generation=generation,
            last_size=None,
            stable_count=0,
            stable_checks=max(1, int(stable_checks)),
            delay_ms=int(delay_ms),
            distance=abs(int(distance)),
            duration_ms=int(duration_ms),
        )

    def _schedule_settle_check(
        self,
        *,
        generation: int,
        last_size: Optional[tuple[int, int]],
        stable_count: int,
        stable_checks: int,
        delay_ms: int,
        distance: int,
        duration_ms: int,
    ) -> None:
        QTimer.singleShot(
            0,
            lambda gen=generation, size=last_size, count=stable_count, needed=stable_checks, delay=delay_ms, dist=distance, dur=duration_ms: self._continue_reveal(
                generation=gen,
                last_size=size,
                stable_count=count,
                stable_checks=needed,
                delay_ms=delay,
                distance=dist,
                duration_ms=dur,
            ),
        )

    def _continue_reveal(
        self,
        *,
        generation: int,
        last_size: Optional[tuple[int, int]],
        stable_count: int,
        stable_checks: int,
        delay_ms: int,
        distance: int,
        duration_ms: int,
    ) -> None:
        if generation != self._reveal_generation or self._content is None:
            return
        size = (self.width(), self.height())
        if size[0] <= 0 or size[1] <= 0:
            self._schedule_settle_check(
                generation=generation,
                last_size=size,
                stable_count=0,
                stable_checks=stable_checks,
                delay_ms=delay_ms,
                distance=distance,
                duration_ms=duration_ms,
            )
            return
        next_count = stable_count + 1 if last_size == size else 1
        if next_count >= stable_checks:
            self.play_reveal(delay_ms=delay_ms, distance=distance, duration_ms=duration_ms)
            return
        self._schedule_settle_check(
            generation=generation,
            last_size=size,
            stable_count=next_count,
            stable_checks=stable_checks,
            delay_ms=delay_ms,
            distance=distance,
            duration_ms=duration_ms,
        )

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
        self._render_start_viewport_width = 0
        self._first_commit_viewport_width: Optional[int] = None

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
        self._render_start_viewport_width = 0
        self._first_commit_viewport_width = None
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
        self._render_start_viewport_width = self._viewport_width()
        self._first_commit_viewport_width = None

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
        self._log.debug(
            "%s render start: %d item(s), viewport=%d px",
            self._name,
            len(self._items),
            self._render_start_viewport_width,
        )
        batch_timer = QElapsedTimer()
        batch_timer.start()
        initial_batch = self._build_initial_batch()
        build_ms = batch_timer.elapsed()
        commit_ms = self._commit_batch(initial_batch)
        self._chunk_count = 1 if initial_batch else 0
        self._log.debug(
            "%s chunk %d: built %d card(s) in %d ms, committed in %d ms",
            self._name,
            self._chunk_count,
            len(initial_batch),
            build_ms,
            commit_ms,
        )
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
        previous_sizes = self._snapshot_shell_sizes()

        restore_parent, restore_viewport = self._suspend_updates()
        try:
            self._clear_layout(delete_widgets=False)
            self._configure_columns(self._columns)

            if self._empty_widget is not None:
                self._layout.addWidget(self._empty_widget, 0, 0, 1, self._columns)
            else:
                for idx, shell in enumerate(self._shells):
                    self._layout.addWidget(shell, idx // self._columns, idx % self._columns)
            self._layout.activate()
            parent_widget = self._layout.parentWidget()
            if parent_widget is not None:
                parent_widget.updateGeometry()
        finally:
            self._restore_updates(restore_parent, restore_viewport)

        if scrollbar is not None:
            scrollbar.setValue(scroll_value)
        resized_visible = self._count_resized_shells(previous_sizes)
        self._log.debug(
            "%s reflow: cols=%d, viewport=%d px, resized visible=%d",
            self._name,
            self._columns,
            self._viewport_width(),
            resized_visible,
        )

    def _schedule_pump(self, generation: int) -> None:
        QTimer.singleShot(0, lambda gen=generation: self._pump(gen))

    def _pump(self, generation: int) -> None:
        if generation != self._generation or not self._rendering:
            return
        batch_timer = QElapsedTimer()
        batch_timer.start()
        batch = self._build_batch(max_items=None, budget_ms=self._frame_budget_ms)
        build_ms = batch_timer.elapsed()
        commit_ms = self._commit_batch(batch)
        self._chunk_count += 1
        self._log.debug(
            "%s chunk %d: built %d card(s) in %d ms, committed in %d ms",
            self._name,
            self._chunk_count,
            len(batch),
            build_ms,
            commit_ms,
        )
        if self._next_index < len(self._items):
            self._schedule_pump(generation)
        else:
            self._finish_render()

    def _build_initial_batch(self) -> list[AnimatedCardShell]:
        batch = self._build_batch(max_items=1, budget_ms=None)
        if not batch:
            return batch
        target = self._estimate_initial_batch_size(batch[0])
        while self._next_index < len(self._items) and len(batch) < target:
            shell = self._build_shell_for_next_item()
            if shell is None:
                break
            batch.append(shell)
        return batch

    def _build_batch(self, *, max_items: Optional[int], budget_ms: Optional[int]) -> list[AnimatedCardShell]:
        if self._build_widget is None:
            return []
        batch: list[AnimatedCardShell] = []
        elapsed = QElapsedTimer()
        elapsed.start()
        while self._next_index < len(self._items):
            shell = self._build_shell_for_next_item()
            if shell is None:
                break
            batch.append(shell)
            if max_items is not None and len(batch) >= max_items:
                break
            if budget_ms is not None and batch and elapsed.elapsed() >= budget_ms:
                break
        return batch

    def _build_shell_for_next_item(self) -> Optional[AnimatedCardShell]:
        if self._build_widget is None or self._next_index >= len(self._items):
            return None
        widget = self._build_widget(self._items[self._next_index])
        shell = AnimatedCardShell()
        shell.set_content(widget)
        self._next_index += 1
        return shell

    def _estimate_initial_batch_size(self, first_shell: AnimatedCardShell) -> int:
        viewport = self._scroll_area.viewport()
        if viewport is None:
            return self._initial_batch
        estimated_height = max(1, first_shell.sizeHint().height())
        row_stride = max(1, estimated_height + max(0, self._layout.verticalSpacing()))
        visible_rows = ceil(max(1, viewport.height()) / row_stride)
        return max(self._initial_batch, (visible_rows + 1) * self._columns)

    def _commit_batch(self, batch: Sequence[AnimatedCardShell]) -> int:
        if not batch:
            return 0
        previous_sizes = self._snapshot_shell_sizes()
        start_index = len(self._shells)
        timer = QElapsedTimer()
        timer.start()
        restore_parent, restore_viewport = self._suspend_updates()
        try:
            for offset, shell in enumerate(batch):
                index = start_index + offset
                self._layout.addWidget(shell, index // self._columns, index % self._columns)
                self._shells.append(shell)
            self._layout.activate()
            parent_widget = self._layout.parentWidget()
            if parent_widget is not None:
                parent_widget.updateGeometry()
        finally:
            self._restore_updates(restore_parent, restore_viewport)

        if self._first_commit_viewport_width is None:
            self._first_commit_viewport_width = self._viewport_width()
        resized_visible = self._count_resized_shells(previous_sizes)
        settle_waits = 0
        if self._animate:
            for offset, shell in enumerate(batch):
                index = start_index + offset
                if index >= self._max_animated_cards:
                    break
                shell.queue_reveal(delay_ms=index * self._stagger_ms)
                settle_waits += 2
        self._log.debug(
            "%s commit: %d card(s), viewport=%d px, resized visible=%d, settle waits=%d",
            self._name,
            len(batch),
            self._viewport_width(),
            resized_visible,
            settle_waits,
        )
        return timer.elapsed()

    def _finish_render(self) -> None:
        self._rendering = False
        total_ms = self._render_elapsed.elapsed() if self._render_elapsed is not None else 0
        self._log.debug(
            "%s render finish: %d item(s) in %d ms, viewport start=%d px, first commit=%s px, finish=%d px",
            self._name,
            len(self._shells),
            total_ms,
            self._render_start_viewport_width,
            self._first_commit_viewport_width if self._first_commit_viewport_width is not None else "n/a",
            self._viewport_width(),
        )

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

    def _viewport_width(self) -> int:
        viewport = self._scroll_area.viewport()
        if viewport is None:
            return 0
        return viewport.width()

    def _snapshot_shell_sizes(self) -> dict[int, tuple[int, int]]:
        return {idx: (shell.width(), shell.height()) for idx, shell in enumerate(self._shells)}

    def _count_resized_shells(self, previous_sizes: dict[int, tuple[int, int]]) -> int:
        resized = 0
        for idx, shell in enumerate(self._shells[: len(previous_sizes)]):
            if previous_sizes.get(idx) != (shell.width(), shell.height()):
                resized += 1
        return resized

    def _suspend_updates(self) -> tuple[bool, bool]:
        parent_widget = self._layout.parentWidget()
        viewport = self._scroll_area.viewport()
        parent_enabled = True if parent_widget is None else parent_widget.updatesEnabled()
        viewport_enabled = True if viewport is None else viewport.updatesEnabled()
        if parent_widget is not None:
            parent_widget.setUpdatesEnabled(False)
        if viewport is not None:
            viewport.setUpdatesEnabled(False)
        return parent_enabled, viewport_enabled

    def _restore_updates(self, parent_enabled: bool, viewport_enabled: bool) -> None:
        parent_widget = self._layout.parentWidget()
        viewport = self._scroll_area.viewport()
        if parent_widget is not None:
            parent_widget.setUpdatesEnabled(parent_enabled)
            parent_widget.updateGeometry()
            parent_widget.update()
        if viewport is not None:
            viewport.setUpdatesEnabled(viewport_enabled)
            viewport.update()
