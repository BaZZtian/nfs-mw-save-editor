"""Reusable UI rendering helpers for chunked card grids."""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
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
    Signal,
    QTimer,
)
from PySide6.QtWidgets import QGridLayout, QGraphicsOpacityEffect, QScrollArea, QWidget

logger = logging.getLogger(__name__)

_EVAL_MODE_NORMAL = "normal"
_EVAL_MODE_FOLLOWUP = "followup_after_metrics"


def fit_columns(
    available_width: int,
    card_min_width: int,
    *,
    spacing: int,
    max_columns: int,
) -> int:
    """How many cards of *card_min_width* fit into *available_width*.

    *available_width* is the viewport width already stripped of the grid's
    left/right margins. Cards whose content cannot compress (the tuning perf
    grid, for one) would otherwise be laid out below their own minimum and
    get clipped, since the card scroll areas have no horizontal scrollbar.
    """
    if card_min_width <= 0:
        return 1
    columns = (available_width + spacing) // (card_min_width + spacing)
    return max(1, min(int(max_columns), int(columns)))


def centered_side_margin(
    viewport_width: int,
    columns: int,
    card_max_width: int,
    *,
    spacing: int,
    base_margin: int,
) -> int:
    """Side margin that centres a row which stops growing before the viewport.

    Cards with a maximum width leave the rest of a wide viewport empty; giving
    that leftover to both margins keeps the row centred instead of parked
    against the left edge. Returns *base_margin* when the row fills the space.
    """
    widest_row = columns * card_max_width + max(0, columns - 1) * spacing
    spare = viewport_width - 2 * base_margin - widest_row
    if spare <= 0:
        return base_margin
    return base_margin + spare // 2


def refresh_widget_style(widget: QWidget) -> None:
    """Re-polish a widget after dynamic-property changes."""
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)


def _visible_shells_in_viewport(
    shells: Sequence[AnimatedCardShell],
    scroll_area: QScrollArea,
) -> list[AnimatedCardShell]:
    scrollbar = scroll_area.verticalScrollBar()
    viewport = scroll_area.viewport()
    if scrollbar is None or viewport is None or viewport.height() <= 0:
        return []
    top = scrollbar.value()
    bottom = top + viewport.height()
    visible = [
        shell
        for shell in shells
        if shell.isVisible()
        and shell.geometry().height() > 0
        and shell.geometry().bottom() > top
        and shell.geometry().top() < bottom
    ]
    visible.sort(key=lambda shell: (shell.geometry().y(), shell.geometry().x()))
    return visible


@dataclass
class BuildTimingMetrics:
    content_build_ms: float = 0.0
    shell_attach_ms: float = 0.0
    shell_pool_hits: int = 0
    shell_pool_misses: int = 0

    def extend(self, other: "BuildTimingMetrics") -> None:
        self.content_build_ms += other.content_build_ms
        self.shell_attach_ms += other.shell_attach_ms
        self.shell_pool_hits += other.shell_pool_hits
        self.shell_pool_misses += other.shell_pool_misses


