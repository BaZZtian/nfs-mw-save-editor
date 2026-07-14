"""Turbo card coin-flip: hover turns INDUCTION (4) over to the supercharger.

INDUCTION is one engine marker type covering turbo and supercharger; the
game ships marker icons for both, and the marker-select screen spins the
markers. The editor's card shows the turbo icon and does a single half-spin
to the supercharger icon on hover (back again on leave).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QAbstractAnimation, QEvent, QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

from ui.icon_map import token_back_icon_path
from ui.widgets import TokenCard


def _app():
    return QApplication.instance() or QApplication([])


def _card(tid: int) -> TokenCard:
    return TokenCard(
        token_id=tid,
        name="Card",
        have=0,
        want=0,
        max_val=5,
        on_change=lambda *_: None,
        on_rename=lambda *_: None,
    )


def test_back_icon_is_mapped_only_for_induction():
    back = token_back_icon_path(4)
    assert back is not None and back.name == "perf_supercharger.png"
    assert all(token_back_icon_path(t) is None for t in (1, 3, 8, 17, 21))


def test_flip_shows_front_back_and_edge_on():
    _app()
    card = _card(4)
    assert card._flip_anim is not None
    front = card._icon_front.toImage()
    back = card._icon_back.toImage()
    assert front != back

    card._set_flip_progress(0.0)
    assert card.icon_label.pixmap().toImage() == front
    card._set_flip_progress(1.0)
    assert card.icon_label.pixmap().toImage() == back
    card._set_flip_progress(0.5)  # edge-on: squeezed to (almost) nothing
    assert card.icon_label.pixmap().width() <= 3


def test_hover_events_drive_the_flip_animation():
    _app()
    card = _card(4)
    pos = QPointF(1.0, 1.0)
    card.enterEvent(QEnterEvent(pos, pos, pos))
    assert card._flip_anim.state() == QAbstractAnimation.Running
    assert card._flip_anim.endValue() == 1.0
    card.leaveEvent(QEvent(QEvent.Leave))
    assert card._flip_anim.endValue() == 0.0
    card._flip_anim.stop()


def test_cards_without_back_icon_do_not_flip():
    _app()
    card = _card(3)  # NOS: no back side
    assert card._flip_anim is None
    pos = QPointF(1.0, 1.0)
    card.enterEvent(QEnterEvent(pos, pos, pos))  # must not raise
    card.leaveEvent(QEvent(QEvent.Leave))
