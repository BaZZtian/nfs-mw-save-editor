"""Shared page chrome helpers used by multiple page mixins."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget


class PageChromeMixin:
    def _make_stat_badge(self, text: str, object_name: str = "contentCardStatBadge") -> QLabel:
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

    def _make_card_frame(
        self,
        *,
        object_name: str = "contentCard",
        changed: bool | None = None,
        minimum_width: int | None = None,
        vertical_policy: QSizePolicy.Policy = QSizePolicy.Fixed,
        size_constraint: QVBoxLayout.SizeConstraint | None = None,
    ) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName(object_name)
        if changed is not None:
            card.setProperty("changed", changed)
        card.setSizePolicy(QSizePolicy.Expanding, vertical_policy)
        if minimum_width is not None:
            card.setMinimumWidth(minimum_width)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        if size_constraint is not None:
            layout.setSizeConstraint(size_constraint)
        return card, layout

    def _make_card_separator(self, object_name: str = "contentCardSep") -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName(object_name)
        return sep

    def _make_card_field_label(self, text: str, object_name: str = "contentCardFieldLabel") -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setAlignment(Qt.AlignCenter)
        return label

    def _make_card_action_button(self, text: str, object_name: str = "cardActionButton") -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.setProperty("readyAction", False)
        return btn

    def _set_card_action_readiness(self, button: QPushButton, ready: bool) -> None:
        ready = bool(ready)
        if bool(button.property("readyAction")) == ready:
            return
        button.setProperty("readyAction", ready)
        button.style().unpolish(button)
        button.style().polish(button)