class AnimatedCardShell(QWidget):
    """Layout-managed shell that animates one child widget into view."""

    revealFinished = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._content: Optional[QWidget] = None
        self._offset_y = 0
        self._animation_group: Optional[QSequentialAnimationGroup] = None
        self._reveal_generation = 0
        self._reveal_finished_slots: list[Callable[[], None]] = []
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self._opacity_effect.setEnabled(False)
        self.setGraphicsEffect(self._opacity_effect)

    def set_content(self, widget: QWidget) -> None:
        if self._content is widget:
            return
        if self._content is not None:
            self._content.hide()
            self._content.setParent(None)
        self._content = widget
        widget.setParent(self)
        widget.show()
        self.setSizePolicy(widget.sizePolicy())
        self.updateGeometry()
        if self.isVisible() and self.width() > 0 and self.height() > 0:
            self._apply_content_geometry()

    def content(self) -> Optional[QWidget]:
        return self._content

    def take_content(self) -> Optional[QWidget]:
        widget = self._content
        if widget is None:
            return None
        widget.setParent(None)
        widget.hide()
        self._content = None
        self.updateGeometry()
        return widget

    def sync_content_geometry(self) -> None:
        if self._content is None:
            return
        if self.width() <= 0 or self.height() <= 0:
            return
        self._apply_content_geometry()

    def clear_animation(self) -> None:
        self._reveal_generation += 1
        if self._animation_group is not None:
            self._animation_group.stop()
            self._animation_group.deleteLater()
            self._animation_group = None
        self._set_offset_y(0)
        self._opacity_effect.setOpacity(1.0)
        self._opacity_effect.setEnabled(False)

    def reset_for_reuse(self) -> None:
        self.clear_animation()
        for slot in self._reveal_finished_slots:
            try:
                self.revealFinished.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._reveal_finished_slots.clear()
        self.hide()
        self.updateGeometry()

    def add_reveal_finished_listener(self, slot: Callable[[], None]) -> None:
        self.revealFinished.connect(slot)
        self._reveal_finished_slots.append(slot)

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
            return self._content.sizeHint().expandedTo(self._content.minimumSize())
        return super().sizeHint()

    def minimumSizeHint(self):
        if self._content is not None:
            return self._content.minimumSizeHint().expandedTo(self._content.minimumSize())
        return super().minimumSizeHint()

    def play_reveal(
        self,
        *,
        delay_ms: int = 0,
        distance: int = 12,
        duration_ms: int = 300,
    ) -> None:
        if self._content is None:
            return
        self.clear_animation()
        self._opacity_effect.setEnabled(True)
        self._opacity_effect.setOpacity(0.0)
        self._set_offset_y(-abs(int(distance)))

        fade = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        fade.setDuration(int(duration_ms))
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutQuart)

        slide = QPropertyAnimation(self, b"offsetY", self)
        slide.setDuration(int(duration_ms))
        slide.setStartValue(-abs(int(distance)))
        slide.setEndValue(0)
        slide.setEasingCurve(QEasingCurve.OutQuart)

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
        duration_ms: int = 300,
        stable_checks: int = 2,
    ) -> None:
        if self._content is None:
            return
        self.clear_animation()
        self._opacity_effect.setEnabled(True)
        self._opacity_effect.setOpacity(0.0)
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
        self._opacity_effect.setOpacity(1.0)
        # A live QGraphicsOpacityEffect keeps an offscreen cache even at full
        # opacity.  Reused lazy-grid shells can otherwise repaint that stale
        # cache after a filter rebuild, so leave the effect enabled only while
        # the reveal is actually running.
        self._opacity_effect.setEnabled(False)
        if self._animation_group is not None:
            self._animation_group.deleteLater()
            self._animation_group = None
        self.revealFinished.emit()


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
        release_widget: Optional[Callable[[QWidget], None]] = None,
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
        self._release_widget = release_widget
        self._log = log or logger

        self._generation = 0
        self._columns = 1
        self._last_columns = 0
        self._items: list[Any] = []
        self._shells: list[AnimatedCardShell] = []
        self._shell_pool: list[AnimatedCardShell] = []
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

    @property
    def current_columns(self) -> int:
        return self._columns

    def has_rendered_content(self) -> bool:
        return bool(self._shells) or self._empty_widget is not None

    def replay_visible_reveal(self) -> None:
        if self._rendering:
            return
        shells = _visible_shells_in_viewport(self._shells, self._scroll_area)
        if not shells:
            return
        for shell in shells:
            shell.clear_animation()
            shell.sync_content_geometry()
        for index, shell in enumerate(shells):
            shell.play_reveal(delay_ms=index * self._stagger_ms)
        self._log.debug(
            "%s replay visible reveal: %d shell(s), viewport=%d px",
            self._name,
            len(shells),
            self._viewport_width(),
        )

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
        initial_batch, build_metrics = self._build_initial_batch()
        build_ms = batch_timer.elapsed()
        commit_ms = self._commit_batch(initial_batch)
        self._chunk_count = 1 if initial_batch else 0
        self._log.debug(
            "%s chunk %d: built %d card(s) in %d ms, committed in %d ms (content %.1f ms, shell %.1f ms, shell pool h/m=%d/%d)",
            self._name,
            self._chunk_count,
            len(initial_batch),
            build_ms,
            commit_ms,
            build_metrics.content_build_ms,
            build_metrics.shell_attach_ms,
            build_metrics.shell_pool_hits,
            build_metrics.shell_pool_misses,
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
                    shell.show()
            self._layout.activate()
            for shell in self._shells:
                shell.sync_content_geometry()
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
        batch, build_metrics = self._build_batch(max_items=None, budget_ms=self._frame_budget_ms)
        build_ms = batch_timer.elapsed()
        commit_ms = self._commit_batch(batch)
        self._chunk_count += 1
        self._log.debug(
            "%s chunk %d: built %d card(s) in %d ms, committed in %d ms (content %.1f ms, shell %.1f ms, shell pool h/m=%d/%d)",
            self._name,
            self._chunk_count,
            len(batch),
            build_ms,
            commit_ms,
            build_metrics.content_build_ms,
            build_metrics.shell_attach_ms,
            build_metrics.shell_pool_hits,
            build_metrics.shell_pool_misses,
        )
        if self._next_index < len(self._items):
            self._schedule_pump(generation)
        else:
            self._finish_render()

    def _build_initial_batch(self) -> tuple[list[AnimatedCardShell], BuildTimingMetrics]:
        batch, metrics = self._build_batch(max_items=1, budget_ms=None)
        if not batch:
            return batch, metrics
        target = self._estimate_initial_batch_size(batch[0])
        while self._next_index < len(self._items) and len(batch) < target:
            shell, shell_metrics = self._build_shell_for_next_item()
            if shell is None:
                break
            batch.append(shell)
            metrics.extend(shell_metrics)
        return batch, metrics

    def _build_batch(self, *, max_items: Optional[int], budget_ms: Optional[int]) -> tuple[list[AnimatedCardShell], BuildTimingMetrics]:
        if self._build_widget is None:
            return [], BuildTimingMetrics()
        batch: list[AnimatedCardShell] = []
        metrics = BuildTimingMetrics()
        elapsed = QElapsedTimer()
        elapsed.start()
        while self._next_index < len(self._items):
            shell, shell_metrics = self._build_shell_for_next_item()
            if shell is None:
                break
            batch.append(shell)
            metrics.extend(shell_metrics)
            if max_items is not None and len(batch) >= max_items:
                break
            if budget_ms is not None and batch and elapsed.elapsed() >= budget_ms:
                break
        return batch, metrics

    def _build_shell_for_next_item(self) -> tuple[Optional[AnimatedCardShell], BuildTimingMetrics]:
        metrics = BuildTimingMetrics()
        if self._build_widget is None or self._next_index >= len(self._items):
            return None, metrics
        content_timer = QElapsedTimer()
        content_timer.start()
        widget = self._build_widget(self._items[self._next_index])
        metrics.content_build_ms = float(content_timer.nsecsElapsed() / 1_000_000)
        shell_timer = QElapsedTimer()
        shell_timer.start()
        shell, from_pool = self._acquire_shell()
        shell.set_content(widget)
        metrics.shell_attach_ms = float(shell_timer.nsecsElapsed() / 1_000_000)
        if from_pool:
            metrics.shell_pool_hits = 1
        else:
            metrics.shell_pool_misses = 1
        self._next_index += 1
        return shell, metrics

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
                shell.show()
                self._shells.append(shell)
            self._layout.activate()
            for shell in batch:
                shell.sync_content_geometry()
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
                    self._dispose_shell(widget)
                else:
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

    def _shell_pool_parent(self) -> Optional[QWidget]:
        return self._layout.parentWidget()

    def _acquire_shell(self) -> tuple[AnimatedCardShell, bool]:
        if self._shell_pool:
            shell = self._shell_pool.pop()
            shell.reset_for_reuse()
            return shell, True
        return AnimatedCardShell(self._shell_pool_parent()), False

    def _release_shell(self, shell: AnimatedCardShell) -> None:
        shell.reset_for_reuse()
        pool_parent = self._shell_pool_parent()
        if pool_parent is not None and shell.parentWidget() is not pool_parent:
            shell.setParent(pool_parent)
        self._shell_pool.append(shell)

    def _dispose_shell(self, shell: AnimatedCardShell) -> None:
        shell.clear_animation()
        widget = shell.take_content()
        if widget is not None:
            if self._release_widget is not None:
                self._release_widget(widget)
            else:
                widget.deleteLater()
        self._release_shell(shell)


@dataclass
class LazyGridRowState:
    row_index: int
    items: list[Any]
    reserved_height: int
    placeholder: Optional[QWidget] = None
    shells: list[AnimatedCardShell] = field(default_factory=list)
    realized: bool = False

    def anchor_widget(self) -> Optional[QWidget]:
        if self.realized and self.shells:
            return self.shells[0]
        return self.placeholder


class ViewportLazyGridController(QObject):
    """Viewport-first row-aware renderer for large card grids."""

    def __init__(
        self,
        parent: QObject,
        *,
        name: str,
        layout: QGridLayout,
        scroll_area: QScrollArea,
        forward_buffer_rows: int = 2,
        backward_buffer_rows: int = 1,
        idle_restart_ms: int = 120,
        stagger_ms: int = 40,
        max_animated_cards: int = 12,
        split_initial_visible_batch: bool = False,
        release_widget: Optional[Callable[[QWidget], None]] = None,
        log: Optional[logging.Logger] = None,
    ):
        super().__init__(parent)
        self._name = str(name)
        self._layout = layout
        self._scroll_area = scroll_area
        self._forward_buffer_rows = max(0, int(forward_buffer_rows))
        self._backward_buffer_rows = max(0, int(backward_buffer_rows))
        self._idle_restart_ms = max(0, int(idle_restart_ms))
        self._stagger_ms = max(0, int(stagger_ms))
        self._max_animated_cards = max(0, int(max_animated_cards))
        self._split_initial_visible_batch = bool(split_initial_visible_batch)
        self._release_widget = release_widget
        self._log = log or logger

        self._generation = 0
        self._columns = 1
        self._last_columns = 0
        self._items: list[Any] = []
        self._rows: list[LazyGridRowState] = []
        self._build_widget: Optional[Callable[[Any], QWidget]] = None
        self._empty_widget_factory: Optional[Callable[[int], QWidget]] = None
        self._empty_widget: Optional[QWidget] = None
        self._shell_pool: list[AnimatedCardShell] = []
        self._animate = False
        self._rendering = False
        self._render_elapsed: Optional[QElapsedTimer] = None
        self._placeholder_row_height = 0
        self._realized_shell_count = 0
        self._render_start_viewport_width = 0
        self._eval_scheduled = False
        self._pending_eval_mode: Optional[str] = None
        self._initial_visible_eval_done = False
        self._idle_token = 0
        self._protected_range: tuple[int, int] = (0, -1)
        self._row_extents: list[tuple[int, int]] = []
        self._visible_reveal_blockers = 0
        self._idle_restart_pending = False
        self._pending_idle_immediate = True
        self._initial_split_consumed = False
        self._deferred_preload_rows: list[int] = []
        self._deferred_preload_scheduled = False
        self._deferred_preload_token = 0

        self._idle_restart_timer = QTimer(self)
        self._idle_restart_timer.setSingleShot(True)
        self._idle_restart_timer.timeout.connect(self._start_idle_prefetch)

        scrollbar = self._scroll_area.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.valueChanged.connect(self._on_scrollbar_changed)
            scrollbar.rangeChanged.connect(self._on_scrollbar_range_changed)

    @property
    def is_rendering(self) -> bool:
        return self._rendering

    @property
    def current_columns(self) -> int:
        return self._columns

    def has_rendered_content(self) -> bool:
        return bool(self._rows) or self._empty_widget is not None

    def replay_visible_reveal(self) -> None:
        if self._rendering:
            return
        shells = _visible_shells_in_viewport(
            [shell for row in self._rows if row.realized for shell in row.shells],
            self._scroll_area,
        )
        if not shells:
            return
        for shell in shells:
            shell.clear_animation()
            shell.sync_content_geometry()
        for index, shell in enumerate(shells):
            shell.play_reveal(delay_ms=index * self._stagger_ms)
        self._log.debug(
            "%s replay visible reveal: %d shell(s), viewport=%d px",
            self._name,
            len(shells),
            self._viewport_width(),
        )

    def cancel(self) -> None:
        self._generation += 1
        self._rendering = False
        self._eval_scheduled = False
        self._pending_eval_mode = None
        self._initial_visible_eval_done = False
        self._idle_token += 1
        self._idle_restart_timer.stop()
        self._visible_reveal_blockers = 0
        self._idle_restart_pending = False
        self._pending_idle_immediate = True
        self._initial_split_consumed = False
        self._deferred_preload_rows = []
        self._deferred_preload_scheduled = False
        self._deferred_preload_token += 1

    def clear(self) -> None:
        self.cancel()
        self._items = []
        self._rows = []
        self._build_widget = None
        self._empty_widget_factory = None
        self._empty_widget = None
        self._render_elapsed = None
        self._placeholder_row_height = 0
        self._realized_shell_count = 0
        self._render_start_viewport_width = 0
        self._protected_range = (0, -1)
        self._row_extents = []
        self._visible_reveal_blockers = 0
        self._idle_restart_pending = False
        self._pending_idle_immediate = True
        self._initial_split_consumed = False
        self._deferred_preload_rows = []
        self._deferred_preload_scheduled = False
        self._deferred_preload_token += 1
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
        scrollbar = self._scroll_area.verticalScrollBar()
        restore_scroll = 0
        if scrollbar is not None and not reset_scroll:
            restore_scroll = scrollbar.value()

        self._items = list(items)
        self._build_widget = build_widget
        self._empty_widget_factory = empty_widget_factory
        self._empty_widget = None
        self._columns = max(1, int(columns or 1))
        self._animate = bool(animate)
        self._render_elapsed = QElapsedTimer()
        self._render_elapsed.start()
        self._placeholder_row_height = 0
        self._realized_shell_count = 0
        self._render_start_viewport_width = self._viewport_width()
        self._protected_range = (0, -1)
        self._row_extents = []
        self._pending_eval_mode = None
        self._initial_visible_eval_done = False
        self._visible_reveal_blockers = 0
        self._idle_restart_pending = False
        self._pending_idle_immediate = True
        self._initial_split_consumed = False
        self._deferred_preload_rows = []
        self._deferred_preload_scheduled = False
        self._deferred_preload_token += 1

        self._clear_layout(delete_widgets=True)
        self._configure_columns(self._columns)

        if not self._items:
            self._rendering = False
            if empty_widget_factory is not None:
                self._empty_widget = empty_widget_factory(self._columns)
                self._layout.addWidget(self._empty_widget, 0, 0, 1, self._columns)
            self._log.debug("%s lazy render finished immediately (empty state)", self._name)
            return

        probe_height = self._build_probe_row_height(self._items[: self._columns])
        self._placeholder_row_height = max(1, probe_height)
        self._rows = [
            LazyGridRowState(
                row_index=row_index,
                items=list(self._items[row_index * self._columns:(row_index + 1) * self._columns]),
                reserved_height=self._placeholder_row_height,
            )
            for row_index in range(ceil(len(self._items) / self._columns))
        ]
        self._recompute_row_extents()
        self._rendering = True
        self._log.debug(
            "%s lazy render start: %d item(s), %d row(s), viewport=%d px, seed row=%d px",
            self._name,
            len(self._items),
            len(self._rows),
            self._render_start_viewport_width,
            self._placeholder_row_height,
        )
        self._commit_placeholders()

        if scrollbar is not None:
            scrollbar.setValue(0 if reset_scroll else restore_scroll)

        self._schedule_visible_eval(mode=_EVAL_MODE_NORMAL)

    def reflow(self, columns: int) -> None:
        new_columns = max(1, int(columns or 1))
        if new_columns == self._columns:
            return
        self._columns = new_columns
        self._log.debug("%s lazy reflow: regroup rows for %d column(s)", self._name, self._columns)
        self.schedule_render(
            self._items,
            build_widget=self._build_widget or (lambda _: QWidget()),
            columns=self._columns,
            empty_widget_factory=self._empty_widget_factory,
            animate=False,
            reset_scroll=False,
        )

    def _build_probe_row_height(self, row_items: Sequence[Any]) -> int:
        shells, _ = self._build_row_shells(row_items)
        height = self._estimate_row_height(shells)
        for shell in shells:
            self._dispose_shell(shell)
        return height

    def _build_row_shells(self, row_items: Sequence[Any]) -> tuple[list[AnimatedCardShell], BuildTimingMetrics]:
        if self._build_widget is None:
            return [], BuildTimingMetrics()
        shells: list[AnimatedCardShell] = []
        metrics = BuildTimingMetrics()
        for item in row_items:
            content_timer = QElapsedTimer()
            content_timer.start()
            widget = self._build_widget(item)
            metrics.content_build_ms += float(content_timer.nsecsElapsed() / 1_000_000)
            shell_timer = QElapsedTimer()
            shell_timer.start()
            shell, from_pool = self._acquire_shell()
            shell.set_content(widget)
            metrics.shell_attach_ms += float(shell_timer.nsecsElapsed() / 1_000_000)
            if from_pool:
                metrics.shell_pool_hits += 1
            else:
                metrics.shell_pool_misses += 1
            shells.append(shell)
        return shells, metrics

    def _estimate_row_height(self, shells: Sequence[AnimatedCardShell]) -> int:
        if not shells:
            return max(1, self._placeholder_row_height)
        return max(
            max(shell.sizeHint().height(), shell.minimumSizeHint().height(), 1)
            for shell in shells
        )

    def _commit_placeholders(self) -> None:
        restore_parent, restore_viewport = self._suspend_updates()
        try:
            for row in self._rows:
                placeholder = self._create_placeholder(row.reserved_height)
                row.placeholder = placeholder
                self._layout.addWidget(placeholder, row.row_index, 0, 1, self._columns)
            self._layout.activate()
            parent_widget = self._layout.parentWidget()
            if parent_widget is not None:
                parent_widget.updateGeometry()
        finally:
            self._restore_updates(restore_parent, restore_viewport)

    def _create_placeholder(self, height: int) -> QWidget:
        placeholder = QWidget()
        placeholder.setObjectName("lazyRowPlaceholder")
        placeholder.setFixedHeight(max(1, int(height)))
        return placeholder

    def _on_scrollbar_changed(self, _value: int) -> None:
        if not self._rendering:
            return
        self._idle_token += 1
        self._clear_deferred_preload_rows()
        self._schedule_visible_eval(mode=_EVAL_MODE_NORMAL)
        self._schedule_idle_restart(immediate=False)

    def _on_scrollbar_range_changed(self, _minimum: int, _maximum: int) -> None:
        if not self._rendering:
            return
        self._schedule_visible_eval(mode=_EVAL_MODE_NORMAL)

    def _schedule_visible_eval(self, *, mode: str) -> None:
        if not self._rendering:
            return
        if self._pending_eval_mode == _EVAL_MODE_NORMAL:
            return
        if self._pending_eval_mode == _EVAL_MODE_FOLLOWUP and mode == _EVAL_MODE_FOLLOWUP:
            return
        if self._pending_eval_mode is None or mode == _EVAL_MODE_NORMAL:
            self._pending_eval_mode = mode
        if self._eval_scheduled:
            return
        self._eval_scheduled = True
        generation = self._generation
        QTimer.singleShot(0, lambda gen=generation: self._run_visible_eval(gen))

    def _run_visible_eval(self, generation: int) -> None:
        self._eval_scheduled = False
        mode = self._pending_eval_mode or _EVAL_MODE_NORMAL
        self._pending_eval_mode = None
        self._evaluate_visible_rows(generation, mode=mode)

    def _evaluate_visible_rows(self, generation: int, *, mode: str) -> None:
        if generation != self._generation or not self._rendering:
            return
        visible_start, visible_end, viewport_ready = self._visible_row_range()
        if viewport_ready:
            preload_start = max(0, visible_start - self._backward_buffer_rows)
            preload_end = min(len(self._rows) - 1, visible_end + self._forward_buffer_rows)
        else:
            preload_start = visible_start
            preload_end = visible_end
        self._protected_range = (preload_start, preload_end)
        if mode == _EVAL_MODE_FOLLOWUP:
            target_range = range(visible_start, visible_end + 1)
            reason = "followup"
        else:
            if (
                self._split_initial_visible_batch
                and viewport_ready
                and not self._initial_split_consumed
            ):
                target_range = range(visible_start, visible_end + 1)
                self._initial_split_consumed = True
                self._deferred_preload_rows = [
                    row_index
                    for row_index in range(preload_start, preload_end + 1)
                    if row_index > visible_end and not self._rows[row_index].realized
                ]
                reason = "visible"
                if self._deferred_preload_rows:
                    self._schedule_deferred_preload_tick(generation, self._deferred_preload_token)
            else:
                target_range = range(preload_start, preload_end + 1)
                reason = "visible"
        target_rows = [row_index for row_index in target_range if not self._rows[row_index].realized]
        self._log.debug(
            "%s lazy %s band: strict %d-%d, preload %d-%d, ready=%s (%d/%d rows)",
            self._name,
            mode,
            visible_start,
            visible_end,
            preload_start,
            preload_end,
            viewport_ready,
            sum(1 for row in self._rows if row.realized),
            len(self._rows),
        )
        if target_rows:
            self._realize_rows(target_rows, reason=reason)
        else:
            self._log.debug(
                "%s lazy %s band: rows %d-%d already realized (%d/%d)",
                self._name,
                mode,
                preload_start,
                preload_end,
                sum(1 for row in self._rows if row.realized),
                len(self._rows),
            )
        if mode == _EVAL_MODE_NORMAL:
            if viewport_ready and not self._initial_visible_eval_done:
                self._initial_visible_eval_done = True
                self._schedule_idle_restart(immediate=True)
            elif not viewport_ready:
                self._schedule_visible_eval(mode=_EVAL_MODE_NORMAL)
        self._finish_if_complete()

    def _schedule_deferred_preload_tick(self, generation: int, token: int) -> None:
        if self._deferred_preload_scheduled or not self._deferred_preload_rows:
            return
        self._deferred_preload_scheduled = True
        QTimer.singleShot(0, lambda gen=generation, deferred_token=token: self._run_deferred_preload_tick(gen, deferred_token))

    def _run_deferred_preload_tick(self, generation: int, token: int) -> None:
        self._deferred_preload_scheduled = False
        if generation != self._generation or token != self._deferred_preload_token or not self._rendering:
            return
        next_row = None
        while self._deferred_preload_rows:
            candidate = self._deferred_preload_rows.pop(0)
            if 0 <= candidate < len(self._rows) and not self._rows[candidate].realized:
                next_row = candidate
                break
        if next_row is None:
            self._finish_if_complete()
            if self._initial_visible_eval_done:
                self._schedule_idle_restart(immediate=True)
            return
        self._realize_rows([next_row], reason="deferred_preload")
        if self._deferred_preload_rows:
            self._schedule_deferred_preload_tick(generation, token)
        else:
            if self._initial_visible_eval_done:
                self._schedule_idle_restart(immediate=True)
        self._finish_if_complete()

    def _visible_row_range(self) -> tuple[int, int, bool]:
        if not self._rows:
            return (0, -1, True)
        scrollbar = self._scroll_area.verticalScrollBar()
        viewport = self._scroll_area.viewport()
        if scrollbar is None or viewport is None:
            return (0, min(len(self._rows) - 1, 0), False)
        viewport_height = viewport.height()
        if viewport_height <= 0:
            return (0, 0, False)
        top = scrollbar.value()
        bottom = top + viewport_height
        start: Optional[int] = None
        end: Optional[int] = None
        for row in self._rows:
            row_top, row_bottom = self._row_bounds(row)
            if row_bottom > top and row_top < bottom:
                if start is None:
                    start = row.row_index
                end = row.row_index
            elif start is not None and row_top >= bottom:
                break
        if start is not None and end is not None:
            return (start, end, True)
        last_index = len(self._rows) - 1
        fallback = 0
        for row in self._rows:
            row_top, row_bottom = self._row_bounds(row)
            if row_bottom > top:
                fallback = row.row_index
                break
            fallback = row.row_index
        fallback = max(0, min(last_index, fallback))
        return (fallback, fallback, True)

    def _row_bounds(self, row: LazyGridRowState) -> tuple[int, int]:
        if 0 <= row.row_index < len(self._row_extents):
            return self._row_extents[row.row_index]
        estimated_top = 0
        if self._row_extents:
            estimated_top = self._row_extents[-1][1] + max(0, self._layout.verticalSpacing())
        estimated_bottom = estimated_top + max(1, row.reserved_height)
        return (estimated_top, estimated_bottom)

    def _realize_rows(self, row_indices: Sequence[int], *, reason: str) -> None:
        pending = [self._rows[row_index] for row_index in row_indices if not self._rows[row_index].realized]
        if not pending:
            return
        build_timer = QElapsedTimer()
        build_timer.start()
        build_metrics = BuildTimingMetrics()
        built_rows: list[tuple[LazyGridRowState, list[AnimatedCardShell]]] = []
        for row in pending:
            shells, row_metrics = self._build_row_shells(row.items)
            build_metrics.extend(row_metrics)
            built_rows.append((row, shells))
        build_ms = build_timer.elapsed()

        commit_timer = QElapsedTimer()
        commit_timer.start()
        restore_parent, restore_viewport = self._suspend_updates()
        try:
            for row, shells in built_rows:
                if row.placeholder is not None:
                    self._remove_widget_from_layout(row.placeholder)
                    row.placeholder.deleteLater()
                    row.placeholder = None
                row.shells = shells
                row.realized = True
                for col, shell in enumerate(shells):
                    self._layout.addWidget(shell, row.row_index, col)
                    shell.show()
            self._layout.activate()
            for _row, shells in built_rows:
                for shell in shells:
                    shell.sync_content_geometry()
            parent_widget = self._layout.parentWidget()
            if parent_widget is not None:
                parent_widget.updateGeometry()
        finally:
            self._restore_updates(restore_parent, restore_viewport)
        commit_ms = commit_timer.elapsed()

        previous_height = self._placeholder_row_height
        max_row_height = previous_height
        metrics_changed = False
        for row, shells in built_rows:
            previous_reserved_height = row.reserved_height
            row_height = max(self._estimate_row_height(shells), self._measured_row_height(row))
            row.reserved_height = max(row.reserved_height, row_height)
            if row.reserved_height != previous_reserved_height:
                metrics_changed = True
            max_row_height = max(max_row_height, row.reserved_height)
        if max_row_height > previous_height:
            self._placeholder_row_height = max_row_height
            metrics_changed = True
        if metrics_changed:
            self._recompute_row_extents()
            self._update_placeholder_heights_outside_protected()
            self._schedule_visible_eval(mode=_EVAL_MODE_FOLLOWUP)

        if self._animate:
            blocks_idle = reason in {"visible", "followup", "deferred_preload"}
            for row, shells in built_rows:
                for shell in shells:
                    if self._realized_shell_count >= self._max_animated_cards:
                        break
                    if blocks_idle:
                        self._register_visible_reveal_blocker(shell)
                    shell.queue_reveal(delay_ms=self._realized_shell_count * self._stagger_ms)
                    self._realized_shell_count += 1
                else:
                    continue
                break

        self._log.debug(
            "%s lazy %s swap: realized row(s) %s in %d ms build + %d ms commit (content %.1f ms, shell %.1f ms, shell pool h/m=%d/%d, %d/%d rows)",
            self._name,
            reason,
            ",".join(str(row.row_index) for row, _ in built_rows),
            build_ms,
            commit_ms,
            build_metrics.content_build_ms,
            build_metrics.shell_attach_ms,
            build_metrics.shell_pool_hits,
            build_metrics.shell_pool_misses,
            sum(1 for row in self._rows if row.realized),
            len(self._rows),
        )

    def _measured_row_height(self, row: LazyGridRowState) -> int:
        if row.realized and row.shells:
            heights = [shell.geometry().height() for shell in row.shells if shell.geometry().height() > 0]
            if heights:
                return max(heights)
        anchor = row.anchor_widget()
        if anchor is not None and anchor.geometry().height() > 0:
            return anchor.geometry().height()
        return row.reserved_height

    def _update_placeholder_heights_outside_protected(self) -> None:
        protected_start, protected_end = self._protected_range
        updated = 0
        restore_parent, restore_viewport = self._suspend_updates()
        try:
            for row in self._rows:
                if row.realized or row.placeholder is None:
                    continue
                if protected_start <= row.row_index <= protected_end:
                    continue
                if row.reserved_height < self._placeholder_row_height:
                    row.reserved_height = self._placeholder_row_height
                    row.placeholder.setFixedHeight(self._placeholder_row_height)
                    updated += 1
            if updated:
                self._layout.activate()
                parent_widget = self._layout.parentWidget()
                if parent_widget is not None:
                    parent_widget.updateGeometry()
        finally:
            self._restore_updates(restore_parent, restore_viewport)
        if updated:
            self._recompute_row_extents()
            self._log.debug(
                "%s lazy placeholder grow: %d row(s) updated to %d px outside band %d-%d",
                self._name,
                updated,
                self._placeholder_row_height,
                protected_start,
                protected_end,
            )

    def _start_idle_prefetch(self) -> None:
        if not self._rendering:
            return
        generation = self._generation
        idle_token = self._idle_token
        QTimer.singleShot(0, lambda gen=generation, token=idle_token: self._idle_prefetch_step(gen, token))

    def _idle_prefetch_step(self, generation: int, idle_token: int) -> None:
        if generation != self._generation or idle_token != self._idle_token or not self._rendering:
            return
        protected_start, protected_end = self._protected_range
        target = next(
            (
                row.row_index
                for row in self._rows
                if not row.realized and row.row_index > protected_end
            ),
            None,
        )
        if target is None:
            target = next(
                (
                    row.row_index
                    for row in reversed(self._rows)
                    if not row.realized and row.row_index < protected_start
                ),
                None,
            )
        if target is None:
            self._finish_if_complete()
            return
        self._realize_rows([target], reason="idle")
        self._finish_if_complete()
        if self._rendering and idle_token == self._idle_token:
            QTimer.singleShot(0, lambda gen=generation, token=idle_token: self._idle_prefetch_step(gen, token))

    def _schedule_idle_restart(self, *, immediate: bool) -> None:
        if not self._rendering:
            return
        if not self._initial_visible_eval_done:
            return
        if self._deferred_preload_rows or self._deferred_preload_scheduled:
            self._idle_restart_timer.stop()
            self._idle_restart_pending = True
            self._pending_idle_immediate = self._pending_idle_immediate and immediate
            return
        if self._visible_reveal_blockers > 0:
            self._idle_restart_timer.stop()
            self._idle_restart_pending = True
            self._pending_idle_immediate = self._pending_idle_immediate and immediate
            self._log.debug(
                "%s lazy idle deferred: %d reveal blocker(s), immediate=%s",
                self._name,
                self._visible_reveal_blockers,
                self._pending_idle_immediate,
            )
            return
        self._idle_restart_timer.stop()
        self._idle_restart_timer.start(0 if immediate else self._idle_restart_ms)

    def _recompute_row_extents(self) -> None:
        spacing = max(0, self._layout.verticalSpacing())
        self._row_extents = []
        top = 0
        for row in self._rows:
            height = max(1, int(row.reserved_height))
            bottom = top + height
            self._row_extents.append((top, bottom))
            top = bottom + spacing

    def _register_visible_reveal_blocker(self, shell: AnimatedCardShell) -> None:
        generation = self._generation
        self._visible_reveal_blockers += 1
        shell.add_reveal_finished_listener(lambda gen=generation: self._on_visible_reveal_finished(gen))

    def _on_visible_reveal_finished(self, generation: int) -> None:
        if generation != self._generation:
            return
        if self._visible_reveal_blockers <= 0:
            return
        self._visible_reveal_blockers -= 1
        self._log.debug(
            "%s lazy reveal blocker complete: %d remaining",
            self._name,
            self._visible_reveal_blockers,
        )
        if self._visible_reveal_blockers == 0:
            self._flush_pending_idle_restart()

    def _clear_deferred_preload_rows(self) -> None:
        self._deferred_preload_token += 1
        self._deferred_preload_rows = []
        self._deferred_preload_scheduled = False

    def _flush_pending_idle_restart(self) -> None:
        if not self._idle_restart_pending or not self._rendering or not self._initial_visible_eval_done:
            return
        immediate = self._pending_idle_immediate
        self._idle_restart_pending = False
        self._pending_idle_immediate = True
        self._log.debug("%s lazy idle resume after reveal batch: immediate=%s", self._name, immediate)
        self._idle_restart_timer.stop()
        self._idle_restart_timer.start(0 if immediate else self._idle_restart_ms)

    def _finish_if_complete(self) -> None:
        if not self._rendering:
            return
        if any(not row.realized for row in self._rows):
            return
        self._rendering = False
        self._idle_restart_timer.stop()
        total_ms = self._render_elapsed.elapsed() if self._render_elapsed is not None else 0
        self._log.debug(
            "%s lazy render finish: %d row(s), %d item(s) in %d ms",
            self._name,
            len(self._rows),
            len(self._items),
            total_ms,
        )

    def _remove_widget_from_layout(self, widget: QWidget) -> None:
        for index in range(self._layout.count()):
            item = self._layout.itemAt(index)
            if item is not None and item.widget() is widget:
                self._layout.takeAt(index)
                return

    def _clear_layout(self, *, delete_widgets: bool) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            if delete_widgets:
                if isinstance(widget, AnimatedCardShell):
                    self._dispose_shell(widget)
                else:
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

    def _shell_pool_parent(self) -> Optional[QWidget]:
        return self._layout.parentWidget()

    def _acquire_shell(self) -> tuple[AnimatedCardShell, bool]:
        if self._shell_pool:
            shell = self._shell_pool.pop()
            shell.reset_for_reuse()
            return shell, True
        return AnimatedCardShell(self._shell_pool_parent()), False

    def _release_shell(self, shell: AnimatedCardShell) -> None:
        shell.reset_for_reuse()
        pool_parent = self._shell_pool_parent()
        if pool_parent is not None and shell.parentWidget() is not pool_parent:
            shell.setParent(pool_parent)
        self._shell_pool.append(shell)

    def _dispose_shell(self, shell: AnimatedCardShell) -> None:
        shell.clear_animation()
        widget = shell.take_content()
        if widget is not None:
            if self._release_widget is not None:
                self._release_widget(widget)
            else:
                widget.deleteLater()
        self._release_shell(shell)
