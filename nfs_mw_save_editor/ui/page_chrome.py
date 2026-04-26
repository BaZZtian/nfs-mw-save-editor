"""Shared page chrome helpers used by multiple page mixins."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QWidget


class PageChromeMixin:
    def _make_stat_badge(self, text: str, object_name: str = "garageCardStatBadge") -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        label.setAlignment(Qt.AlignCenter)
        return label

    def _make_page_controls_bar(self) -> tuple[QFrame, QHBoxLayout]:
        frame = QFrame()
        frame.setObjectName("pageControlsRow")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        return frame, layout

    def _make_centered_search_host(self, search: QLineEdit, *, max_width: int = 460) -> QWidget:
        search.setMinimumWidth(220)
        search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        host = QWidget()
        host.setObjectName("pageControlsSearchHost")
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(search, 1)
        return host
