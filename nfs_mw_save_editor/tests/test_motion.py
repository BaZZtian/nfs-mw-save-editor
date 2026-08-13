from __future__ import annotations

import os
from pathlib import Path
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtCore import (  # noqa: E402
    QAbstractAnimation,
    QEasingCurve,
    QEventLoop,
    QObject,
    QPoint,
    Property,
)
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.motion import PacedAnimation  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


class _Dial(QObject):
    """Something with a Qt property to be driven, and nothing else."""

    def __init__(self) -> None:
        super().__init__()
        self._angle = 0.0

    def _get_angle(self) -> float:
        return self._angle

    def _set_angle(self, value: float) -> None:
        self._angle = value

    angle = Property(float, _get_angle, _set_angle)


def test_it_ticks_faster_than_qt_drives_animations():
    """Qt's animation timer runs at 60Hz whatever the screen does, and anything
    crossing real distance steps visibly between two of those ticks.

    The interval is asserted rather than counted: how many ticks actually land
    depends on the timer resolution the process is granted, which is coarse in
    a bare test and fine in the running app - measured there at 165fps against
    Qt's 62.
    """
    assert PacedAnimation._INTERVAL_MS <= 7, "slower than one tick per 144Hz refresh"


def test_a_run_reaches_its_end_and_never_goes_backwards():
    app = _app()
    run = PacedAnimation()
    seen = []
    run.valueChanged.connect(seen.append)
    loop = QEventLoop()
    run.finished.connect(loop.quit)
    run.setDuration(60)
    run.setStartValue(0.0)
    run.setEndValue(1.0)
    run.start()
    loop.exec()

    assert seen[0] == 0.0
    assert seen[-1] == 1.0
    assert seen == sorted(seen), "the run went backwards"
    assert not run.isRunning()
    assert run.state() == QAbstractAnimation.Stopped


def test_a_late_tick_lands_where_the_clock_says():
    """Progress is read off a clock, not counted in ticks: a frame that took
    too long must not stretch the run into slow motion."""
    app = _app()
    run = PacedAnimation()
    seen = []
    run.valueChanged.connect(seen.append)
    ended = []
    run.finished.connect(lambda: ended.append(True))

    run.setDuration(30)
    run.start()
    time.sleep(0.2)          # a frame that overran the whole span
    app.processEvents()

    assert seen[-1] == 1.0, f"the run was stretched: {seen}"
    assert ended == [True]
    assert not run.isRunning()


def test_it_writes_the_property_it_was_given():
    app = _app()
    dial = _Dial()
    run = PacedAnimation(dial, b"angle", dial)
    run.setDuration(100)
    run.setStartValue(0.0)
    run.setEndValue(90.0)

    run.start()
    assert dial.angle == 0.0
    run.setCurrentTime(50)
    assert 0.0 < dial.angle < 90.0
    run.setCurrentTime(100)
    assert dial.angle == 90.0
    assert not run.isRunning()


def test_it_carries_a_point_across_the_screen():
    """Toasts slide by their position, which is a point and not a number."""
    app = _app()
    run = PacedAnimation()
    run.setDuration(100)
    run.setStartValue(QPoint(0, 0))
    run.setEndValue(QPoint(100, 40))

    run.start()
    run.setCurrentTime(50)
    half = run.currentValue()
    assert isinstance(half, QPoint)
    assert half == QPoint(50, 20)


def test_the_curve_is_applied_to_the_value():
    app = _app()
    run = PacedAnimation()
    run.setDuration(100)
    run.setStartValue(0.0)
    run.setEndValue(1.0)
    run.setEasingCurve(QEasingCurve.OutCubic)

    run.start()
    run.setCurrentTime(50)
    assert run.currentValue() > 0.6, "an ease-out that is not ahead by halfway"


def test_stopping_is_silent():
    """As Qt does it: `stop` leaves the value where it stands and says
    nothing, so a run cut short cannot be mistaken for one that arrived."""
    app = _app()
    run = PacedAnimation()
    ended = []
    run.finished.connect(lambda: ended.append(True))
    run.setDuration(100)
    run.start()
    run.setCurrentTime(40)
    caught = run.currentValue()
    run.stop()

    assert not run.isRunning()
    assert ended == []
    assert run.currentValue() == caught
